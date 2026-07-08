"""
github_service.py
Fetches a GitHub repo's code files so the agent can read/understand them.
"""
import os
import base64
from github import Github, GithubException

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".rb", ".php", ".cs", ".html", ".css", ".md", ".json",
    ".yml", ".yaml"
}

# Don't pull huge/irrelevant folders into context
SKIP_DIRS = {"node_modules", ".git", "venv", "__pycache__", "dist", "build", ".next"}

MAX_FILES = 40          # safety cap so we don't blow up context / rate limits
MAX_FILE_CHARS = 20000  # skip absurdly large single files


def _get_client():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not set in .env")
    return Github(token)


def parse_repo_url(repo_url: str) -> str:
    """Turns https://github.com/user/repo(.git) into 'user/repo'."""
    repo_url = repo_url.rstrip("/").removesuffix(".git")
    parts = repo_url.split("github.com/")
    if len(parts) != 2:
        raise ValueError("Invalid GitHub URL. Use format: https://github.com/user/repo")
    return parts[1]


def fetch_repo_files(repo_url: str) -> list[dict]:
    """
    Returns a list of {"path": str, "content": str} for every relevant
    code file in the repo (default branch), skipping binaries/junk dirs.
    """
    client = _get_client()
    repo_name = parse_repo_url(repo_url)

    try:
        repo = client.get_repo(repo_name)
    except GithubException as e:
        raise ValueError(f"Could not access repo '{repo_name}': {e.data.get('message', str(e))}")

    files = []
    contents = repo.get_contents("")  # start at root

    while contents and len(files) < MAX_FILES:
        item = contents.pop(0)

        if item.type == "dir":
            if item.name in SKIP_DIRS:
                continue
            try:
                contents.extend(repo.get_contents(item.path))
            except GithubException:
                continue
            continue

        ext = os.path.splitext(item.name)[1]
        if ext not in CODE_EXTENSIONS:
            continue

        try:
            if item.encoding == "base64":
                raw = base64.b64decode(item.content).decode("utf-8", errors="ignore")
            else:
                raw = item.decoded_content.decode("utf-8", errors="ignore")
        except Exception:
            continue

        if len(raw) > MAX_FILE_CHARS:
            raw = raw[:MAX_FILE_CHARS] + "\n... [truncated]"

        files.append({"path": item.path, "content": raw})

    return files


def get_repo_metadata(repo_url: str) -> dict:
    client = _get_client()
    repo = client.get_repo(parse_repo_url(repo_url))
    return {
        "name": repo.full_name,
        "description": repo.description,
        "language": repo.language,
        "stars": repo.stargazers_count,
        "default_branch": repo.default_branch,
    }