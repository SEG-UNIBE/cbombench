import os
import shutil
import subprocess
import sys
import re
import time
from tqdm import tqdm
import threading

# --- Constants for Spinner Animation ---
ANIMATION_INTERVAL = 0.2  # Seconds between each frame update
ANIMATION_FRAMES = [
    "⠋", "⠙", "⠹", "⠸", "⠼",
    "⠴", "⠦", "⠧", "⠇", "⠏"
]  # Braille spinner characters for a smooth animation


def check_git_installed():
    """
    Checks if Git is installed and accessible in the system's PATH.

    Returns:
        bool: True if Git is found, False otherwise.
    """
    if shutil.which("git") is None:
        print("Error: 'git' is not installed or not found in your system's PATH.", file=sys.stderr)
        return False
    return True


def clone_repo(github_url, branch="main", target_dir="repo"):
    """
    Clones a GitHub repository with detailed progress bars for different clone stages.

    This function uses `subprocess` to run the 'git clone' command and captures
    its stderr stream to parse progress information, which is then displayed
    using `tqdm` progress bars.

    Args:
        github_url (str): The HTTPS or SSH URL of the GitHub repository.
        branch (str): The name of the branch to clone. Defaults to "main".
        target_dir (str): The local directory to clone the repository into.
                          This directory will be deleted if it already exists.

    Returns:
        Optional[str]: The absolute path to the cloned repository on success,
                       or None if an error occurs.
    """
    if not check_git_installed():
        return None

    print(f"Starting clone: {github_url} (branch: {branch})")
    try:
        # Clean up the target directory before cloning
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        clone_cmd = [
            "git", "clone", "--progress", "-b", branch, github_url, target_dir
        ]

        # Start the git process, redirecting stderr to stdout to capture all output
        process = subprocess.Popen(
            clone_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Capture progress info from stderr
            text=True,
            bufsize=1  # Line-buffered
        )

        # Regex patterns to parse progress percentages from git's output
        patterns = {
            "Counting": re.compile(r"Counting objects:\s+(\d+)%"),
            "Compressing": re.compile(r"Compressing objects:\s+(\d+)%"),
            "Receiving": re.compile(r"Receiving objects:\s+(\d+)%"),
            "Resolving": re.compile(r"Resolving deltas:\s+(\d+)%"),
            "Updating files": re.compile(r"Updating files:\s+(\d+)%")
        }
        progress_bars = {key: None for key in patterns}

        # Read git's output line by line
        for line in process.stdout:
            line = line.strip()
            matched = False
            for key, pattern in patterns.items():
                match = pattern.search(line)
                if match:
                    percent = int(match.group(1))
                    bar = progress_bars.get(key)

                    # Create a new progress bar if it's the first time we see this stage
                    if bar is None:
                        bar = tqdm(total=100, desc=key.ljust(12), leave=False)
                        progress_bars[key] = bar

                    # Update the progress bar to the new percentage
                    bar.update(percent - bar.n)
                    matched = True
                    break

            # If the line didn't match any progress pattern, print it directly
            if not matched and line:
                print(line)

        process.wait()

        # Ensure all progress bars are closed and show 100%
        for bar in progress_bars.values():
            if bar:
                bar.update(100 - bar.n)
                bar.close()

        if process.returncode != 0:
            print(f"Error: Git clone failed with return code {process.returncode}.", file=sys.stderr)
            return None

        print("\nClone completed successfully!")
        return os.path.abspath(target_dir)

    except Exception as e:
        print(f"An unexpected error occurred during clone: {e}", file=sys.stderr)
        return None


def delete_file(file_path):
    """
    Deletes a single file from the filesystem.

    Args:
        file_path (str): The path to the file to be deleted.

    Returns:
        bool: True if the file was deleted successfully, False otherwise.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"File deleted: {file_path}")
            return True
        else:
            # It's not an error if the file is already gone
            return True
    except OSError as e:
        print(f"Error deleting file {file_path}: {e}", file=sys.stderr)
        return False


def delete_directory(path):
    """
    Deletes a directory and all its contents recursively.

    Args:
        path (str): The path to the directory to be deleted.

    Returns:
        bool: True if the directory was deleted successfully, False otherwise.
    """
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"Directory deleted: {path}")
            return True
        else:
            # It's not an error if the directory is already gone
            return True
    except OSError as e:
        print(f"Error deleting directory {path}: {e}", file=sys.stderr)
        return False


def spinner_animation(stop_event):
    """
    Displays a command-line spinner animation in a separate thread.

    The animation continues until the `stop_event` is set from another thread.

    Args:
        stop_event (threading.Event): An event object that signals the
                                      spinner to stop when set.
    """
    i = 0
    # The loop continues as long as the event is not set
    while not stop_event.is_set():
        # Cycle through the animation frames
        frame = ANIMATION_FRAMES[i % len(ANIMATION_FRAMES)]
        # Print the spinner frame, using carriage return to overwrite the line
        print(f"\rScan in progress... {frame}", end="", flush=True)
        i += 1
        time.sleep(ANIMATION_INTERVAL)

    # Clean up the line after the spinner stops
    print("\rScan completed!        ", flush=True)