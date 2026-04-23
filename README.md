# AGit - AI-Powered Git Commit Assistant

AGit is a lightweight desktop GUI app that generates smart commit messages with Gemini API and helps you commit in a clean 2-step workflow.

## Highlights

- Clean deep-forest green UI inspired by GitHub Desktop.
- Two-step commit flow:
  - **Step 1:** Generate and preview commit message.
  - **Step 2:** Confirm and run commit.
- Multi-line commit message format:
  - Summary line
  - Blank line
  - Detailed description/body
- Optional `git push` after commit.
- Dynamic model selection from API at runtime (no fixed model hardcoding).
- Automatic fallback to the next available model on quota/rate errors.
- Windows executable build support via PyInstaller.

## Requirements

- Windows 10/11
- Git installed and available in PATH
- Python 3.11+ (for source run)
- A valid Gemini API key

Get API key and docs:
- [Gemini API Docs](https://ai.google.dev/gemini-api/docs)

## Environment Setup

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

## Run from Source

1. Clone the repository:

```bash
git clone <repository-url>
cd AGit
```

2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. Run the app:

```bash
python main.py
```

## Build EXE

1. Install build dependencies:

```bash
pip install -r requirements-dev.txt
```

2. Build executable:

```bash
python build_exe.py
```

3. Output path:

```text
dist/AGit.exe
```

## How to Use

1. Enter repository path (or click **Browse**).
2. Optionally check **Push to remote after commit**.
3. Click **Generate Commit Message**.
4. Review the generated message in the GUI.
5. Click **Commit** to execute.

## Model Selection Strategy

AGit selects models dynamically from the API response each run:

- Calls `models.list()` using your current API key.
- Filters for usable generation models.
- Prioritizes lower-cost candidates using model metadata.
- Falls back automatically if a selected model fails due to quota/rate limits.

## Troubleshooting

### `GEMINI_API_KEY not found`

- Ensure `.env` is in the project/app directory.
- Ensure key format is correct:
  - `GEMINI_API_KEY=...`

### `RESOURCE_EXHAUSTED` / `429`

- Your key is valid, but current quota/rate limit is exhausted.
- Check usage and limits in Google AI Studio / project quota settings.

### Not a Git repository

- The selected folder must contain a `.git` directory.

### Push failed

- Verify remote setup with:
  - `git remote -v`
- Ensure your Git credentials and permissions are valid.

## Project Structure

```text
AGit/
├── main.py
├── git_handler.py
├── gemini_client.py
├── build_exe.py
├── AGit.spec
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

## License

MIT License. See `LICENSE`.
