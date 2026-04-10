#!/usr/bin/env python3
"""
onemem.py — Claude Code hook handler for cross-session memory via PowerMem.

Subcommands:
  load   SessionStart hook: fetch last memory from PowerMem, inject as context
  save   Stop hook: extract transcript context, persist to PowerMem

Config: ~/.oneMem/settings.json  (override with ONEMEM_CONFIG env var)
  {
    "powermem_url": "https://...",  # required
    "api_key": "...",               # optional (leave empty if no auth required)
    "agent_id": "onemem"            # optional, default "onemem"
  }
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CONFIG_PATH = Path.home() / ".oneMem" / "settings.json"


def load_config(path=None):
    """
    Read ~/.oneMem/settings.json (or a custom path for testing).
    The ONEMEM_CONFIG environment variable overrides the default path.
    Returns a dict with keys: powermem_url, api_key, agent_id.
    Returns None if file is missing or powermem_url is absent.
    """
    config_file = Path(path) if path else Path(os.environ.get("ONEMEM_CONFIG", "") or CONFIG_PATH)
    try:
        with open(config_file) as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not cfg.get("powermem_url"):
        return None
    # api_key is optional — PowerMem may run without authentication
    cfg.setdefault("api_key", "")

    cfg.setdefault("agent_id", "onemem")
    cfg.setdefault("user", "")
    cfg.setdefault("user_id", "")
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

    Handles two formats:
    - Current CC format: entry.type == "assistant", content in entry.message.content
    - Legacy format: entry.role == "assistant", content in entry.content
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
        # Claude Code transcript format: entry.type == "assistant" with
        # content nested in entry.message.content.
        # Also handle legacy format where role is at the top level.
        if entry.get("type") == "assistant":
            content = entry.get("message", {}).get("content", [])
        elif entry.get("role") == "assistant":
            content = entry.get("content", [])
        else:
            continue
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


def powermem_search(base_url, api_key, agent_id, user_id, run_id, user="", limit=1):
    """
    POST /api/v1/memories/search.
    user_id  — from config (or UUID fallback), sent in request body
    run_id   — git remote / cwd basename, sent in request body
    user     — from config, sent as Powermem-User-Id header (omitted if empty)
    Returns list of result dicts from data.results, or [] on any error.
    """
    url = base_url.rstrip("/") + "/api/v1/memories/search"
    payload = {
        "query": "development context progress tasks",
        "agent_id": agent_id,
        "user_id": user_id,
        "run_id": run_id,
        "limit": limit,
    }
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    if user:
        headers["Powermem-User-Id"] = user
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
        return body.get("data", {}).get("results", [])
    except Exception:
        return []


def powermem_add(base_url, api_key, agent_id, user_id, content, metadata):
    """
    POST /api/v1/memories.
    Returns True on success, False on any error.
    """
    url = base_url.rstrip("/") + "/api/v1/memories"
    payload = {
        "content": content,
        "agent_id": agent_id,
        "user_id": user_id,
        "infer": False,
        "metadata": metadata,
    }
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True
    except Exception:
        return False


def cmd_load(stdin_data):
    """
    SessionStart hook handler.
    Returns a JSON string: either hookSpecificOutput with additionalContext,
    or {} if no config / no memory found.
    """
    cfg = load_config()
    if not cfg:
        return json.dumps({})

    cwd = stdin_data.get("cwd", os.getcwd())
    run_id = get_project_id(cwd)
    user_id = cfg.get("user_id") or run_id

    results = powermem_search(
        cfg["powermem_url"], cfg["api_key"], cfg["agent_id"],
        user_id=user_id, run_id=run_id, user=cfg.get("user", ""),
    )
    if not results:
        return json.dumps({})

    content = results[0].get("content", "")
    if not content:
        return json.dumps({})

    saved_at = results[0].get("metadata", {}).get("saved_at", "")
    date_str = saved_at[:10] if saved_at else "unknown date"

    output = {
        "systemMessage": f"oneMem: memory loaded from {date_str}",
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"## Previous Session Memory\n\n{content}",
        },
    }
    return json.dumps(output)


def cmd_save(stdin_data):
    """
    Stop hook handler.
    Extracts the last 10 assistant messages from the transcript and
    persists them to PowerMem. Silent on all errors.
    """
    cfg = load_config()
    if not cfg:
        return

    cwd = stdin_data.get("cwd", os.getcwd())
    user_id = get_project_id(cwd)
    session_id = stdin_data.get("session_id", "")
    transcript_path = stdin_data.get("transcript_path", "")

    context = extract_context_from_transcript(transcript_path)
    if not context:
        return

    metadata = {
        "session_id": session_id,
        "cwd": cwd,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    powermem_add(cfg["powermem_url"], cfg["api_key"], cfg["agent_id"], user_id, context, metadata)


def main():
    """Entry point. Reads stdin JSON, dispatches to cmd_load or cmd_save."""
    if len(sys.argv) < 2 or sys.argv[1] not in ("load", "save"):
        sys.exit(1)

    try:
        stdin_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError):
        stdin_data = {}

    try:
        if sys.argv[1] == "load":
            output = cmd_load(stdin_data)
            print(output)
        else:
            cmd_save(stdin_data)
    except Exception:
        # Never crash — hooks must always exit 0
        if sys.argv[1] == "load":
            print("{}")


if __name__ == "__main__":
    main()
