"""
Git Handler Module
Handles Git command execution
"""
import subprocess
import os
from pathlib import Path

# Set environment to use UTF-8 encoding for git commands
GIT_ENV = os.environ.copy()
GIT_ENV['PYTHONIOENCODING'] = 'utf-8'
# Force git to use UTF-8
GIT_ENV['LANG'] = 'en_US.UTF-8'
GIT_ENV['LC_ALL'] = 'en_US.UTF-8'


def check_is_git_repo(repo_path: str) -> bool:
    """
    Check if the path is a Git repository
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if it's a git repo, False otherwise
    """
    git_dir = Path(repo_path) / '.git'
    return git_dir.exists() and git_dir.is_dir()


def get_git_status(repo_path: str) -> tuple[str, str]:
    """
    Get git status and diff of the repository
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Tuple (status_output, diff_output)
    """
    try:
        # Get git status
        status_result = subprocess.run(
            ['git', 'status', '--short'],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid characters instead of failing
            env=GIT_ENV,
            check=False
        )
        
        # Get git diff
        diff_result = subprocess.run(
            ['git', 'diff'],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=GIT_ENV,
            check=False
        )
        
        # Get diff of staged files
        diff_staged_result = subprocess.run(
            ['git', 'diff', '--cached'],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=GIT_ENV,
            check=False
        )
        
        status_output = status_result.stdout.strip()
        diff_output = (diff_result.stdout + diff_staged_result.stdout).strip()
        
        return status_output, diff_output
    except Exception as e:
        raise Exception(f"Error getting git status: {str(e)}")


def has_changes(repo_path: str) -> bool:
    """
    Check if there are any uncommitted changes
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if there are changes, False otherwise
    """
    try:
        status_output, _ = get_git_status(repo_path)
        return len(status_output) > 0
    except Exception:
        return False


def add_all_changes(repo_path: str) -> bool:
    """
    Run git add . to add all changes to staging area
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if successful, False if error
    """
    try:
        # Use list arguments to prevent shell injection
        result = subprocess.run(
            ['git', 'add', '.'],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=GIT_ENV,
            check=True,
            timeout=30  # 30 second timeout
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
    """
    Run git commit with provided message
    
    Args:
        repo_path: Path to repository
        message: Commit message
        
    Returns:
        True if successful
    """
    try:
        # Escape commit message to prevent injection
        # Use list arguments, message passed directly
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=GIT_ENV,
            check=True,
            timeout=30  # 30 second timeout
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
    """
    Run git push to push commits to remote
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if successful
    """
    try:
        # Check if remote exists
        remote_result = subprocess.run(
            ['git', 'remote'],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=GIT_ENV,
            check=False
        )
        
        if not remote_result.stdout.strip():
            raise Exception("Repository has no remote configured")
        
        # Push to remote
        subprocess.run(
            ['git', 'push'],
            cwd=repo_path,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=GIT_ENV,
            check=True,
            timeout=120  # 2 minute timeout for push (may take time)
        )
        return True
    except subprocess.TimeoutExpired:
        raise Exception("git push command timed out")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else e.stdout.strip()
        raise Exception(f"Error pushing: {error_msg}")
    except Exception as e:
        raise Exception(f"Error: {str(e)}")
