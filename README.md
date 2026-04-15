# oneMem

Persistent cross-session memory for Claude Code, powered by [PowerMem](https://github.com/oceanbase/powermem).

## What it does

- **Session start:** loads the most recent development context for the current project and injects it into Claude's context
- **Session end:** saves the current session's assistant responses to PowerMem for future recall
- Project identity is based on `git remote get-url origin` (falls back to directory name for non-git projects)

## Installation

### 1. Add the marketplace

```
/plugin marketplace add linyuanbin/oneMem
```

### 2. Install the plugin

```bash
/plugin install onemem@lin

/plugin install superpowers@lin

/plugin install everything-claude-code@lin

/plugin install claude-mem@lin
```

### 3. Configure PowerMem access

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
| `api_key` | ✅ | API key sent as `X-API-Key` header |
| `agent_id` | ❌ | Namespace for memories (default: `"onemem"`) |

## Requirements

- Python 3 (stdlib only, no pip installs needed)
- A running [PowerMem](https://github.com/oceanbase/powermem) instance

## Error handling

All errors are silent and non-blocking. If PowerMem is unreachable or config is missing, Claude Code starts and stops normally — no memory is loaded or saved for that session.
