"""
Gemini Client Module
Integrates with Google Gemini API to automatically generate commit messages
"""

import os
import sys
from pathlib import Path

try:
    # Optional dependency: PyInstaller sometimes misses it.
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None


def _load_env_fallback() -> None:
    """
    Minimal .env loader if python-dotenv is not available.

    Looks for `.env` next to the executable (PyInstaller) or next to this file.
    """
    candidates: list[Path] = []

    # When frozen, prefer the folder containing the exe.
    if getattr(sys, "frozen", False):
        try:
            candidates.append(Path(sys.executable).resolve().parent / ".env")
        except Exception:
            pass

    # Source run: alongside this module.
    try:
        candidates.append(Path(__file__).resolve().parent / ".env")
    except Exception:
        pass

    # As a last resort, current working directory.
    candidates.append(Path.cwd() / ".env")

    env_path = next(
        (p for p in candidates if p.exists() and p.is_file()),
        None,
    )
    if not env_path:
        return

    try:
        raw_text = env_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        for raw in raw_text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            os.environ.setdefault(key, value)
    except Exception:
        return


def _load_env() -> None:
    """Load environment variables from `.env` (best-effort)."""
    if load_dotenv is not None:
        try:
            load_dotenv()
            return
        except Exception:
            pass
    _load_env_fallback()


# Load environment variables (best-effort)
_load_env()

# Timeout for API requests (30 seconds)
API_TIMEOUT = 30


def initialize_gemini():
    """Initialize and return the Gemini API client."""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise Exception("GEMINI_API_KEY not found in .env file")

    if api_key == "your_api_key_here":
        raise Exception("Please configure GEMINI_API_KEY in .env file")

    try:
        # Lazy import so the GUI can still start even if dependencies
        # are missing.
        from google.genai import Client  # type: ignore

        return Client(api_key=api_key)
    except ModuleNotFoundError as e:
        raise Exception(
            "Missing dependency: google-genai. "
            "Please install requirements and rebuild the executable."
        ) from e
    except Exception as e:
        raise Exception(f"Error initializing Gemini API: {str(e)}")


def select_available_models(client) -> list[str]:
    """
    Query available models from API and return usable generation models.
    This is fully dynamic per run and uses API-returned metadata only.
    """
    try:
        candidates: list[tuple[int, int, str]] = []
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            # model names come as "models/<name>"
            normalized = name.split("/", 1)[-1]
            if not normalized:
                continue

            supported_actions = getattr(model, "supported_actions", []) or []
            # Keep only general-purpose generation models using action metadata.
            # Requiring batch + cache support filters out TTS/live/embedding-like
            # specialized endpoints without relying on model name hardcoding.
            required_actions = {
                "generateContent",
                "countTokens",
                "createCachedContent",
                "batchGenerateContent",
            }
            if not required_actions.issubset(set(supported_actions)):
                continue

            description = (getattr(model, "description", "") or "").lower()
            if any(
                token in description
                for token in (
                    "robotics",
                    "text to speech",
                    "tts",
                    "audio",
                    "image",
                    "embedding",
                    "live api",
                )
            ):
                continue

            # Cost proxy from API metadata only:
            # lower token limits are typically lower-cost serving tiers.
            input_limit = int(getattr(model, "input_token_limit", 10**9) or 10**9)
            output_limit = int(getattr(model, "output_token_limit", 10**9) or 10**9)
            candidates.append((input_limit, output_limit, normalized))

        # Sort cheapest-looking models first by metadata, then deduplicate by name.
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        ordered_names = [name for _, _, name in candidates]
        unique_available = list(dict.fromkeys(ordered_names))
        return unique_available
    except Exception:
        return []


