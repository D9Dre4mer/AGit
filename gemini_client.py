"""
Gemini Client Module
Integrates with Google Gemini API to automatically generate commit messages
"""
import os
from dotenv import load_dotenv
from google.genai import Client

# Load environment variables
load_dotenv()

# Timeout for API requests (30 seconds)
API_TIMEOUT = 30


def initialize_gemini():
    """
    Initialize Gemini API client
    
    Returns:
        Client instance
    """
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        raise Exception("GEMINI_API_KEY not found in .env file")
    
    if api_key == 'your_api_key_here':
        raise Exception("Please configure GEMINI_API_KEY in .env file")
    
    try:
        client = Client(api_key=api_key)
        return client
    except Exception as e:
        raise Exception(f"Error initializing Gemini API: {str(e)}")


def generate_commit_message(diff_content: str) -> str:
    """
    Generate commit message from git diff using Gemini API
    
    Args:
        diff_content: Git diff content
        
    Returns:
        AI-generated commit message
    """
    if not diff_content or not diff_content.strip():
        return "Update code"
    
    try:
        client = initialize_gemini()
        
        # Limit diff length to avoid exceeding token limit
        max_diff_length = 50000  # ~50k characters
        if len(diff_content) > max_diff_length:
            diff_content = diff_content[:max_diff_length] + "\n... (diff truncated due to length)"
        
        prompt = f"""Generate a commit message in English based on the following git diff changes.

The commit message should follow this format:
1. First line: A short summary (max 50 characters) in format "Type: Brief description"
2. Blank line
3. Detailed description explaining what was changed and why (2-4 sentences)

Example format:
```
feat: Add user authentication

Implement login and registration functionality with JWT tokens.
Added password hashing using bcrypt for security.
Created user model and authentication middleware.
```

Git diff:
{diff_content}

Return only the commit message in the format above, without any explanations or special characters."""

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
            raise Exception("API key error. Please check GEMINI_API_KEY in .env file")
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            raise Exception("API quota exceeded. Please try again later.")
        else:
            raise Exception(f"Error generating commit message: {error_msg}")
