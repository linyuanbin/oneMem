# oneMem

Persistent cross-session memory for **Claude Code** and **Cursor**, powered by [PowerMem](https://github.com/oceanbase/powermem).

## What it does

- **Session start:** loads the most recent development context for the current project and injects it into the agent’s context
- **Session end:** saves the current session’s assistant responses to PowerMem for future recall
- Project identity is based on `git remote get-url origin` (falls back to directory name for non-git projects)

## How hooks work

| Stage | Behavior |
|--------|------------|
| **Load** | Reads `~/.oneMem/settings.json`, resolves `user_id` from git remote (or folder name), calls PowerMem search, returns JSON that injects prior memory as extra context |
| **Save** | Reads the conversation transcript path from hook stdin, extracts recent assistant text, POSTs a new memory to PowerMem |

All failures are non-blocking: missing config, network errors, or bad transcripts result in no load / no save, exit code `0`.

---

## Installation: Claude Code

### 1. Add the marketplace

```
/plugin marketplace add linyuanbin/oneMem
```

### 2. Install the plugin

```bash
claude plugin install onemem@lin
```

The plugin registers hooks via `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}` and the lifecycle events **`SessionStart`** (load) and **`Stop`** (save).

### 3. Configure PowerMem

Same as [Configure PowerMem access](#configure-powermem-access) below.

---

## Installation: Cursor

Cursor does not load `.claude-plugin` manifests. You wire **project hooks** under `.cursor/hooks.json` (paths are relative to the **project root**). Official reference: [Cursor Hooks](https://cursor.com/docs/hooks).

### 1. Get `onemem.py` on disk

Either clone this repo into your project (e.g. `tools/oneMem/`) or copy `scripts/onemem.py` somewhere stable. You need a path that `python3` can run from the hook command.

### 2. Create `.cursor/hooks.json`

Use schema **`version`: 1**. Map:

- **`sessionStart`** → `onemem.py load` (inject `additional_context`; Cursor supplies `workspace_roots`, `transcript_path`, etc. in stdin)
- **`sessionEnd`** → `onemem.py save` (fire-and-forget; reads `transcript_path` from stdin when transcripts are enabled)

Example (adjust the path to match your layout):

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "command": "python3 tools/oneMem/scripts/onemem.py load",
        "timeout": 15
      }
    ],
    "sessionEnd": [
      {
        "command": "python3 tools/oneMem/scripts/onemem.py save",
        "timeout": 15
      }
    ]
  }
}
```

If this repository **is** the workspace root, you can use:

```json
"command": "python3 scripts/onemem.py load"
```

### 3. Configure PowerMem

Same as the next section.

### Cursor-specific notes

- **Load output:** When stdin includes Cursor’s `cursor_version`, the script prints `{"additional_context": "..."}` (Cursor format). Claude Code uses `hookSpecificOutput.additionalContext` instead.
- **Project path:** Cursor often sends `workspace_roots` instead of `cwd`; the script maps the first root to `cwd` for git-based project identity.
- **Transcripts:** Save needs a valid `transcript_path` in hook input. If transcripts are disabled in Cursor, save becomes a no-op.
- **Debugging:** After editing `hooks.json`, Cursor reloads it on save; use the **Hooks** tab or **Hooks** output channel if something does not run.

---

## Configure PowerMem access

```bash
mkdir -p ~/.oneMem
cat > ~/.oneMem/settings.json << 'EOF'
{
  "powermem_url": "https://your-powermem-instance.com",
  "api_key": "your-api-key",
  "agent_id": "onemem"
}
EOF
```

| Field | Required | Description |
|-------|----------|-------------|
| `powermem_url` | ✅ | Base URL of your PowerMem instance |
| `api_key` | ✅ | API key sent as `X-API-Key` header (may be empty if your server has no auth) |
| `agent_id` | ❌ | Namespace for memories (default: `"onemem"`) |

Override the config file path with the environment variable **`ONEMEM_CONFIG`**.

---

## Requirements

- Python 3 (stdlib only, no pip installs needed)
- A running [PowerMem](https://github.com/oceanbase/powermem) instance

## Manual smoke tests

```bash
# Load (Claude-style stdin; Cursor adds cursor_version and workspace_roots)
echo '{"cwd":"/tmp","session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | python3 scripts/onemem.py load

# Cursor-style load (prints additional_context)
echo '{"cursor_version":"1.0","workspace_roots":["/tmp"],"session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | python3 scripts/onemem.py load

# Save
echo '{"cwd":"/tmp","session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | python3 scripts/onemem.py save
```

## Error handling

All errors exit `0` — hooks must never block the editor workflow. If PowerMem is unreachable or config is missing, sessions start and end normally; that turn simply skips memory load or save.
