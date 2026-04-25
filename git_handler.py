"""
Git Handler Module
Handles Git command execution
"""

import subprocess
import os
from pathlib import Path
import re
from typing import Optional

# Set environment to use UTF-8 encoding for git commands
GIT_ENV = os.environ.copy()
GIT_ENV["PYTHONIOENCODING"] = "utf-8"
# Force git to use UTF-8
GIT_ENV["LANG"] = "en_US.UTF-8"
GIT_ENV["LC_ALL"] = "en_US.UTF-8"

DEFAULT_AI_CONTEXT_MAX_CHARS = 120_000
DEFAULT_UNTRACKED_PREVIEW_MAX_FILES = 10
DEFAULT_UNTRACKED_PREVIEW_MAX_CHARS_PER_FILE = 6_000
DEFAULT_LOG_NEWEST_COMMITS = 60
DEFAULT_LOG_OLDEST_COMMITS = 20


def _run_git(
    repo_path: str,
    args: list[str],
    timeout: int = 30,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a git command and return CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=GIT_ENV,
        check=check,
        timeout=timeout,
    )


def _run_git_stdout(
    repo_path: str,
    args: list[str],
    timeout: int = 30,
    check: bool = False,
) -> str:
    """Run a git command and return stdout (stripped)."""
    result = _run_git(repo_path, args=args, timeout=timeout, check=check)
    return (result.stdout or "").strip()


def _run_git_nul_list(
    repo_path: str,
    args: list[str],
    timeout: int = 30,
) -> list[str]:
    """
    Run a git command that outputs NUL-separated paths (with -z) and return a list.
    """
    out = _run_git_stdout(repo_path, args=args, timeout=timeout, check=False)
    if not out:
        return []
    return [p for p in out.split("\x00") if p]


def _safe_read_text_file(path: Path, max_chars: int) -> tuple[str, bool]:
    """
    Read a file as UTF-8 text (replacement on errors). Returns (content, truncated?).
    If reading fails, returns ("", False).
    """
    try:
        # Use bytes first so we can cap without loading huge files.
        with path.open("rb") as f:
            data = f.read(max_chars + 1)
        truncated = len(data) > max_chars
        text = data[:max_chars].decode("utf-8", errors="replace")
        return text, truncated
    except Exception:
        return "", False


def _truncate_middle(text: str, max_len: int) -> str:
    """Truncate by keeping head+tail with a clear marker."""
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    # Keep a bit more head than tail (diff headers are at the top)
    head_len = max(0, int(max_len * 0.7))
    tail_len = max_len - head_len
    head = text[:head_len].rstrip()
    tail = text[-tail_len:].lstrip() if tail_len > 0 else ""
    return f"{head}\n... (truncated) ...\n{tail}".strip()


def _extract_diff_file_id(diff_chunk: str) -> Optional[str]:
    """
    Extract file path from a diff chunk header line:
    'diff --git a/path b/path'
    """
    first_line = diff_chunk.splitlines()[0] if diff_chunk else ""
    m = re.match(r"^diff --git a/(.+?) b/(.+?)$", first_line.strip())
    if not m:
        return None
    # Prefer the b/ path
    return m.group(2)


