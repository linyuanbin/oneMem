# oneMem Plugin — Design Spec

**Date:** 2026-04-02
**Status:** Approved
**Author:** Claude Code (brainstorming session)

---

## Overview

**oneMem** is a Claude Code plugin that provides persistent, cross-session development memory. It hooks into Claude Code's session lifecycle to automatically load the most recent memory context at session start, and save the current session's development context at session end. Memory is stored in and retrieved from **PowerMem** (oceanbase/powermem), an open-source semantic memory service.

The plugin is distributed via a GitHub-hosted marketplace and installed with a single `claude plugin install` command.

---

## Goals

- Restore previous development context automatically when starting a new Claude Code session
- Save current session's progress/context automatically when a session ends
- Zero friction: no manual commands required from the user during normal workflow
- Never block or disrupt the user's normal Claude Code workflow (all errors are non-fatal)

## Non-Goals (v1)

- LLM-based summarization of transcripts (raw extraction only)
- Support for Cursor, OpenClaw, or other editors (future work)
- Multiple memories per session (only the most recent 1 memory is loaded)
- Memory search/browsing UI

---

## Architecture

```
User installs plugin
     │
     ├─ ~/.oneMem/settings.json  ← user config (powermem_url, api_key, agent_id)
     │
SessionStart hook
     │  python onemem.py load
     │  ├── read ~/.oneMem/settings.json
     │  ├── get git remote origin URL → user_id (fallback: basename(cwd))
     │  ├── POST /api/v1/memories/search (query="development context progress tasks", limit=1)
     │  └── stdout → { hookSpecificOutput: { additionalContext: "<memory content>" } }
     │                        ↓ injected into Claude's context
     │
   [development session...]
     │
Stop hook
     │  python onemem.py save
     │  ├── read ~/.oneMem/settings.json
     │  ├── get user_id (same as above)
     │  ├── read transcript_path from stdin JSON
     │  ├── extract last 10 assistant messages from transcript.jsonl
     │  ├── POST /api/v1/memories (content=summary, user_id, agent_id, infer=false)
     │  └── exit silently
     │
PowerMem (oceanbase/powermem)
     └── semantic storage and retrieval
```

---

## File Structure

```
oneMem/
├── .claude-plugin/
│   ├── plugin.json          ← plugin metadata, declares name/version/hooks path
│   └── marketplace.json     ← marketplace manifest for /plugin install
│
├── hooks/
│   └── hooks.json           ← registers SessionStart + Stop hooks
│
├── scripts/
│   └── onemem.py            ← single Python script with load/save subcommands
│
├── README.md                ← installation guide + settings.json config example
└── CLAUDE.md                ← updated project guidance
```

---

## Component Details

### `.claude-plugin/plugin.json`

```json
{
  "name": "onemem",
  "version": "0.1.0",
  "description": "Persistent cross-session memory for Claude Code via PowerMem",
  "hooks": "./hooks/hooks.json"
}
```

### `.claude-plugin/marketplace.json`

```json
{
  "name": "onemem",
  "owner": { "name": "oneMem" },
  "plugins": [
    {
      "name": "onemem",
      "source": ".",
      "description": "Persistent cross-session memory for Claude Code via PowerMem",
      "version": "0.1.0",
      "category": "productivity",
      "tags": ["memory", "context", "persistence", "ai-agent"]
    }
  ]
}
```

