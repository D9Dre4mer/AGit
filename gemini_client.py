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


def _list_generation_models(
    client,
) -> list[tuple[str, int, int]]:
    """
    List general-purpose text models with API-reported (input, output) limits.

    Returns tuples of (model_name, input_token_limit, output_token_limit),
    sorted by **largest input context first** so we can size the prompt to
    the most capable model; all following models in the list can use the same
    prompt.
    """
    try:
        raw: list[tuple[int, int, str]] = []
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

            input_limit = int(getattr(model, "input_token_limit", 0) or 0)
            output_limit = int(getattr(model, "output_token_limit", 0) or 0)
            if input_limit <= 0:
                input_limit = 1_048_576
            if output_limit <= 0:
                output_limit = 8192
            raw.append((input_limit, output_limit, normalized))

        # Largest context first, then by output, then by name.
        raw.sort(key=lambda x: (-x[0], -x[1], x[2]))
        seen: set[str] = set()
        out: list[tuple[str, int, int]] = []
        for inp, outp, mname in raw:
            if mname in seen:
                continue
            seen.add(mname)
            out.append((mname, inp, outp))
        return out
    except Exception:
        return []


def select_available_models(client) -> list[str]:
    """
    Query available models from API and return usable generation models.
    This is fully dynamic per run and uses API-returned metadata only.
    """
    return [m[0] for m in _list_generation_models(client)]


# Margin between reported input_token_limit and count_tokens: packing,
# system templates, and tiny tokenizer drift.
_INPUT_TOKEN_SAFETY_MARGIN = 512


def _head_tail_from_body(text: str, keep: int) -> str:
    """
    Keep at most `keep` characters from the body using a 70/30 head/tail
    split and a clear marker. If `keep` covers the full string, return it
    without a marker. Assumes `keep < len(text)` when a marker is used.
    """
    n = len(text)
    if keep <= 0:
        return ""
    if n <= keep:
        return text
    head = int(keep * 0.7)
    tail = keep - head
    mark = "\n... (context truncated due to length) ...\n"
    return text[:head].rstrip() + mark + text[-tail:].lstrip()


def _read_total_tokens(count_response):
    if count_response is None:
        return None
    n = getattr(count_response, "total_tokens", None)
    if n is not None:
        return int(n)
    if isinstance(count_response, dict):
        for key in ("total_tokens", "totalTokens"):
            if key in count_response and count_response[key] is not None:
                return int(count_response[key])
    return None


def _count_prompt_tokens(client, model, text: str):
    try:
        resp = client.models.count_tokens(model=model, contents=text)
        return _read_total_tokens(resp)
    except Exception:
        return None


def _fit_diff_to_input_tokens(
    client,
    model: str,
    prefix: str,
    suffix: str,
    body: str,
    max_input_tokens: int,
) -> tuple[str, bool]:
    """
    Shrink `body` only (head+tail) until prefix+body+suffix is within
    `max_input_tokens` according to the API tokenizer for `model`.
    """
    if max_input_tokens < 1:
        max_input_tokens = 1

    full = prefix + body + suffix
    t_full = _count_prompt_tokens(client, model, full)
    if t_full is not None and t_full <= max_input_tokens:
        return body, False

    if t_full is None:
        # count_tokens failed: use a conservative char cap (~3 chars/token).
        max_chars = max(4096, max_input_tokens * 3)
        if len(body) <= max_chars:
            return body, False
        return _head_tail_from_body(body, max_chars), True

    empty = prefix + suffix
    t_empty = _count_prompt_tokens(client, model, empty)
    if t_empty is not None and t_empty > max_input_tokens:
        return body[: max(1, len(body) // 2)], True

    n = len(body)
    if n == 0:
        return "", False

    # Full prompt already over budget. Search the largest "keep" in
    # [0, n - 1] using a head+tail+marker form only (no k == n), so token
    # count is monotone increasing in k. (k == n is full text without a marker
    # and is already known not to fit.)
    lo, hi = 0, n - 1
    best_keep = 0
    for _ in range(40):
        if lo > hi:
            break
        mid = (lo + hi + 1) // 2
        cand = _head_tail_from_body(body, mid)
        t_c = _count_prompt_tokens(client, model, prefix + cand + suffix)
        if t_c is None:
            hi = mid - 1
            continue
        if t_c <= max_input_tokens:
            best_keep = mid
            lo = mid + 1
        else:
            hi = mid - 1

    out = _head_tail_from_body(body, best_keep)
    return out, True


def _build_commit_prompt_prefix_suffix(
    use_detailed: bool,
) -> tuple[str, str]:
    """
    Return (prefix, suffix) with the diff text inserted as prefix+body+suffix.
    Must stay in sync with the instructions sent to the model.
    """
    if use_detailed:
        prefix = (
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
            "Git change context:\n"
        )
        suffix = (
            "\n\nReturn only the commit message in the format above, without "
            "any extra commentary."
        )
    else:
        prefix = (
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
            "Git change context:\n"
        )
        suffix = (
            "\n\nReturn only the commit message in the format above, without "
            "any explanations or special characters."
        )
    return prefix, suffix


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

        models = _list_generation_models(client)
        if not models:
            raise Exception(
                "No usable model available for current API key. "
                "No generation models found for this key."
            )

        # Size the diff using the same tokenizer the API uses (count_tokens) on
        # the model with the largest input budget (so we keep as many chars as
        # that model can actually take).
        reference_model = models[0][0]
        largest_in = max(1, int(models[0][1]))
        max_input_tokens = max(1, largest_in - _INPUT_TOKEN_SAFETY_MARGIN)
        raw_diff = diff_content
        use_detailed = _is_truncated_or_compacted(raw_diff)
        pfx, sfx = _build_commit_prompt_prefix_suffix(use_detailed)
        body, was_trunc = _fit_diff_to_input_tokens(
            client,
            reference_model,
            pfx,
            sfx,
            raw_diff,
            max_input_tokens,
        )
        if was_trunc and not use_detailed:
            use_detailed = True
            pfx, sfx = _build_commit_prompt_prefix_suffix(True)
            body, was_trunc = _fit_diff_to_input_tokens(
                client,
                reference_model,
                pfx,
                sfx,
                raw_diff,
                max_input_tokens,
            )
        prompt = pfx + body + sfx

        last_error = None
        response = None
        response_finish_reason = ""
        selected_commit_message = ""

        # Each call uses that model's full output_token_limit (no app-side cap).
        for selected_model, _in_lim, out_lim in models:
            out_cap = int(out_lim) if int(out_lim) > 0 else 8192
            try:
                response = client.models.generate_content(
                    model=selected_model,
                    contents=prompt,
                    config={
                        "temperature": 0.5,
                        "max_output_tokens": out_cap,
                    },
                )
                commit_text = (getattr(response, "text", "") or "").strip()
                finish_reason = _extract_finish_reason(response)

                if not commit_text:
                    continue

                if (
                    "max" in finish_reason
                    or "length" in finish_reason
                    or _looks_incomplete_message(commit_text)
                ):
                    # Keep partial; try next model in case a larger output cap
                    # or different model completes the message.
                    selected_commit_message = commit_text
                    response_finish_reason = finish_reason
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
                    continue
                raise

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
