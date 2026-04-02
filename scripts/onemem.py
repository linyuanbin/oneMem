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


def extract_context_from_transcript(transcript_path, max_messages=10, max_chars=8000):
    """
    Read a Claude Code transcript.jsonl and extract the last max_messages
    assistant text blocks. Returns concatenated text capped at max_chars.
    Returns empty string on any error.
    """
    try:
        with open(transcript_path) as f:
            raw_lines = f.readlines()
    except (FileNotFoundError, OSError):
        return ""

    assistant_texts = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("role") != "assistant":
            continue
        content = entry.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        assistant_texts.append(text)
        elif isinstance(content, str) and content.strip():
            assistant_texts.append(content.strip())

    last_messages = assistant_texts[-max_messages:]
    combined = "\n---\n".join(last_messages)
    return combined[:max_chars]
