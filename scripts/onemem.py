#!/usr/bin/env python3
"""
onemem.py — Claude Code hook handler for cross-session memory via PowerMem.

Subcommands:
  load   SessionStart hook: fetch last memory from PowerMem, inject as context
  save   Stop hook: extract transcript context, persist to PowerMem

Config: ~/.oneMem/settings.json  (override with ONEMEM_CONFIG env var)
  {
    "powermem_url": "https://...",  # required
    "api_key": "...",               # required
    "agent_id": "onemem"            # optional, default "onemem"
  }
"""

import json
import os
import subprocess
import sys
from pathlib import Path


CONFIG_PATH = Path.home() / ".oneMem" / "settings.json"


def load_config(path=None):
    """
    Read ~/.oneMem/settings.json (or a custom path for testing).
    The ONEMEM_CONFIG environment variable overrides the default path.
    Returns a dict with keys: powermem_url, api_key, agent_id.
    Returns None if file is missing or required fields are absent.
    """
    config_file = Path(path) if path else Path(os.environ.get("ONEMEM_CONFIG", "") or CONFIG_PATH)
    try:
        with open(config_file) as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not cfg.get("powermem_url") or not cfg.get("api_key"):
        return None

    cfg.setdefault("agent_id", "onemem")
    return cfg


def get_project_id(cwd):
    """
    Return the git remote origin URL as the project identity.
    Falls back to basename(cwd) if not a git repo or no remote configured.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        url = result.stdout.strip()
        if result.returncode == 0 and url:
            return url
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return Path(cwd).name