### `hooks/hooks.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/onemem.py load",
            "timeout": 15,
            "statusMessage": "Loading memory context..."
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/onemem.py save",
            "timeout": 15,
            "async": true,
            "statusMessage": "Saving session memory..."
          }
        ]
      }
    ]
  }
}
```

### `scripts/onemem.py` — Internal Structure

Single file, logically organized into these sections:

| Function | Responsibility |
|----------|---------------|
| `load_config()` | Read `~/.oneMem/settings.json`, validate required fields (`powermem_url`, `api_key`) |
| `get_project_id(cwd)` | Run `git remote get-url origin` in `cwd`; fallback to `basename(cwd)` |
| `powermem_search(url, api_key, agent_id, user_id)` | POST `/api/v1/memories/search` with `query="development context progress tasks"`, `limit=1` |
| `powermem_add(url, api_key, agent_id, user_id, content, metadata)` | POST `/api/v1/memories` with `infer=false` |
| `extract_context_from_transcript(transcript_path)` | Read jsonl, filter `role=assistant`, take last 10 entries, concatenate text content, cap at 8000 chars |
| `cmd_load(stdin_data)` | Orchestrates load: config → project_id → search → output additionalContext JSON |
| `cmd_save(stdin_data)` | Orchestrates save: config → project_id → extract transcript → add to PowerMem |
| `main()` | Parse `sys.argv[1]` as subcommand (`load` or `save`), read stdin JSON, dispatch |

### `~/.oneMem/settings.json` (user-created, not in repo)

```json
{
  "powermem_url": "https://your-powermem-instance.com",
  "api_key": "your-api-key",
  "agent_id": "onemem"
}
```

- `powermem_url`: required — base URL of the PowerMem service
- `api_key`: required — sent as `X-API-Key` header
- `agent_id`: optional — defaults to `"onemem"` if omitted

---

## Data Flow

### SessionStart (load)

**Input (stdin):**
```json
{
  "session_id": "...",
  "transcript_path": "/.../.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/admin/go/src/myproject",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```

**Processing:**
1. Read `~/.oneMem/settings.json`
2. `git remote get-url origin` in `cwd` → `user_id`; fallback to `basename(cwd)`
3. POST `/api/v1/memories/search`: `{ query, agent_id, user_id, limit: 1 }`
4. If `results[0]` exists, prepare `additionalContext`

**Output (stdout, exit 0):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "## Previous Session Memory\n\n<content from PowerMem>"
  }
}
```

If no memory found or config missing: output `{}` (empty JSON object), exit 0.

### Stop (save)

**Input (stdin):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/.../.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/admin/go/src/myproject",
  "hook_event_name": "Stop"
}
```

**Processing:**
1. Read `~/.oneMem/settings.json`
2. Get `user_id` from git remote / basename
3. Read `transcript_path`, parse jsonl lines
4. Filter entries where `role == "assistant"`, extract text blocks
5. Take last 10 entries, join with `\n---\n`, truncate to 8000 chars
6. POST `/api/v1/memories`: `{ content, agent_id, user_id, infer: false, metadata: { session_id, cwd, saved_at } }`

**Output:** no stdout, exit 0 silently.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `~/.oneMem/settings.json` missing | `load`: output `additionalContext` with setup instructions; `save`: silent exit 0 |
| `powermem_url` or `api_key` missing | Same as above |
| Not a git repo | Fallback to `basename(cwd)` as `user_id` |
| PowerMem HTTP error / timeout | Catch exception, exit 0 (never block Claude) |
| `transcript_path` missing or malformed | Catch exception, silent exit 0 |
| No previous memories found | `load` outputs `{}`, session starts normally |
| Python not found | Hook fails silently (exit non-0 is non-blocking for non-PreToolUse events) |

**Core principle:** hooks must never block the user's workflow. All errors exit 0 (non-blocking).

---

## User Installation Flow

```bash
# 1. Add the oneMem marketplace
/plugin marketplace add <github-repo-path>

# 2. Install the plugin
claude plugin install onemem@onemem

# 3. Create config file
mkdir -p ~/.oneMem
cat > ~/.oneMem/settings.json << 'EOF'
{
  "powermem_url": "https://your-powermem-instance.com",
  "api_key": "your-api-key",
  "agent_id": "onemem"
}
EOF

# 4. Memory loads/saves automatically on every Claude Code session
```

---

## PowerMem API Reference

Based on `github.com/oceanbase/powermem`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/memories` | POST | Store a memory |
| `/api/v1/memories/search` | POST | Semantic search |

**Auth:** `X-API-Key: <api_key>` header (omitted if empty)

**Store request body:**
```json
{
  "content": "<text>",
  "agent_id": "<agent_id>",
  "user_id": "<git_remote_url>",
  "infer": false,
  "metadata": { "session_id": "...", "cwd": "...", "saved_at": "..." }
}
```

**Search request body:**
```json
{
  "query": "development context progress tasks",
  "agent_id": "<agent_id>",
  "user_id": "<git_remote_url>",
  "limit": 1
}
```

**Search response:**
```json
{
  "data": {
    "results": [
      { "memory_id": "...", "content": "...", "metadata": {}, "created_at": "..." }
    ]
  }
}
```

---

## Future Work (Out of Scope for v1)

- Cursor and OpenClaw support
- LLM-based transcript summarization before storing
- `/recall-memory` slash command for manual retrieval
- Multiple memory entries per session / memory management UI
- Automatic `~/.oneMem/settings.json` creation with guided setup prompt
