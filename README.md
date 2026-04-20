English | [中文](README.zh.md) 
# oneMem

Cross-IDE persistent memory plugin for Claude Code and Cursor IDE, powered by [PowerMem](https://github.com/oceanbase/powermem).

## What it does

- **Session start:** loads a memory index with progressive disclosure (search → timeline → details)
- **During session:** captures tool observations via PostToolUse hook with automatic classification
- **Session end:** saves structured observations with metadata (type, title, concepts, files)
- **MCP tools:** provides `search`, `get_memory`, `recent` tools for on-demand lookup

### Progressive Disclosure

Instead of dumping all context at session start, oneMem uses a 3-layer workflow:

1. **Index at session start** — shows available memories grouped by date
2. **Timeline via MCP tool** — `recent` returns structured list with types/titles
3. **Details on demand** — `get_memory` fetches full content when needed

### Observation Classification

Automatic type detection based on content patterns:

| Type | Emoji | Pattern examples |
|------|-------|------------------|
| Gotcha | 🔴 | timeout, failed, error, crash |
| Bugfix | 🟡 | fix, fixed, bug, patched |
| Decision | 🟤 | decided, chose, architecture |
| Feature | 🟢 | added, implemented, created |
| Discovery | 🟣 | found, discovered, learned |
| Trade-off | ⚖️ | compromise, balance, pros/cons |
| Change | 🔵 | modified, updated, refactored |

## Installation

### 1. Add the marketplace

```
/plugin marketplace add linyuanbin/oneMem
```

### 2. Install the plugin

```bash
/plugin install onemem@lin
```

### 3. Configure PowerMem access

```bash
mkdir -p ~/.oneMem
cat > ~/.oneMem/settings.json << 'EOF'
{
  "powermem_url": "https://your-powermem-instance.com",
  "api_key": "your-api-key",
  "user": "your-email"
}
EOF
```

| Field          | Required | Description                                  |
|----------------|----------|----------------------------------------------|
| `powermem_url` | ✅ | Base URL of your PowerMem instance           |
| `api_key`      | ✅ | API key sent as `X-API-Key` header           |
| `user`         | ✅ | User email sent as `Powermem-User-Id` header |
| `user_id`      | ❌ | Optional user identifier (UUID fallback)     |

## PowerMem Parameter Mapping

The plugin uses a specific mapping for PowerMem parameters:

| PowerMem Parameter | Value | Description |
|--------------------|-------|-------------|
| `agent_id` | Project identity | `git remote get-url origin` or `basename(cwd)` |
| `run_id` | Session ID | Claude Code: `session_id`, Cursor: `conversation_id` |
| `user_id` | User identifier | From config or random UUID |
| `user` | User email | Sent as `Powermem-User-Id` header |

**Design rationale:**

- **agent_id = project identity**: **Primary isolation dimension** - memories shared across sessions/IDEs for same project
- **run_id = session_id**: Stored for **traceability only** - saved at write, NOT used as search filter
- **agent_id field in config is NOT used**: Project identity derived from git/cwd

**Cross-session/Cross-IDE sharing:**

Since `agent_id` is project identity, all sessions working on the same project:
- **Search**: Get all historical memories for this project (not filtered by session_id)
- **Save**: Record current session_id (for traceability)

This enables:
- ✅ Cross-session memory sharing within same project
- ✅ Cross-IDE memory sharing (Claude Code ↔ Cursor)
- ✅ Project isolation (different projects don't share memories)

## MCP Tools

The plugin provides an MCP server with these tools.

### How to Trigger MCP Queries

In Claude Code, MCP tools are automatically available after plugin installation.

**Option 1: Direct Request**

Just ask Claude in natural language:

```
Search memory for authentication implementation
```

```
Show recent memories from last 7 days
```

```
Get full details for memory ID 123 and 456
```

**Option 2: After Viewing Index**

Session start shows a memory index table:

```
### Recent Observations Index

| ID | Type | Title | Date |
|----|------|-------|------|
| #123 | 🟢 | Add auth module | 2024-01-15 |
| #124 | 🟡 | Fix timeout bug | 2024-01-14 |

💡 Progressive Disclosure: Use MCP search tools to fetch full details on-demand.
```

Then request specific details:

```
Get full content for #123 and #124
```

### search

Search memories by query with optional type filter.

**Example requests:**

```
Search for "API endpoint" in memory
```

```
Show all bugfix type memories
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Search query (can be empty to get all) |
| `type` | string | Type filter: gotcha, decision, bugfix, feature, discovery, change |
| `limit` | integer | Max results (default 20) |

### get_memory

Fetch full content of specific memories by IDs.

**Example request:**

```
Get details for memory #123
```

```
Show full content for IDs 123, 456, 789
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ids` | array[int] | ✅ | Memory ID array |

Returns: full text, type, title, concepts, related files, saved date.

### recent

Get timeline of recent memories for the current project.

**Example request:**

```
Show memories from last 30 days
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `days` | integer | Days to look back (default 7) |
| `limit` | integer | Max results (default 10) |

### Tool Names

Internal MCP tool names:

| Display Name | MCP Tool | Server |
|--------------|----------|--------|
| search | `search` | `memory-search` |
| get_memory | `get_memory` | `memory-search` |
| recent | `recent` | `memory-search` |

## Cursor IDE Setup

Cursor IDE supports Claude Code hooks format but requires manual configuration.

### Option 1: Manual Hooks Configuration (Recommended)

#### 1. Create hooks config in project

```bash
mkdir -p .cursor
cat > .cursor/hooks.json << 'EOF'
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/plugins/xx/onemem/scripts/onemem.py load",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/plugins/xx/onemem/scripts/onemem.py load observe",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/plugins/xx/onemem/scripts/onemem.py load save",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
EOF
```

Replace the path with your actual plugin location.

#### 2. Configure MCP (Optional)

In Cursor Settings → MCP → Add Server:

```json
{
  "name": "memory-search",
  "command": "python3",
  "args": ["~/.claude/plugins/xx/onemem/scripts/onemem.py load", "mcp"]
}
```

#### 3. Configure PowerMem

Same as Claude Code: create `~/.oneMem/settings.json`.

### Option 2: Clone Plugin Repository

```bash
git clone https://github.com/linyuanbin/oneMem.git
# Then configure .cursor/hooks.json with absolute paths
```

### Comparison: Claude Code vs Cursor

| Feature | Claude Code | Cursor IDE |
|---------|-------------|------------|
| Plugin install | `/plugin install` command | Manual hooks.json config |
| MCP config | Auto-registered via plugin.json | Manual in Settings |
| Hooks path | `${CLAUDE_PLUGIN_ROOT}` variable | Absolute path required |
| Session ID | `session_id` | `conversation_id` |
| Working dir | `cwd` | `workspace_roots` |

## Cross-IDE Compatibility

Works with both Claude Code and Cursor IDE:

| Feature | Claude Code | Cursor IDE |
|---------|-------------|------------|
| Session ID | `session_id` | `conversation_id` |
| Working dir | `cwd` | `workspace_roots[0]` |
| Transcript format | `.jsonl` with `type` field | `.jsonl` with `role` + `<user_query>` tags |

## Requirements

- Python 3 (stdlib only, no pip installs needed)
- A running [PowerMem](https://github.com/oceanbase/powermem) instance

## Error handling

All errors are silent and non-blocking. If PowerMem is unreachable or config is missing, the IDE starts and stops normally — no memory is loaded or saved for that session.