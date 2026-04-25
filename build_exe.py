"""
Build script to create executable file from Python application
"""

import PyInstaller.__main__
import importlib.util
import os
import shutil
import stat
import time
import sys


def _require_module(module_name: str, install_hint: str) -> None:
    """
    Fail fast if a required module is missing in the build environment.
    """
    if importlib.util.find_spec(module_name) is None:
        python_exe = sys.executable
        raise RuntimeError(
            "Missing dependency in build environment.\n\n"
            f"- Module: {module_name}\n"
            f"- Python: {python_exe}\n\n"
            "Fix (run exactly with this Python):\n"
            f'  "{python_exe}" -m pip install -r requirements.txt\n'
            f'  "{python_exe}" -m pip install -r requirements-dev.txt\n\n'
            f"Hint: {install_hint}"
        )


def _ensure_ico(png_path: str, ico_path: str) -> str:
    """
    Ensure an .ico exists for PyInstaller --icon.

    PyInstaller expects a .ico for the EXE file icon on Windows.
    """
    if os.path.exists(ico_path):
        return ico_path

    try:
        from PIL import Image  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Pillow is required to generate AGIT.ico. "
            "Run: pip install -r requirements-dev.txt"
        ) from e

    if not os.path.exists(png_path):
        raise FileNotFoundError(
            f"Logo not found at '{png_path}'. Expected logo/AGIT.png"
        )

    img = Image.open(png_path)
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")

    os.makedirs(os.path.dirname(ico_path) or ".", exist_ok=True)
    img.save(
        ico_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    return ico_path


def _rmtree_onerror(func, path, exc_info):
    """
    Best-effort handler for shutil.rmtree on Windows.
    Clears read-only bit and retries the failed operation.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass
    func(path)


def _safe_rmtree(path: str) -> None:
    """
    Remove a directory tree with retries.
    If it remains locked (WinError 5), rename it and continue.
    """
    if not os.path.exists(path):
        return

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            shutil.rmtree(path, onerror=_rmtree_onerror)
            return
        except PermissionError as e:
            last_exc = e
            time.sleep(0.6 * (attempt + 1))

    ts = time.strftime("%Y%m%d-%H%M%S")
    try:
        os.rename(path, f"{path}_old_{ts}")
        return
    except Exception as e:
        last_exc = e

    raise last_exc  # type: ignore[misc]


def build_exe():
    """Build executable file using PyInstaller"""

    # Remove old build and dist directories if they exist
    _safe_rmtree("build")
    _safe_rmtree("dist")

    # Preflight: make sure deps exist in the build environment.
    _require_module("PIL", "pip install -r requirements-dev.txt")
    _require_module("google.genai", "pip install -r requirements.txt")

    logo_png = os.path.join("logo", "AGIT.png")
    logo_ico = os.path.join("logo", "AGIT.ico")
    _ensure_ico(logo_png, logo_ico)
    logo_ico_abs = os.path.abspath(logo_ico)

    # PyInstaller arguments
    args = [
        "main.py",  # Main script
        "--name=AGit",  # Executable file name
        "--onefile",  # Create single exe file
        "--windowed",  # Don't show console window
        f"--icon={logo_ico_abs}",  # EXE file icon (Explorer)
        "--clean",  # Clean old cache
        "--noconfirm",  # Don't ask for confirmation
        "--add-data=.env.example;.",  # Include .env.example
        "--add-data=logo/AGIT.png;logo",  # Include app logo
        "--add-data=logo/AGIT.ico;logo",  # Include ico (optional)
        # Keep Gemini SDK bundleable in onefile:
        "--hidden-import=google.genai",
        "--collect-all=google.genai",
        "--collect-submodules=google.genai",
    ]

    # Run PyInstaller
    PyInstaller.__main__.run(args)

    exe_path = os.path.abspath(os.path.join("dist", "AGit.exe"))

    print("\n" + "=" * 50)
    print("Build completed!")
    print("=" * 50)
    print(f"Executable file created at: {exe_path}")
    print("\nNote:")
    print("- Copy .env.example file and rename it to .env")
    print("- Fill in GEMINI_API_KEY in the .env file")
    print("- Place .env file in the same directory as AGit.exe")
    print("=" * 50)


if __name__ == "__main__":
    build_exe()
