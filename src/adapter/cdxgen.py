import json
import time
import threading
import subprocess
import sys

from util import delete_file, delete_directory, clone_repo, spinner_animation

# --- Constants ---
CBOM_FILE = "cbom.json"
CBOM_MAP_FILE = "cbom.json.map"
CBOM_CMD_TYPE = "java"


def generate_cbom_from_file(target_path, output_file=CBOM_FILE):
    """
    Generates a CBOM for a specified directory.

    Args:
        target_path (str): Path to the directory.
        output_file (str): Name of the output file.

    Returns:
        tuple[bool, float | None]: (True, duration) on success, (False, None) on error.
    """
    start = time.perf_counter()
    stop_animation = threading.Event()
    animation_thread = threading.Thread(target=spinner_animation, args=(stop_animation,))
    animation_thread.start()

    try:
        cmd = ['cbom', '-t', 'java', '-o', output_file, target_path]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = time.perf_counter() - start
        stop_animation.set()
        animation_thread.join()
        print("CBOM generation successful.")
        return True, duration
    except subprocess.CalledProcessError as e:
        stop_animation.set()
        animation_thread.join()
        print(f"\nError generating CBOM: {e.stderr}", file=sys.stderr)
        return False, None
    except Exception as e:
        stop_animation.set()
        animation_thread.join()
        print(f"\nUnexpected error during CBOM generation: {str(e)}", file=sys.stderr)
        return False, None


def generate_cbom(github_url, branch="main", output_path="cbom.json"):
    """
    Clones a GitHub repo, generates a CBOM from it, deletes the repo, and returns the CBOM as a dictionary.

    Args:
        github_url (str): URL of the GitHub repository.
        branch (str, optional): Branch to clone. Defaults to "main".
        output_path (str, optional): Path to store the CBOM file.

    Returns:
        tuple[dict | None, float | None]: (CBOM data dict, duration) or (None, None) on failure.
    """
    repo_dir = clone_repo(github_url, branch)

    if not repo_dir:
        print("Cloning failed.", file=sys.stderr)
        return None, None

    success, duration = generate_cbom_from_file(repo_dir, output_path)
    if not success:
        print("CBOM generation failed.", file=sys.stderr)
        delete_directory(repo_dir)
        return None, None

    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            cbom_data = json.load(f)
            print(f"CBOM successfully generated in {duration:.2f} seconds.")
    except Exception as e:
        print(f"Error reading CBOM file: {str(e)}", file=sys.stderr)
        cbom_data = None

    delete_directory(repo_dir)
    delete_file(output_path)
    return cbom_data, duration