def generate_commit_message(diff_content: str) -> str:
    """
    Generate commit message from git change context using Gemini API

    Args:
        diff_content: Git change context (status/log/stats/diffs/previews)

    Returns:
        AI-generated commit message
    """
    if not diff_content or not diff_content.strip():
        return "Update code"

    try:
        client = initialize_gemini()

        def _is_truncated_or_compacted(text: str) -> bool:
            markers = (
                "truncated",
                "omitted",
                "... (truncated) ...",
                "... (context truncated",
                "more file diffs omitted",
            )
            lower = text.lower()
            return any(m in lower for m in markers)

        def _extract_finish_reason(resp) -> str:
            """
            Best-effort extraction of model finish reason.
            Gemini SDK response shape may differ by version.
            """
            try:
                candidates = getattr(resp, "candidates", None) or []
                if not candidates:
                    return ""
                finish_reason = getattr(candidates[0], "finish_reason", "")
                return str(finish_reason or "").strip().lower()
            except Exception:
                return ""

        def _looks_incomplete_message(text: str) -> bool:
            """
            Heuristic for truncated commit messages:
            - Ends with dangling punctuation/list marker
            - Very short body despite requested structure
            """
            if not text:
                return True

            normalized = text.rstrip()
            if not normalized:
                return True

            dangling_suffixes = (":", "-", "(", "[", "{", ",", "/", "\\")
            if normalized.endswith(dangling_suffixes):
                return True

            lines = normalized.splitlines()
            if len(lines) >= 2:
                body_lines = [ln for ln in lines[1:] if ln.strip()]
                # Body unexpectedly short often means token cut.
                if len(body_lines) <= 1:
                    return True

            # No sentence terminator at the end can indicate cutoff.
            if normalized[-1] not in (".", "!", "?", "`", ")", "]"):
                # Allow complete bullet-list endings:
                last_line = lines[-1].strip() if lines else ""
                if not (last_line.startswith("- ") and len(last_line) > 3):
                    return True

            return False

        # Limit input length to avoid exceeding model context.
        # Prefer keeping both start and end rather than truncating only the
        # start.
        max_input_length = 120000  # ~120k characters
        was_truncated = False
        if len(diff_content) > max_input_length:
            head_len = int(max_input_length * 0.7)
            tail_len = max_input_length - head_len
            head = diff_content[:head_len].rstrip()
            tail = diff_content[-tail_len:].lstrip()
            diff_content = (
                f"{head}\n" "... (context truncated due to length) ...\n" f"{tail}"
            )
            was_truncated = True

        detailed_mode = was_truncated or _is_truncated_or_compacted(diff_content)

        if detailed_mode:
            prompt = (
                "Generate a commit message in English based on the following git "
                "change context.\n"
                "The context may include git status, changed file lists, diff "
                "summaries, untracked file previews, recent git log, and "
                "staged/unstaged diffs.\n\n"
                "Important: The context may be truncated/compacted. "
                "If so, infer details from the file list and diff stats rather "
                "than referencing exact line-level changes.\n\n"
                "The commit message must follow this format:\n"
                "1. First line: A short summary (max 50 characters) in format "
                '"Type: Brief description"\n'
                "2. Blank line\n"
                "3. A detailed body (more detailed than usual):\n"
                "   - Prefer 8-14 bullet points\n"
                "   - Mention key files/modules when useful\n"
                "   - Include rationale/impact where it is evident\n\n"
                "Example format:\n"
                "```\n"
                "feat: Improve commit context handling\n\n"
                "- Expand git context to include untracked previews\n"
                "- Add staged/unstaged diff stats for better summarization\n"
                "- Compact large diffs by file to preserve coverage\n"
                "- Include recent history snapshots for broader context\n"
                "- Improve truncation strategy to keep head+tail\n"
                "```\n\n"
                f"Git change context:\n{diff_content}\n\n"
                "Return only the commit message in the format above, without "
                "any extra commentary."
            )
            max_output_tokens = 700
        else:
            prompt = (
                "Generate a commit message in English based on the following git "
                "change context.\n"
                "The context may include git status, changed file lists, diff "
                "summaries, untracked file previews, recent git log, and "
                "staged/unstaged diffs.\n\n"
                "The commit message should follow this format:\n"
                "1. First line: A short summary (max 50 characters) in format "
                '"Type: Brief description"\n'
                "2. Blank line\n"
                "3. Detailed description explaining what was changed and why "
                "(2-4 sentences)\n\n"
                "Example format:\n"
                "```\n"
                "feat: Add user authentication\n\n"
                "Implement login and registration functionality with "
                "JWT tokens.\n"
                "Added password hashing using bcrypt for security.\n"
                "Created user model and authentication middleware.\n"
                "```\n\n"
                f"Git change context:\n{diff_content}\n\n"
                "Return only the commit message in the format above, without "
                "any explanations or special characters."
            )
            max_output_tokens = 300

        model_candidates = select_available_models(client)
        last_error = None
        response = None
        response_finish_reason = ""
        selected_commit_message = ""

        # Try candidates in order, fallback automatically on transient issues.
        # For each model, retry with a larger output budget if result looks cut.
        token_attempts = [
            max_output_tokens,
            min(2048, max(max_output_tokens * 2, 900)),
        ]
        for selected_model in model_candidates:
            for output_token_budget in token_attempts:
                try:
                    response = client.models.generate_content(
                        model=selected_model,
                        contents=prompt,
                        config={
                            "temperature": 0.5,
                            "max_output_tokens": output_token_budget,
                        },
                    )
                    commit_text = (getattr(response, "text", "") or "").strip()
                    finish_reason = _extract_finish_reason(response)

                    if not commit_text:
                        response = None
                        continue

                    if (
                        "max" in finish_reason
                        or "length" in finish_reason
                        or _looks_incomplete_message(commit_text)
                    ):
                        # Retry same model with larger budget.
                        selected_commit_message = commit_text
                        response_finish_reason = finish_reason
                        response = None
                        continue

                    selected_commit_message = commit_text
                    response_finish_reason = finish_reason
                    break
                except Exception as model_error:
                    last_error = model_error
                    err_text = str(model_error).lower()
                    # Continue trying next model for quota/rate errors.
                    if any(
                        token in err_text
                        for token in (
                            "resource_exhausted",
                            "quota",
                            "rate",
                            "429",
                            "503",
                            "unavailable",
                            "high demand",
                            "temporarily",
                            "not found",
                            "unsupported",
                        )
                    ):
                        break
                    raise
            if selected_commit_message:
                break

        if not selected_commit_message:
            raise Exception(
                "No usable model available for current API key. "
                f"Last error: {last_error}"
            )

        commit_message = selected_commit_message

        # Clean commit message (remove quotes if present)
        commit_message = commit_message.strip('"').strip("'")

        # Ensure proper format: summary + blank line + description
        lines = commit_message.split("\n")
        if len(lines) > 1:
            # Check if there's already a blank line
            if lines[1].strip() != "":
                # Insert blank line between summary and description
                summary = lines[0]
                description = "\n".join(lines[1:])
                commit_message = f"{summary}\n\n{description}"

        final_message = (
            commit_message if commit_message else "Update code\n\nCode changes"
        )
        # If still clearly max-token limited, add fallback note instead of
        # returning a dangling sentence.
        if (
            response_finish_reason
            and ("max" in response_finish_reason or "length" in response_finish_reason)
            and _looks_incomplete_message(final_message)
        ):
            lines = final_message.splitlines()
            if lines:
                summary = lines[0]
                body = "\n".join(lines[1:]).strip()
                if not body:
                    body = "- Update code changes based on current " "diff context."
                if not body.endswith((".", "!", "?")):
                    body = body + "."
                final_message = (
                    f"{summary}\n\n{body}\n"
                    "- Additional details omitted due to output limits."
                )

        return final_message

    except Exception as e:
        # If error occurs, return default message
        error_msg = str(e)
        if "API_KEY" in error_msg or "api key" in error_msg.lower():
            raise Exception("API key error. Please check GEMINI_API_KEY in .env file")
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            raise Exception("API quota exceeded. Please try again later.")
        else:
            raise Exception(f"Error generating commit message: {error_msg}")
