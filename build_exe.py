"""
Build script to create executable file from Python application
"""
import PyInstaller.__main__
import os
import shutil
from pathlib import Path

def build_exe():
    """Build executable file using PyInstaller"""
    
    # Remove old build and dist directories if they exist
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    
    # PyInstaller arguments
    args = [
        'main.py',                          # Main script
        '--name=AGit',                      # Executable file name
        '--onefile',                        # Create single exe file
        '--windowed',                       # Don't show console window
        '--clean',                          # Clean old cache
        '--noconfirm',                      # Don't ask for confirmation
        '--add-data=.env.example;.',        # Include .env.example
        '--hidden-import=dotenv',           # Ensure dotenv import
        '--hidden-import=google.genai',     # Ensure google.genai import
        '--hidden-import=google',           # Ensure google package import
        '--collect-all=google.genai',       # Collect all from google.genai
        '--collect-all=google',             # Collect all from google
    ]
    
    # Run PyInstaller
    PyInstaller.__main__.run(args)
    
    print("\n" + "="*50)
    print("Build completed!")
    print("="*50)
    print(f"Executable file created at: {os.path.abspath('dist/AGit.exe')}")
    print("\nNote:")
    print("- Copy .env.example file and rename it to .env")
    print("- Fill in GEMINI_API_KEY in the .env file")
    print("- Place .env file in the same directory as AGit.exe")
    print("="*50)

if __name__ == "__main__":
    build_exe()