def _compact_diff_by_file(
    diff_text: str,
    max_chars: int,
    max_files: int = 25,
    per_file_max_chars: int = 4_000,
) -> str:
    """
    Compact a unified diff by slicing it into file chunks and budgeting chars per file.
    This avoids "cutting from the start" and tries to cover more files.
    """
    if not diff_text or max_chars <= 0:
        return ""
    if len(diff_text) <= max_chars:
        return diff_text

    # Find file chunk boundaries at "diff --git".
    indices = [m.start() for m in re.finditer(r"(?m)^diff --git ", diff_text)]
    if not indices:
        return _truncate_middle(diff_text, max_chars)

    preamble = diff_text[: indices[0]].strip()
    file_chunks: list[tuple[str, str]] = []
    for i, start in enumerate(indices):
        end = indices[i + 1] if i + 1 < len(indices) else len(diff_text)
        chunk = diff_text[start:end].strip()
        file_id = _extract_diff_file_id(chunk) or f"file_{i+1}"
        file_chunks.append((file_id, chunk))

    # Dedupe by file_id (keep first occurrence).
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for file_id, chunk in file_chunks:
        if file_id in seen:
            continue
        seen.add(file_id)
        deduped.append((file_id, chunk))

    if len(deduped) > max_files:
        deduped = deduped[:max_files]

    header = ""
    if preamble:
        header = _truncate_middle(preamble, min(2_000, max_chars)).strip() + "\n\n"

    remaining = max_chars - len(header)
    if remaining <= 0:
        return header.strip()

    # Simple budgeting: cap each file chunk, and stop when out of budget.
    out_parts: list[str] = []
    for file_id, chunk in deduped:
        if remaining <= 0:
            break
        budget = min(per_file_max_chars, remaining)
        clipped = _truncate_middle(chunk, budget)
        out_parts.append(clipped)
        remaining -= len(clipped) + 2  # +2 for \n\n join

    compacted = (header + "\n\n".join(out_parts)).strip()
    if len(compacted) > max_chars:
        compacted = _truncate_middle(compacted, max_chars)
    omitted = len(file_chunks) - len(deduped)
    if omitted > 0:
        compacted += f"\n\n... ({omitted} more file diffs omitted) ..."
    return compacted.strip()


def _get_recent_history(
    repo_path: str,
    max_commits: int = DEFAULT_LOG_NEWEST_COMMITS,
) -> str:
    """
    Get a compact representation of full git history.

    - Always includes newest commits (up to max_commits)
    - Also includes oldest commits (tail) to reflect full history
    - Adds total commit count for context
    """
    pretty = "--pretty=format:%h %s (%an, %ar)"

    total_str = _run_git_stdout(
        repo_path,
        ["rev-list", "--count", "HEAD"],
        timeout=30,
        check=False,
    )
    try:
        total = int(total_str) if total_str else 0
    except ValueError:
        total = 0

    newest = _run_git_stdout(
        repo_path,
        ["log", f"-n{max_commits}", pretty],
        timeout=60,
        check=False,
    )
    oldest = _run_git_stdout(
        repo_path,
        ["log", "--reverse", f"-n{DEFAULT_LOG_OLDEST_COMMITS}", pretty],
        timeout=60,
        check=False,
    )

    parts: list[str] = []
    parts.append(f"Total commits: {total}")
    if newest:
        parts.append("Newest commits:\n" + newest)
    if total > (max_commits + DEFAULT_LOG_OLDEST_COMMITS):
        omitted = total - (max_commits + DEFAULT_LOG_OLDEST_COMMITS)
        parts.append(f"... ({omitted} commits omitted) ...")
    if oldest:
        parts.append("Oldest commits:\n" + oldest)
    return "\n\n".join(parts).strip()


def _get_changed_paths(repo_path: str) -> dict[str, list[str]]:
    """
    Return changed paths grouped by staged/unstaged/untracked.
    Uses -z to handle special characters in paths.
    """
    staged = _run_git_nul_list(
        repo_path,
        ["diff", "--cached", "--name-only", "-z"],
        timeout=30,
    )
    unstaged = _run_git_nul_list(
        repo_path,
        ["diff", "--name-only", "-z"],
        timeout=30,
    )
    untracked = _run_git_nul_list(
        repo_path,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        timeout=30,
    )
    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def _format_paths(title: str, paths: list[str], max_items: int = 200) -> str:
    if not paths:
        return f"{title} (0)\n(none)"
    display = paths[:max_items]
    more = len(paths) - len(display)
    lines = "\n".join(f"- {p}" for p in display)
    if more > 0:
        lines += f"\n... (+{more} more)"
    return f"{title} ({len(paths)})\n{lines}"


