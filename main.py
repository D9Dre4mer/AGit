"""
AGit - Auto Commit GUI Application
Desktop application to automatically commit Git with AI-generated commit messages
"""
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
import threading
import os
from git_handler import (
    check_is_git_repo,
    get_git_status,
    has_changes,
    add_all_changes,
    commit_changes,
    push_changes
)
from gemini_client import generate_commit_message


# Deep Forest Green Color Scheme
COLORS = {
    'bg_primary': '#0d2818',      # Deep forest green background
    'bg_secondary': '#1a4d2e',    # Slightly lighter green
    'bg_input': '#1a3d2a',        # Input field background
    'bg_button': '#2d5a3d',       # Button background
    'bg_button_hover': '#3d6a4d', # Button hover
    'text_primary': '#ffffff',    # White text
    'text_secondary': '#e8f5e9',  # Light green text
    'border': '#2d5a3d',          # Border color
    'success': '#4caf50',         # Success green
    'error': '#f44336',           # Error red
    'warning': '#ff9800'          # Warning orange
}


class AGitApp:
    def __init__(self, root):
        self.root = root
        self.repo_path = tk.StringVar()
        self.commit_message = None  # Store generated commit message
        self.message_generated = False  # Track if message has been generated
        self.repo_path_value = None  # Store validated repo path
        self.setup_window()
        self.create_widgets()
        
    def setup_window(self):
        """Configure main window"""
        self.root.title("AGit - Auto Commit")
        self.root.geometry("500x550")  # Increased height for commit message display
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS['bg_primary'])
        
        # Center window on screen
        self.center_window()
        
    def center_window(self):
        """Center window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
    def create_widgets(self):
        """Create GUI widgets"""
        # Main container with padding
        main_frame = tk.Frame(self.root, bg=COLORS['bg_primary'], padx=30, pady=30)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="AGit - Auto Commit",
            font=('Segoe UI', 18, 'bold'),
            bg=COLORS['bg_primary'],
            fg=COLORS['text_primary']
        )
        title_label.pack(pady=(0, 20))
        
        # Repository Path Section
        repo_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        repo_frame.pack(fill=tk.X, pady=(0, 15))
        
        repo_label = tk.Label(
            repo_frame,
            text="Repository Path:",
            font=('Segoe UI', 10),
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary'],
            anchor='w'
        )
        repo_label.pack(fill=tk.X, pady=(0, 5))
        
        # Input frame with entry and browse button
        input_frame = tk.Frame(repo_frame, bg=COLORS['bg_primary'])
        input_frame.pack(fill=tk.X)
        
        self.repo_entry = tk.Entry(
            input_frame,
            textvariable=self.repo_path,
            font=('Segoe UI', 10),
            bg=COLORS['bg_input'],
            fg=COLORS['text_primary'],
            insertbackground=COLORS['text_primary'],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS['border'],
            highlightcolor=COLORS['bg_button'],
            selectbackground=COLORS['bg_button']
        )
        self.repo_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, ipady=8, padx=(0, 10))
        
        browse_btn = tk.Button(
            input_frame,
            text="Browse",
            font=('Segoe UI', 9),
            bg=COLORS['bg_button'],
            fg=COLORS['text_primary'],
            activebackground=COLORS['bg_button_hover'],
            activeforeground=COLORS['text_primary'],
            relief=tk.FLAT,
            bd=0,
            cursor='hand2',
            command=self.browse_repo,
            padx=15,
            pady=5
        )
        browse_btn.pack(side=tk.RIGHT)
        
        # Push Checkbox
        self.push_var = tk.BooleanVar(value=False)
        checkbox_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        checkbox_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Custom checkbox styling
        self.push_checkbox = tk.Checkbutton(
            checkbox_frame,
            text="Push to remote after commit",
            variable=self.push_var,
            font=('Segoe UI', 10),
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary'],
            activebackground=COLORS['bg_primary'],
            activeforeground=COLORS['text_secondary'],
            selectcolor=COLORS['bg_input'],
            cursor='hand2',
            relief=tk.FLAT
        )
        self.push_checkbox.pack(anchor='w')
        
        # Commit Message Display Section
        message_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        message_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        message_label = tk.Label(
            message_frame,
            text="Commit Message:",
            font=('Segoe UI', 10),
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary'],
            anchor='w'
        )
        message_label.pack(fill=tk.X, pady=(0, 5))
        
        # Text area for commit message (read-only)
        self.message_text = scrolledtext.ScrolledText(
            message_frame,
            height=6,
            font=('Segoe UI', 9),
            bg=COLORS['bg_input'],
            fg=COLORS['text_primary'],
            insertbackground=COLORS['text_primary'],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS['border'],
            wrap=tk.WORD,
            state=tk.DISABLED  # Read-only
        )
        self.message_text.pack(fill=tk.BOTH, expand=True)
        
        # Button frame
        button_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Commit Button (changes text based on state)
        self.commit_button = tk.Button(
            button_frame,
            text="Generate Commit Message",
            font=('Segoe UI', 12, 'bold'),
            bg=COLORS['bg_button'],
            fg=COLORS['text_primary'],
            activebackground=COLORS['bg_button_hover'],
            activeforeground=COLORS['text_primary'],
            relief=tk.FLAT,
            bd=0,
            cursor='hand2',
            command=self.handle_button_click,
            padx=30,
            pady=12
        )
        self.commit_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Cancel/Reset Button
        self.cancel_button = tk.Button(
            button_frame,
            text="Reset",
            font=('Segoe UI', 10),
            bg=COLORS['bg_input'],
            fg=COLORS['text_secondary'],
            activebackground=COLORS['bg_secondary'],
            activeforeground=COLORS['text_primary'],
            relief=tk.FLAT,
            bd=0,
            cursor='hand2',
            command=self.reset_state,
            padx=15,
            pady=12,
            state=tk.DISABLED
        )
        self.cancel_button.pack(side=tk.RIGHT)
        
        # Status Label
        self.status_label = tk.Label(
            main_frame,
            text="Ready",
            font=('Segoe UI', 9),
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary'],
            wraplength=440,
            justify=tk.LEFT
        )
        self.status_label.pack(fill=tk.X)
        
    def browse_repo(self):
        """Open dialog to select repository folder"""
        folder = filedialog.askdirectory(title="Select Git Repository")
        if folder:
            self.repo_path.set(folder)
            self.reset_state()  # Reset when repo path changes
            
    def reset_state(self):
        """Reset to initial state"""
        self.message_generated = False
        self.commit_message = None
        self.repo_path_value = None
        self.commit_button.config(text="Generate Commit Message", bg=COLORS['bg_button'])
        self.cancel_button.config(state=tk.DISABLED)
        self.message_text.config(state=tk.NORMAL)
        self.message_text.delete(1.0, tk.END)
        self.message_text.config(state=tk.DISABLED)
        self.update_status("Ready", COLORS['text_secondary'])
        
    def display_commit_message(self, message: str):
        """Display commit message in text area"""
        self.message_text.config(state=tk.NORMAL)
        self.message_text.delete(1.0, tk.END)
        self.message_text.insert(1.0, message)
        self.message_text.config(state=tk.DISABLED)
        
    def update_status(self, message: str, color: str = None):
        """Update status label - thread-safe"""
        if color is None:
            color = COLORS['text_secondary']
        # Use after() to ensure thread-safe GUI update
        self.root.after(0, lambda: self.status_label.config(text=message, fg=color))
        self.root.update_idletasks()
        
    def set_button_state(self, enabled: bool):
        """Enable/disable button - thread-safe"""
        state = tk.NORMAL if enabled else tk.DISABLED
        bg_color = COLORS['bg_button'] if enabled else COLORS['bg_input']
        # Use after() to ensure thread-safe GUI update
        self.root.after(0, lambda: self._update_button_state(state, bg_color))
        
    def _update_button_state(self, state, bg_color):
        """Helper method to update button state"""
        self.commit_button.config(state=state, bg=bg_color)
        
    def handle_button_click(self):
        """Handle button click - different behavior based on state"""
        if not self.message_generated:
            # Step 1: Generate commit message
            self.start_generate_process()
        else:
            # Step 2: Commit
            self.start_commit_process()
            
    def start_generate_process(self):
        """Start commit message generation in separate thread"""
        self.set_button_state(False)
        self.cancel_button.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.generate_message_process, daemon=True)
        thread.start()
        
    def generate_message_process(self):
        """Generate commit message process"""
        try:
            # Validate repo path
            repo_path = self.repo_path.get().strip()
            if not repo_path:
                self.update_status("Please enter repository path", COLORS['error'])
                self.set_button_state(True)
                return
                
            if not os.path.exists(repo_path):
                self.update_status("Path does not exist", COLORS['error'])
                self.set_button_state(True)
                return
                
            if not check_is_git_repo(repo_path):
                self.update_status("Path is not a Git repository", COLORS['error'])
                self.set_button_state(True)
                return
                
            # Check for changes
            self.update_status("Checking for changes...", COLORS['warning'])
            if not has_changes(repo_path):
                self.update_status("No changes to commit", COLORS['warning'])
                self.set_button_state(True)
                return
                
            # Get git diff
            self.update_status("Getting change information...", COLORS['warning'])
            status_output, diff_output = get_git_status(repo_path)
            
            # Generate commit message from Gemini
            self.update_status("Generating commit message with AI...", COLORS['warning'])
            commit_message = generate_commit_message(diff_output)
            
            # Store values
            self.commit_message = commit_message
            self.repo_path_value = repo_path
            self.message_generated = True
            
            # Display message
            self.root.after(0, lambda: self.display_commit_message(commit_message))
            
            # Update UI
            self.root.after(0, lambda: self.commit_button.config(
                text="Commit",
                bg=COLORS['success']
            ))
            self.root.after(0, lambda: self.cancel_button.config(state=tk.NORMAL))
            
            self.update_status("Commit message generated. Review and click 'Commit' to proceed.", COLORS['success'])
            self.set_button_state(True)
                
        except Exception as e:
            error_msg = str(e)
            self.update_status(f"✗ Error: {error_msg}", COLORS['error'])
            messagebox.showerror("Error", error_msg)
            self.set_button_state(True)
            
    def start_commit_process(self):
        """Start commit process in separate thread"""
        if not self.commit_message or not self.repo_path_value:
            self.update_status("Please generate commit message first", COLORS['error'])
            return
            
        self.set_button_state(False)
        self.cancel_button.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.commit_process, daemon=True)
        thread.start()
        
    def commit_process(self):
        """Main commit process"""
        try:
            # Add changes
            self.update_status("Staging changes...", COLORS['warning'])
            add_all_changes(self.repo_path_value)
            
            # Commit
            self.update_status("Committing...", COLORS['warning'])
            commit_changes(self.repo_path_value, self.commit_message)
            
            # Push if selected
            if self.push_var.get():
                self.update_status("Pushing to remote...", COLORS['warning'])
                push_changes(self.repo_path_value)
                summary = self.commit_message.split('\n')[0]
                self.update_status(f"✓ Successfully committed and pushed!\n{summary}", COLORS['success'])
            else:
                summary = self.commit_message.split('\n')[0]
                self.update_status(f"✓ Successfully committed!\n{summary}", COLORS['success'])
            
            # Reset after successful commit
            self.root.after(2000, self.reset_state)  # Reset after 2 seconds
            self.set_button_state(True)
                
        except Exception as e:
            error_msg = str(e)
            self.update_status(f"✗ Error: {error_msg}", COLORS['error'])
            messagebox.showerror("Error", error_msg)
            self.set_button_state(True)
            self.cancel_button.config(state=tk.NORMAL)


def main():
    """Main function to run the application"""
    root = tk.Tk()
    AGitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
