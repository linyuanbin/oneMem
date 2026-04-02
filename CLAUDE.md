# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**oneMem** is a Claude Code plugin for persistent cross-session development memory via PowerMem (oceanbase/powermem). It hooks into `SessionStart` and `Stop` lifecycle events to automatically load and save context.

## Project Structure

```
.claude-plugin/     Plugin manifest (plugin.json, marketplace.json)
hooks/              hooks.json — registers SessionStart + Stop handlers
scripts/onemem.py   Single Python script: all hook logic
tests/              Unit tests (Python unittest / pytest)
```

## Commands

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run a single test class
python3 -m pytest tests/test_onemem.py::TestLoadConfig -v

# Validate plugin JSON files
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"

# Smoke-test the load hook manually
echo '{"cwd":"/tmp","session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | python3 scripts/onemem.py load

# Smoke-test the save hook manually
echo '{"cwd":"/tmp","session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | python3 scripts/onemem.py save
```

## Key Design Decisions

- `user_id` for PowerMem = `git remote get-url origin`, fallback to `basename(cwd)`
- Config at `~/.oneMem/settings.json` (not in repo — survives plugin reinstalls)
- All errors exit 0 — hooks must never block the Claude Code workflow
- Python stdlib only — no dependencies to install