def _build_ai_change_context(repo_path: str, status_short: str) -> str:
    """
    Build a rich context string for AI: status + file list + stats + diffs + untracked previews + recent history.
    Applies best-effort compaction if too large.
    """
    paths = _get_changed_paths(repo_path)

    # Smaller, higher-signal summaries
    diff_stat = _run_git_stdout(
        repo_path,
        ["diff", "--stat"],
        timeout=60,
        check=False,
    )
    diff_stat_cached = _run_git_stdout(
        repo_path,
        ["diff", "--cached", "--stat"],
        timeout=60,
        check=False,
    )

    # Diffs (use low context to fit more hunks)
    diff_unstaged = _run_git_stdout(
        repo_path,
        ["diff", "--no-color", "--unified=1"],
        timeout=120,
        check=False,
    )
    diff_staged = _run_git_stdout(
        repo_path,
        ["diff", "--cached", "--no-color", "--unified=1"],
        timeout=120,
        check=False,
    )

    recent_history = _get_recent_history(repo_path)

    # Untracked file previews (since git diff doesn't include them)
    untracked_previews: list[str] = []
    repo_root = Path(repo_path)
    for rel in paths["untracked"][:DEFAULT_UNTRACKED_PREVIEW_MAX_FILES]:
        p = repo_root / rel
        # Skip directories just in case
        if p.exists() and p.is_file():
            content, truncated = _safe_read_text_file(
                p,
                DEFAULT_UNTRACKED_PREVIEW_MAX_CHARS_PER_FILE,
            )
            if content:
                suffix = "\n... (file truncated) ..." if truncated else ""
                untracked_previews.append(f"### {rel}\n{content}{suffix}".strip())
            else:
                untracked_previews.append(f"### {rel}\n(binary or unreadable preview)")
        else:
            untracked_previews.append(f"### {rel}\n(missing on disk)")

    context_parts: list[str] = []
    context_parts.append(
        "## Git status (short)\n" + (status_short if status_short else "(empty)")
    )
    context_parts.append(
        "## Changed paths\n"
        + "\n\n".join(
            [
                _format_paths("Staged", paths["staged"]),
                _format_paths("Unstaged", paths["unstaged"]),
                _format_paths("Untracked", paths["untracked"]),
            ]
        )
    )
    context_parts.append(
        "## Diff summary (unstaged)\n" + (diff_stat if diff_stat else "(empty)")
    )
    context_parts.append(
        "## Diff summary (staged)\n"
        + (diff_stat_cached if diff_stat_cached else "(empty)")
    )
    if untracked_previews:
        context_parts.append(
            "## Untracked file previews\n" + "\n\n".join(untracked_previews)
        )
    context_parts.append(
        "## Recent history (git log)\n"
        + (recent_history if recent_history else "(empty)")
    )
    context_parts.append(
        "## Staged diff (git diff --cached)\n"
        + (diff_staged if diff_staged else "(empty)")
    )
    context_parts.append(
        "## Unstaged diff (git diff)\n"
        + (diff_unstaged if diff_unstaged else "(empty)")
    )

    full_context = "\n\n".join(context_parts).strip()
    if len(full_context) <= DEFAULT_AI_CONTEXT_MAX_CHARS:
        return full_context

    # If too long: compact the biggest parts first (diffs), keeping other summaries & history.
    # Allocate diff budget ~60% for diffs, 40% for everything else.
    non_diff_parts = "\n\n".join(context_parts[:-2]).strip()
    non_diff_budget = min(
        len(non_diff_parts),
        int(DEFAULT_AI_CONTEXT_MAX_CHARS * 0.4),
    )
    non_diff = _truncate_middle(non_diff_parts, non_diff_budget).strip()

    remaining = DEFAULT_AI_CONTEXT_MAX_CHARS - len(non_diff) - 2
    if remaining <= 0:
        return _truncate_middle(full_context, DEFAULT_AI_CONTEXT_MAX_CHARS)

    # Split remaining between staged/unstaged diffs, but only if they exist.
    diffs: list[tuple[str, str]] = [
        ("## Staged diff (git diff --cached)", diff_staged),
        ("## Unstaged diff (git diff)", diff_unstaged),
    ]
    available = [(title, txt) for title, txt in diffs if txt]
    if not available:
        return _truncate_middle(full_context, DEFAULT_AI_CONTEXT_MAX_CHARS)

    per = max(5_000, remaining // len(available))
    compacted_diffs: list[str] = []
    for title, txt in available:
        # Keep the title, compact by file.
        budget = max(1_000, min(per, remaining))
        compacted = _compact_diff_by_file(txt, max_chars=budget)
        compacted_diffs.append(f"{title}\n{compacted}".strip())
        remaining -= len(compacted) + len(title) + 2
        if remaining <= 0:
            break

    compact_context = (non_diff + "\n\n" + "\n\n".join(compacted_diffs)).strip()
    return _truncate_middle(compact_context, DEFAULT_AI_CONTEXT_MAX_CHARS)


def check_is_git_repo(repo_path: str) -> bool:
    """Return True if repo_path looks like a Git repository."""
    git_dir = Path(repo_path) / ".git"
    return git_dir.exists() and git_dir.is_dir()


def get_git_status(repo_path: str) -> tuple[str, str]:
    """
    Get git status and a rich AI context string.

    Returns (status_output, ai_context).
    """
    try:
        # Get git status
        status_output = _run_git_stdout(
            repo_path,
            ["status", "--short"],
            timeout=30,
            check=False,
        )

        # Build richer AI input (diffs + stats + untracked previews + history)
        ai_context = _build_ai_change_context(repo_path, status_short=status_output)
        return status_output, ai_context
    except Exception as e:
        raise Exception(f"Error getting git status: {str(e)}")


def has_changes(repo_path: str) -> bool:
    """Return True if there are any uncommitted changes."""
    try:
        status_output, _ = get_git_status(repo_path)
        return len(status_output) > 0
    except Exception:
        return False


def add_all_changes(repo_path: str) -> bool:
    """Run `git add .` to stage all changes."""
    try:
        # Use list arguments to prevent shell injection
        subprocess.run(
            ["git", "add", "."],
            cwd=repo_path,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=GIT_ENV,
            check=True,
            timeout=30,  # 30 second timeout
        )
        return True
    except subprocess.TimeoutExpired:
        raise Exception("git add command timed out")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else e.stdout.strip()
        raise Exception(f"Error running git add: {error_msg}")
    except Exception as e:
        raise Exception(f"Unknown error: {str(e)}")


def commit_changes(repo_path: str, message: str) -> bool:
    """Run `git commit` with a (possibly multi-line) commit message."""
    try:
        # For multi-line commit messages, we need to use -m for each line
        # or use stdin. Using -m multiple times is safer.
        lines = message.split("\n")

        # Build git commit command with multiple -m flags
        # This preserves the format: summary, blank line, description
        commit_args = ["git", "commit"]
        for line in lines:
            commit_args.extend(["-m", line])

        subprocess.run(
            commit_args,
            cwd=repo_path,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=GIT_ENV,
            check=True,
            timeout=30,  # 30 second timeout
        )
        return True
    except subprocess.TimeoutExpired:
        raise Exception("git commit command timed out")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else e.stdout.strip()
        raise Exception(f"Error committing: {error_msg}")
    except Exception as e:
        raise Exception(f"Unknown error: {str(e)}")


def push_changes(repo_path: str) -> bool:
    """Run `git push` to push commits to remote."""
    try:
        # Check if remote exists
        remote_result = subprocess.run(
            ["git", "remote"],
            cwd=repo_path,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=GIT_ENV,
            check=False,
        )

        if not remote_result.stdout.strip():
            raise Exception("Repository has no remote configured")

        # Push to remote
        subprocess.run(
            ["git", "push"],
            cwd=repo_path,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=GIT_ENV,
            check=True,
            timeout=120,  # 2 minute timeout for push (may take time)
        )
        return True
    except subprocess.TimeoutExpired:
        raise Exception("git push command timed out")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else e.stdout.strip()
        raise Exception(f"Error pushing: {error_msg}")
    except Exception as e:
        raise Exception(f"Error: {str(e)}")
