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
    if getattr(sys, 'frozen', False):
        try:
            candidates.append(Path(sys.executable).resolve().parent / '.env')
        except Exception:
            pass

    # Source run: alongside this module.
    try:
        candidates.append(Path(__file__).resolve().parent / '.env')
    except Exception:
        pass

    # As a last resort, current working directory.
    candidates.append(Path.cwd() / '.env')

    env_path = next(
        (p for p in candidates if p.exists() and p.is_file()),
        None,
    )
    if not env_path:
        return

    try:
        raw_text = env_path.read_text(
            encoding='utf-8',
            errors='replace',
        )
        for raw in raw_text.splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
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
    api_key = os.getenv('GEMINI_API_KEY')

    if not api_key:
        raise Exception("GEMINI_API_KEY not found in .env file")

    if api_key == 'your_api_key_here':
        raise Exception("Please configure GEMINI_API_KEY in .env file")

    try:
        # Lazy import so the GUI can still start even if dependencies are missing.
        from google.genai import Client  # type: ignore
        return Client(api_key=api_key)
    except ModuleNotFoundError as e:
        raise Exception(
            "Missing dependency: google-genai. "
            "Please install requirements and rebuild the executable."
        ) from e
    except Exception as e:
        raise Exception(f"Error initializing Gemini API: {str(e)}")


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

        # Limit input length to avoid exceeding model context.
        # Prefer keeping both start and end rather than truncating only the start.
        max_input_length = 120000  # ~120k characters
        if len(diff_content) > max_input_length:
            head_len = int(max_input_length * 0.7)
            tail_len = max_input_length - head_len
            head = diff_content[:head_len].rstrip()
            tail = diff_content[-tail_len:].lstrip()
            diff_content = (
                f"{head}\n"
                "... (context truncated due to length) ...\n"
                f"{tail}"
            )

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
            "Implement login and registration functionality with JWT tokens.\n"
            "Added password hashing using bcrypt for security.\n"
            "Created user model and authentication middleware.\n"
            "```\n\n"
            f"Git diff:\n{diff_content}\n\n"
            "Return only the commit message in the format above, without any "
            "explanations or special characters."
        )

        # Generate content using new SDK
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config={
                'temperature': 0.7,
                'max_output_tokens': 300,  # Increased for description
            }
        )
        
        commit_message = response.text.strip()

        # Clean commit message (remove quotes if present)
        commit_message = commit_message.strip('"').strip("'")

        # Ensure proper format: summary + blank line + description
        lines = commit_message.split('\n')
        if len(lines) > 1:
            # Check if there's already a blank line
            if lines[1].strip() != '':
                # Insert blank line between summary and description
                summary = lines[0]
                description = '\n'.join(lines[1:])
                commit_message = f"{summary}\n\n{description}"
        
        return commit_message if commit_message else "Update code\n\nCode changes"

    except Exception as e:
        # If error occurs, return default message
        error_msg = str(e)
        if "API_KEY" in error_msg or "api key" in error_msg.lower():
            raise Exception(
                "API key error. Please check GEMINI_API_KEY in .env file"
            )
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            raise Exception("API quota exceeded. Please try again later.")
        else:
            raise Exception(f"Error generating commit message: {error_msg}")
