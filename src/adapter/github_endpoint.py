"""
Module for finding GitHub repositories matching specific criteria.
"""
import requests
from datetime import datetime, timedelta
import random
import os
from urllib.parse import urlparse

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos"
PAGE_SIZE = 50


def find_repos(language="java", min_size=1000, max_size=None, sample_size=5):
    """
    Finds random GitHub repositories matching the criteria.

    Args:
        language (str): Programming language to filter by (default: "java")
        min_size (int): Minimum size of repositories in KB (default: 1000)
        max_size (int): Maximum size of repositories in KB (default: None)
        sample_size (int): Number of random repositories to return (default: 5)

    Returns:
        list: List of randomly selected repositories matching the criteria
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN environment variable required.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Date: one year ago
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    # Search query with language, push date, and size filter
    if max_size is None:
        query = f"language:{language} pushed:>{one_year_ago} size:>{min_size}"
    else:
        query = f"language:{language} pushed:>{one_year_ago} size:{min_size}..{max_size}"
    url = f"{GITHUB_SEARCH_URL}?q={query}&sort=stars&order=desc&per_page={PAGE_SIZE}"

    response = requests.get(url, headers=headers)
    # Error handling
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.status_code} - {response.text}")

    data = response.json()
    repos = data.get("items", [])
    if len(repos) < sample_size:
        print(f"Not enough repositories found matching your filters. Found {len(repos)} repos.")
        return [(repo["full_name"], repo["clone_url"], repo["default_branch"], repo["size"]) for repo in repos]
    # Return list with full name, url, default branch and size in KB
    selected = random.sample(repos, sample_size)
    return [(repo["full_name"], repo["clone_url"], repo["default_branch"], repo["size"]) for repo in selected]


def get_repo_info(repo_url):
    """
    Get basic repository information (default branch only) from GitHub API.

    Args:
        repo_url (str): URL of the GitHub repository (HTTPS or SSH)

    Returns:
        str or None: default_branch or None on error
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN environment variable required.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Extract owner and repo name from URL
    owner, repo = _parse_github_url(repo_url)
    if not owner or not repo:
        return None

    # Get repository info from GitHub API
    api_url = f"{GITHUB_REPO_URL}/{owner}/{repo}"

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        repo_data = response.json()

        default_branch = repo_data.get('default_branch', 'main')
        return default_branch

    except requests.RequestException as e:
        print(f"Error fetching repository info: {e}")
        return None


def get_repo_sizes(repo_url):
    """
    Get repository sizes (net size and Java size) from GitHub API.

    Args:
        repo_url (str): URL of the GitHub repository

    Returns:
        tuple: (net_size_kb, java_size_kb) or (None, None) on error
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set, cannot get repository sizes")
        return None, None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Extract owner and repo name from URL
    owner, repo = _parse_github_url(repo_url)
    if not owner or not repo:
        return None, None

    try:
        # Get repository info from GitHub API
        repo_api_url = f"{GITHUB_REPO_URL}/{owner}/{repo}"
        repo_response = requests.get(repo_api_url, headers=headers)
        repo_response.raise_for_status()
        repo_data = repo_response.json()

        net_size = repo_data.get('size', 0)

        # Get languages from GitHub API
        languages_api_url = f"{GITHUB_REPO_URL}/{owner}/{repo}/languages"
        languages_response = requests.get(languages_api_url, headers=headers)
        languages_response.raise_for_status()
        languages = languages_response.json()

        # Extract Java size and convert to KB
        java_bytes = languages.get('Java', 0)
        java_size = java_bytes // 1024 if java_bytes > 0 else None  # Convert to KB

        return net_size, java_size

    except requests.RequestException as e:
        print(f"Error fetching repository sizes for {owner}/{repo}: {e}")
        return None, None


def _parse_github_url(repo_url):
    """
    Parse GitHub URL to extract owner and repository name.

    Args:
        repo_url (str): GitHub repository URL

    Returns:
        tuple: (owner, repo) or (None, None) on error
    """
    parsed_url = urlparse(repo_url)
    path_parts = parsed_url.path.strip('/').split('/')

    # Handle different URL formats
    if 'github.com' in parsed_url.netloc:
        # Handle HTTPS URLs
        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
            if repo.endswith('.git'):
                repo = repo[:-4]
        else:
            print(f"Error: Could not parse GitHub URL: {repo_url}")
            return None, None
    elif 'git@github.com' in repo_url:
        # Handle SSH URLs like git@github.com:owner/repo.git
        path = repo_url.split('git@github.com:')[1]
        owner, repo = path.split('/')
        if repo.endswith('.git'):
            repo = repo[:-4]
    else:
        print(f"Error: Not a GitHub URL: {repo_url}")
        return None, None

    return owner, repo


# Example usage:
if __name__ == "__main__":
    # Test repository info retrieval
    branch = get_repo_info("https://github.com/anthropic/claude-api")
    print(f"Default branch: {branch}")

    # Test size retrieval
    net_size, java_size = get_repo_sizes("https://github.com/anthropic/claude-api")
    print(f"Net size: {net_size} KB, Java size: {java_size} KB")

    # Test find repos
    repos = find_repos(language="python", min_size=2000, sample_size=3)
    for repo in repos:
        print(f"Name: {repo[0]}, URL: {repo[1]}, Branch: {repo[2]}, Size: {repo[3]} KB")