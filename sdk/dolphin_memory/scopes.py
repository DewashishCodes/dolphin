"""
Memory Scopes
==============
A scope is a memory namespace. Agents use two:

- a project scope, shared by every session working in the same repository
- USER_SCOPE, for preferences that apply across all projects
"""

import hashlib
import os
import re
import subprocess
from typing import Optional

USER_SCOPE = "user:global"


def _git(cwd: str, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _normalize_remote(url: str) -> str:
    """git@github.com:Org/Repo.git and https://github.com/Org/Repo -> github.com/org/repo"""
    url = re.sub(r"^[a-z+]+://", "", url.strip())
    url = re.sub(r"^[^@/]+@", "", url)
    url = url.replace(":", "/", 1) if "/" not in url.split(":", 1)[0] else url
    url = re.sub(r"\.git$", "", url.rstrip("/"))
    return url.lower()


def project_scope(cwd: Optional[str] = None) -> str:
    """
    The scope for the project containing `cwd`.

    Uses the git remote so that clones and worktrees of one repository share
    memory; falls back to the repository root, then the directory itself.
    """
    cwd = os.path.abspath(cwd or os.getcwd())

    root = _git(cwd, "rev-parse", "--show-toplevel")
    # A home directory kept in git (dotfiles) is not the project of everything under it
    if root and _same_path(root, os.path.expanduser("~")):
        root = None

    if root:
        remote = _git(root, "remote", "get-url", "origin")
        if remote:
            return f"project:{_normalize_remote(remote)}"

    root = os.path.normcase(os.path.abspath(root or cwd))
    digest = hashlib.sha1(root.encode("utf-8")).hexdigest()[:12]
    return f"project:{os.path.basename(root) or 'root'}-{digest}"


def resolve_scope(scope: Optional[str], cwd: Optional[str] = None) -> str:
    """Turn a scope argument into a namespace: None -> project, 'user' -> USER_SCOPE."""
    scope = scope or os.environ.get("DOLPHIN_SCOPE")
    if not scope or scope == "project":
        return project_scope(cwd)
    if scope == "user":
        return USER_SCOPE
    return scope
