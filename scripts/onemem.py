#!/usr/bin/env python3
"""
onemem.py — Cross-IDE persistent memory plugin with progressive disclosure.

Enhanced version of oneMem with:
- Structured observations with type classification (gotcha, decision, bugfix, etc.)
- PostToolUse hook for capturing key tool executions
- MCP search tools for progressive disclosure retrieval

Subcommands:
  load       SessionStart hook: fetch memory index, inject as context
  save       Stop hook: extract transcript, create structured observations
  observe    PostToolUse hook: capture individual tool execution
  mcp        MCP server mode: provide search tools

Config: ~/.oneMem/settings.json
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================

CONFIG_PATH = Path.home() / ".oneMem" / "settings.json"
OBSERVATION_TYPES = {
    "decision": "🟤",  # Architecture or design decisions
    "gotcha": "🔴",  # Critical edge cases or pitfalls
    "bugfix": "🟡",  # Bug fixes and corrections
    "feature": "🟢",  # New features or capabilities
    "discovery": "🟣",  # Learnings about the codebase
    "change": "🔵",  # General changes and modifications
    "how-it-works": "🔷",  # Technical explanations
    "trade-off": "⚖️",  # Deliberate compromises
    "request": "🎯",  # User's original goal
}


# ============================================================================
# Configuration Management
# ============================================================================

def load_config(path=None):
    """Read ~/.oneMem/settings.json or custom path."""
    config_file = Path(path) if path else Path(os.environ.get("ONEMEM_CONFIG", "") or CONFIG_PATH)
    try:
        with open(config_file) as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not cfg.get("powermem_url"):
        return None

    cfg.setdefault("api_key", "")
    cfg.setdefault("user", "")
    cfg.setdefault("user_id", "")
    cfg.setdefault("index_limit", 20)  # Max observations in session start index
    cfg.setdefault("index_days", 7)  # Days to look back for index
    # Note: agent_id is NOT from config - it's derived from project identity (git remote or cwd)
    return cfg


def get_project_id(cwd):
    """Return git remote origin URL as project identity."""
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


def get_cwd(stdin_data):
    """Extract working directory from hook input (Claude Code or Cursor format)."""
    if "cwd" in stdin_data:
        return stdin_data["cwd"]
    workspace_roots = stdin_data.get("workspace_roots", [])
    if isinstance(workspace_roots, list) and workspace_roots:
        return workspace_roots[0]
    return os.getcwd()


def get_session_id(stdin_data):
    """Get session/conversation ID from hook input."""
    return stdin_data.get("session_id") or stdin_data.get("conversation_id", "")


# ============================================================================
# PowerMem API Operations
# ============================================================================

def powermem_search(base_url, api_key, agent_id, user_id, run_id, query="",
                    obs_type=None, limit=20, days=7, user=""):
    """
    Search observations from PowerMem with filters.
    agent_id: project identity (git remote URL or cwd basename)
    run_id: session/conversation ID (optional - omit if empty)
    """
    url = base_url.rstrip("/") + "/api/v1/memories/search"
    payload = {
        "query": query or "development context",
        "agent_id": agent_id,  # Project identity
        "user_id": user_id,
        "limit": limit,
    }
    # Only include run_id if it's non-empty (empty run_id causes API to filter all results)
    if run_id:
        payload["run_id"] = run_id

    # Add metadata filters if supported
    if obs_type:
        payload["metadata_filter"] = {"type": obs_type}
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        payload["created_after"] = cutoff.isoformat()

    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    if user:
        headers["Powermem-User-Id"] = user

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        return body.get("data", {}).get("results", [])
    except Exception:
        return []


def powermem_add(base_url, api_key, agent_id, user_id, run_id, content,
                 metadata, user=""):
    """
    Add an observation to PowerMem.
    agent_id: project identity (git remote URL or cwd basename)
    run_id: session/conversation ID
    """
    url = base_url.rstrip("/") + "/api/v1/memories"
    payload = {
        "content": content,
        "agent_id": agent_id,  # Now: project identity
        "user_id": user_id,
        "run_id": run_id,  # Now: session_id
        "infer": False,
        "metadata": metadata,
    }
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    if user:
        headers["Powermem-User-Id"] = user

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            pass
        return True
    except Exception:
        return False


def powermem_get(base_url, api_key, agent_id, memory_ids, user="", user_id="", run_id=""):
    """
    Fetch specific observations by IDs.
    Falls back to search if batch endpoint not available.
    """
    results = []
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    if user:
        headers["Powermem-User-Id"] = user

    # Try individual GET requests for each ID
    for memory_id in memory_ids:
        url = base_url.rstrip("/") + f"/api/v1/memories/{memory_id}"
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode())
                if body.get("data"):
                    results.append(body["data"])
        except Exception:
            continue

    return results


# ============================================================================
# Transcript Processing
# ============================================================================

def extract_text_from_content(content):
    """Extract text from a content array or string."""
    texts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    texts.append(text)
    elif isinstance(content, str) and content.strip():
        texts.append(content.strip())
    return texts


def extract_user_query(text):
    """Extract question text from <user_query> tags (Cursor format)."""
    match = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def detect_transcript_format(entries):
    """Detect if transcript is Cursor or Claude Code format."""
    for e in entries:
        if e.get("role") == "user":
            content = e.get("message", {}).get("content", []) or e.get("content", [])
            texts = extract_text_from_content(content)
            for t in texts:
                if "<user_query>" in t:
                    return "cursor"
    return "claude_code"


def extract_context_from_transcript(transcript_path, max_messages=10, max_chars=8000):
    """
    Read transcript.jsonl and extract context.
    Returns: {"user_query": str, "assistant_texts": list}
    """
    try:
        with open(transcript_path) as f:
            raw_lines = f.readlines()
    except (FileNotFoundError, OSError):
        return {"user_query": "", "assistant_texts": []}

    entries = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(entry)

    if not entries:
        return {"user_query": "", "assistant_texts": []}

    format_type = detect_transcript_format(entries)

    if format_type == "cursor":
        # Cursor: extract last user question + subsequent assistant replies
        last_user_idx = -1
        last_user_text = ""
        for i, entry in enumerate(entries):
            if entry.get("role") == "user":
                content = entry.get("message", {}).get("content", []) or entry.get("content", [])
                texts = extract_text_from_content(content)
                for t in texts:
                    query = extract_user_query(t)
                    if query:
                        last_user_idx = i
                        last_user_text = query

        if last_user_idx < 0:
            return {"user_query": "", "assistant_texts": []}

        assistant_texts = []
        for entry in entries[last_user_idx + 1:]:
            if entry.get("role") == "assistant":
                content = entry.get("message", {}).get("content", [])
                texts = extract_text_from_content(content)
                for t in texts:
                    if t.strip() and not t.startswith("[REDACTED]"):
                        cleaned = re.sub(r"\n+\[REDACTED\]$", "", t)
                        if cleaned.strip():
                            assistant_texts.append(cleaned)

        return {
            "user_query": last_user_text,
            "assistant_texts": assistant_texts[:max_messages]
        }

    else:
        # Claude Code: extract last max_messages assistant texts
        assistant_texts = []
        for entry in entries:
            if entry.get("type") == "assistant":
                content = entry.get("message", {}).get("content", [])
            elif entry.get("role") == "assistant":
                content = entry.get("message", {}).get("content", []) or entry.get("content", [])
            else:
                continue
            texts = extract_text_from_content(content)
            assistant_texts.extend(texts)

        return {
            "user_query": "",  # Claude Code format doesn't have clear user query extraction
            "assistant_texts": assistant_texts[-max_messages:]
        }


# ============================================================================
# Observation Classification (Phase 1)
# ============================================================================

def classify_observation(content, tool_name=None):
    """
    Classify observation type based on content patterns.
    Returns: (type_key, type_icon)
    """
    content_lower = content.lower()

    # Pattern-based classification
    patterns = {
        "gotcha": [
            r"timeout|failed|error|crash|exception",
            r"gotcha|pitfall|edge case|boundary",
            r"doesn't work|not working|broken",
            r"surprising|unexpected|counterintuitive",
        ],
        "bugfix": [
            r"fix|fixed|bug|bugfix",
            r"patch|hotfix|workaround",
            r"resolve|resolved|correct",
        ],
        "decision": [
            r"decision|decided|choose|chose",
            r"architecture|design|pattern",
            r"strategy|approach|method",
            r"adopt|adopted|implement",
        ],
        "feature": [
            r"add|added|new feature|implement",
            r"create|created|build|built",
            r"extend|extended|enhance",
        ],
        "discovery": [
            r"found|discover|learned|realized",
            r"noticed|observed|insight",
            r"turns out|actually|seems",
        ],
        "trade-off": [
            r"trade-off|tradeoff|compromise",
            r"balance|权衡|versus|vs",
            r"pro|con|advantage|disadvantage",
        ],
    }

    for type_key, regex_list in patterns.items():
        for pattern in regex_list:
            if re.search(pattern, content_lower):
                return type_key, OBSERVATION_TYPES.get(type_key, "🔵")

    # Default classification based on tool
    if tool_name:
        tool_classification = {
            "Write": "change",
            "Edit": "change",
            "Bash": "change",
            "Read": "discovery",
        }
        if tool_name in tool_classification:
            return tool_classification[tool_name], OBSERVATION_TYPES.get(tool_classification[tool_name], "🔵")

    return "change", "🔵"


def extract_concepts(content):
    """Extract key concepts/topics from content."""
    # Simple keyword extraction
    concepts = []

    # Technical keywords
    tech_patterns = [
        r"\b(api|rest|graphql|http|endpoint)\b",
        r"\b(auth|authentication|oauth|jwt|token)\b",
        r"\b(database|db|sql|postgres|mysql|mongo)\b",
        r"\b(test|testing|unittest|pytest|jest)\b",
        r"\b(config|configuration|settings|env)\b",
        r"\b(hook|plugin|extension)\b",
        r"\b(mcp|server|protocol)\b",
        r"\b(memory|context|session)\b",
        r"\b(git|branch|commit|merge|pull)\b",
        r"\b(type|interface|class|function|method)\b",
    ]

    for pattern in tech_patterns:
        match = re.search(pattern, content.lower())
        if match:
            concepts.append(match.group(1))

    return concepts[:5]  # Limit to 5 concepts


def extract_files_from_content(content):
    """Extract file paths mentioned in content."""
    # Look for file paths
    file_patterns = [
        r"([a-zA-Z0-9_\-./]+\.[a-zA-Z]{2,4})",  # Simple file extensions
        r"`([^`]+\.[a-zA-Z]{2,4})`",  # Files in backticks
        r"\"([^\"]+\.[a-zA-Z]{2,4})\"",  # Files in quotes
    ]

    files = []
    for pattern in file_patterns:
        matches = re.findall(pattern, content)
        for m in matches:
            if len(m) > 3 and not m.startswith("http"):
                files.append(m)

    return files[:10]  # Limit to 10 files


def create_title(content, max_length=60):
    """Create a concise title from content."""
    # Take first meaningful sentence
    lines = content.strip().split("\n")
    first_line = lines[0] if lines else ""

    # Remove common prefixes
    prefixes_to_remove = [
        "I ", "I'll ", "I will ", "Let me ", "Let's ",
        "The ", "This ", "Here ", "Now ", "Okay ",
        "Sure ", "Yes ", "No ", "Good ",
    ]
    for prefix in prefixes_to_remove:
        if first_line.startswith(prefix):
            first_line = first_line[len(prefix):]

    # Truncate to max length
    if len(first_line) > max_length:
        # Find a good break point
        break_points = ["。", ".", ",", " ", ":", ";"]
        for bp in break_points:
            idx = first_line[:max_length].rfind(bp)
            if idx > max_length // 2:
                return first_line[:idx + 1].strip()
        return first_line[:max_length].strip()

    return first_line.strip()


# ============================================================================
# Index Formatting (Progressive Disclosure)
# ============================================================================

def format_index(results):
    """
    Format search results as progressive disclosure index.
    Returns: Markdown table with ID, Type, Title, Date, Tokens
    """
    if not results:
        return "No recent observations found."

    lines = ["### Recent Observations Index", "",
             "| ID | Type | Title | Date |",
             "|----|------|-------|------|"]

    for obs in results:
        # PowerMem API returns "memory_id", some responses have "id"
        obs_id = obs.get("id") or obs.get("memory_id", "N/A")
        metadata = obs.get("metadata", {})

        # Get type with icon
        obs_type = metadata.get("type", "change")
        type_icon = OBSERVATION_TYPES.get(obs_type, "🔵")

        # Get title (from content or metadata)
        title = metadata.get("title", "")
        if not title:
            content = obs.get("content", "")
            title = create_title(content, 50)

        # Get date
        saved_at = metadata.get("saved_at", "")
        date_str = saved_at[:10] if saved_at else "unknown"

        # Estimate tokens (rough: 1 token per 4 chars)
        content_len = len(obs.get("content", ""))
        tokens = max(content_len // 4, 50)

        lines.append(f"| #{obs_id} | {type_icon} | {title} | {date_str} |")

    lines.append("")
    lines.append("💡 **Progressive Disclosure:** Use MCP search tools to fetch full details on-demand.")
    lines.append("- `search(query)` - Search memory index")
    lines.append("- `get_memory([ids])` - Fetch full details for selected IDs")

    return "\n".join(lines)


# ============================================================================
# Hook Handlers
# ============================================================================

def cmd_load(stdin_data):
    """
    SessionStart hook: Load memory index and inject as context.
    Implements progressive disclosure - show index, not full details.

    Parameter mapping:
    - agent_id (PowerMem): project identity (git remote URL or cwd basename)
    - run_id (PowerMem): session/conversation ID
    """
    cfg = load_config()
    if not cfg:
        return json.dumps({})

    cwd = get_cwd(stdin_data)
    project_id = get_project_id(cwd)  # Used as agent_id
    session_id = get_session_id(stdin_data)  # Used as run_id
    user_id = cfg.get("user_id") or cfg.get("user") or str(uuid.uuid4())
    user = cfg.get("user", "")

    # Search for recent observations
    # agent_id = project_id (isolation by project)
    # run_id is NOT used for search - we want ALL historical memories for this project
    # (run_id is only stored during save for traceability, not for filtering)
    results = powermem_search(
        cfg["powermem_url"], cfg["api_key"],
        agent_id=project_id,  # Project identity - main isolation dimension
        user_id=user_id, run_id="",  # Empty: don't filter by session
        user=user,
        limit=cfg.get("index_limit", 20),
        days=cfg.get("index_days", 7),
    )

    if not results:
        return json.dumps({})

    # Format as progressive disclosure index
    index_text = format_index(results)

    output = {
        "systemMessage": "onemem: memory index loaded for progressive disclosure",
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"## Memory Index\n\n{index_text}",
        },
    }
    return json.dumps(output)


def cmd_save(stdin_data):
    """
    Stop hook: Create structured observation from transcript.
    Phase 1: Enhanced with type classification and metadata.

    Parameter mapping:
    - agent_id (PowerMem): project identity (git remote URL or cwd basename)
    - run_id (PowerMem): session/conversation ID
    """
    cfg = load_config()
    if not cfg:
        return

    cwd = get_cwd(stdin_data)
    project_id = get_project_id(cwd)  # Used as agent_id
    session_id = get_session_id(stdin_data)  # Used as run_id
    user_id = cfg.get("user_id") or cfg.get("user") or str(uuid.uuid4())
    user = cfg.get("user", "")
    transcript_path = stdin_data.get("transcript_path", "")

    context = extract_context_from_transcript(transcript_path)
    if not context.get("assistant_texts"):
        return

    # Combine content
    combined = ""
    if context.get("user_query"):
        combined = f"Q: {context['user_query']}\n---\n"
    combined += "A: " + "\n".join(context["assistant_texts"])
    combined = combined[:4000]  # Limit content size

    # Create structured observation
    obs_type, type_icon = classify_observation(combined)
    title = create_title(combined)
    concepts = extract_concepts(combined)
    files = extract_files_from_content(combined)

    metadata = {
        "type": obs_type,
        "type_icon": type_icon,
        "title": title,
        "concepts": concepts,
        "files_mentioned": files,
        "session_id": session_id,
        "cwd": cwd,
        "project_id": project_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source": "stop_hook",
    }

    # agent_id = project_id, run_id = session_id
    powermem_add(
        cfg["powermem_url"], cfg["api_key"],
        agent_id=project_id,  # Project identity
        user_id=user_id, run_id=session_id,  # session_id as run_id
        content=combined, metadata=metadata, user=user,
    )


def cmd_observe(stdin_data):
    """
    PostToolUse hook: Capture individual tool execution as observation.
    Phase 1: Capture key tool executions with metadata.

    Parameter mapping:
    - agent_id (PowerMem): project identity (git remote URL or cwd basename)
    - run_id (PowerMem): session/conversation ID
    """
    cfg = load_config()
    if not cfg:
        return

    cwd = get_cwd(stdin_data)
    project_id = get_project_id(cwd)  # Used as agent_id
    session_id = get_session_id(stdin_data)  # Used as run_id
    user_id = cfg.get("user_id") or cfg.get("user") or str(uuid.uuid4())
    user = cfg.get("user", "")

    tool_name = stdin_data.get("tool_name", "")
    tool_input = stdin_data.get("tool_input", {})
    tool_output = stdin_data.get("tool_output", "")

    # Skip low-value tools
    skip_tools = ["Glob", "Grep", "LSP", "TaskOutput", "TaskList", "TaskGet"]
    if tool_name in skip_tools:
        return

    # Create observation content
    content_parts = [f"Tool: {tool_name}"]

    if tool_name in ["Write", "Edit"]:
        file_path = tool_input.get("file_path", "")
        content_parts.append(f"File: {file_path}")
        # Extract the change description
        if tool_name == "Edit":
            old_str = tool_input.get("old_string", "")[:100]
            new_str = tool_input.get("new_string", "")[:100]
            content_parts.append(f"Changed: '{old_str}' → '{new_str}'")

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        content_parts.append(f"Command: {command}")
        # Include output summary
        if tool_output:
            output_preview = tool_output[:200] if len(tool_output) > 200 else tool_output
            content_parts.append(f"Output: {output_preview}")

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        content_parts.append(f"Read: {file_path}")

    else:
        # Generic tool capture
        if tool_input:
            input_preview = json.dumps(tool_input)[:200]
            content_parts.append(f"Input: {input_preview}")

    content = "\n".join(content_parts)

    # Classify and create metadata
    obs_type, type_icon = classify_observation(content, tool_name)
    title = f"{tool_name}: " + create_title(content, 40)
    concepts = extract_concepts(content)

    # Extract files
    files = []
    if tool_name in ["Write", "Edit", "Read"]:
        files.append(tool_input.get("file_path", ""))

    metadata = {
        "type": obs_type,
        "type_icon": type_icon,
        "title": title,
        "tool_name": tool_name,
        "concepts": concepts,
        "files_modified": files,
        "cwd": cwd,
        "project_id": project_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source": "post_tool_use",
    }

    # agent_id = project_id, run_id = session_id
    powermem_add(
        cfg["powermem_url"], cfg["api_key"],
        agent_id=project_id,  # Project identity
        user_id=user_id, run_id=session_id,  # session_id as run_id
        content=content, metadata=metadata, user=user,
    )


# ============================================================================
# MCP Server (Phase 2)
# ============================================================================

def mcp_handle_request(request):
    """Handle MCP protocol request."""
    method = request.get("method", "")

    # MCP initialization handshake
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "onemem",
                "version": "1.0.0"
            }
        }

    if method == "initialized":
        # Notification after initialize, no response needed
        return None

    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "search",
                    "description": "Search memory index. Returns compact index with IDs (~50-100 tokens). Use this FIRST to find relevant observations.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "type": {"type": "string",
                                     "description": "Filter by type: gotcha, decision, bugfix, feature, discovery, change"},
                            "limit": {"type": "integer", "description": "Max results (default 20)"},
                        },
                    },
                },
                {
                    "name": "get_memory",
                    "description": "Fetch full observation details by IDs. Use AFTER search to get details for relevant observations (~500-1000 tokens each).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ids": {"type": "array", "items": {"type": "integer"},
                                    "description": "Observation IDs from search results"},
                        },
                        "required": ["ids"],
                    },
                },
                {
                    "name": "recent",
                    "description": "Get recent observations for current project.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "description": "Days to look back (default 7)"},
                            "limit": {"type": "integer", "description": "Max results (default 10)"},
                        },
                    },
                },
            ]
        }

    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")
        args = request.get("params", {}).get("arguments", {})

        cfg = load_config()
        if not cfg:
            return {"content": [{"type": "text", "text": "Error: Configuration not found"}]}

        # Get project context from environment or default
        cwd = os.environ.get("CURSOR_PROJECT_DIR", os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
        project_id = get_project_id(cwd)  # Used as agent_id
        user_id = cfg.get("user_id") or cfg.get("user") or str(uuid.uuid4())
        user = cfg.get("user", "")

        if tool_name == "search":
            query = args.get("query", "")
            obs_type = args.get("type")
            limit = args.get("limit", 20)

            # agent_id = project_id, run_id = "" (no session context in MCP)
            results = powermem_search(
                cfg["powermem_url"], cfg["api_key"],
                agent_id=project_id,  # Project identity
                user_id=user_id, run_id="",  # No session context
                user=user,
                query=query, obs_type=obs_type, limit=limit, days=30,
            )

            # Return as formatted index
            index_text = format_index(results)
            return {"content": [{"type": "text", "text": index_text}]}

        elif tool_name == "get_memory":
            ids = args.get("ids", [])
            if not ids:
                return {"content": [{"type": "text", "text": "Error: No IDs provided"}]}

            # agent_id = project_id, run_id = "" (no session context in MCP)
            results = powermem_get(
                cfg["powermem_url"], cfg["api_key"],
                agent_id=project_id,
                memory_ids=ids, user=user, user_id=user_id, run_id="",
            )

            if not results:
                return {"content": [{"type": "text", "text": "No observations found for given IDs"}]}

            # Format full details
            details = []
            for obs in results:
                # PowerMem API returns "memory_id", some responses have "id"
                obs_id = obs.get("id") or obs.get("memory_id", "N/A")
                content = obs.get("content", "")
                metadata = obs.get("metadata", {})

                obs_type = metadata.get("type", "change")
                type_icon = OBSERVATION_TYPES.get(obs_type, "🔵")
                title = metadata.get("title", "Untitled")
                concepts = metadata.get("concepts", [])
                files = metadata.get("files_modified", [])
                saved_at = metadata.get("saved_at", "")

                detail = f"## #{obs_id} {type_icon} {title}\n"
                detail += f"**Type:** {obs_type}\n"
                detail += f"**Date:** {saved_at[:10] if saved_at else 'unknown'}\n"
                if concepts:
                    detail += f"**Concepts:** {', '.join(concepts)}\n"
                if files:
                    detail += f"**Files:** {', '.join(files)}\n"
                detail += f"\n**Content:**\n{content}\n"
                details.append(detail)

            return {"content": [{"type": "text", "text": "\n---\n".join(details)}]}

        elif tool_name == "recent":
            days = args.get("days", 7)
            limit = args.get("limit", 10)

            # agent_id = project_id, run_id = "" (no session context in MCP)
            results = powermem_search(
                cfg["powermem_url"], cfg["api_key"],
                agent_id=project_id,  # Project identity
                user_id=user_id, run_id="",  # No session context
                user=user,
                limit=limit, days=days,
            )

            index_text = format_index(results)
            return {"content": [{"type": "text", "text": index_text}]}

        else:
            return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}

    return {"error": f"Unknown method: {method}"}


def cmd_mcp():
    """
    MCP server mode: Read JSON-RPC requests from stdin, write responses to stdout.
    Implements Phase 2 MCP tools: search, get_memory, recent.
    """
    # MCP protocol: read requests line by line
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            response = mcp_handle_request(request)

            # Notifications (like "initialized") don't need responses
            if response is None:
                continue

            # Add JSON-RPC wrapper
            output = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": response,
            }
            print(json.dumps(output))
            sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": str(e)}))
            sys.stdout.flush()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Entry point. Dispatches to appropriate command."""
    if len(sys.argv) < 2:
        sys.exit(1)

    command = sys.argv[1]

    # Get stdin data (hook input)
    if sys.stdin.isatty():
        stdin_data = {}
    else:
        try:
            stdin_data = json.loads(sys.stdin.read())
        except (json.JSONDecodeError, IOError):
            stdin_data = {}

    try:
        if command == "load":
            output = cmd_load(stdin_data)
            print(output)
        elif command == "save":
            cmd_save(stdin_data)
        elif command == "observe":
            cmd_observe(stdin_data)
        elif command == "mcp":
            cmd_mcp()
        else:
            sys.exit(1)
    except Exception:
        # Never crash - hooks must always exit 0
        if command in ["load", "mcp"]:
            print("{}")


if __name__ == "__main__":
    main()
