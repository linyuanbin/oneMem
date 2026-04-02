# oneMem Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that automatically loads the most recent development context from PowerMem at session start and saves the current session's context at session end.

**Architecture:** A single Python script (`scripts/onemem.py`) serves as the hook handler for two lifecycle events: `SessionStart` (load) and `Stop` (save). It reads user config from `~/.oneMem/settings.json`, uses the git remote origin URL as the project identity (`user_id`), and communicates with PowerMem via its HTTP REST API.

**Tech Stack:** Python 3 (stdlib only: `json`, `urllib.request`, `subprocess`, `sys`, `os`, `pathlib`, `datetime`); Claude Code plugin manifest JSON; PowerMem REST API (`/api/v1/memories`, `/api/v1/memories/search`).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `.claude-plugin/plugin.json` | Create | Plugin metadata: name, version, hooks path |
| `.claude-plugin/marketplace.json` | Create | Marketplace manifest for distribution |
| `hooks/hooks.json` | Create | Register `SessionStart` and `Stop` hook handlers |
| `scripts/onemem.py` | Create | All hook logic: config loading, PowerMem client, transcript parsing, load/save commands |
| `tests/test_onemem.py` | Create | Unit tests for all pure functions in `onemem.py` |
| `README.md` | Create | Installation guide and configuration reference |
| `CLAUDE.md` | Modify | Update with project structure and commands |

---

## Task 1: Project scaffold — directories and static JSON files

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `hooks/hooks.json`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p .claude-plugin hooks scripts tests
```

- [ ] **Step 2: Create `.claude-plugin/plugin.json`**

```json
{
  "name": "onemem",
  "version": "0.1.0",
  "description": "Persistent cross-session memory for Claude Code via PowerMem",
  "hooks": "./hooks/hooks.json",
  "engines": { "claude-code": ">=1.0.0" }
}
```

- [ ] **Step 3: Create `.claude-plugin/marketplace.json`**

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

- [ ] **Step 4: Create `hooks/hooks.json`**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/onemem.py load",
            "timeout": 15
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
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/onemem.py save",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

> `Stop` is non-blocking by design — Claude Code does not wait for Stop hooks.

- [ ] **Step 5: Verify JSON files are valid**

```bash
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('plugin.json OK')"
python3 -c "import json; json.load(open('.claude-plugin/marketplace.json')); print('marketplace.json OK')"
python3 -c "import json; json.load(open('hooks/hooks.json')); print('hooks.json OK')"
```

Expected output:
```
plugin.json OK
marketplace.json OK
hooks.json OK
```

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/ hooks/
git commit -m "feat: add plugin manifest and hooks registration"
```

---

## Task 2: `load_config()` — read and validate `~/.oneMem/settings.json`

**Files:**
- Create: `scripts/onemem.py`
- Create: `tests/test_onemem.py`

- [ ] **Step 1: Create the test file with failing tests for `load_config`**

Create `tests/test_onemem.py`:

```python
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add scripts/ to path so we can import onemem
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import onemem


class TestLoadConfig(unittest.TestCase):

    def test_returns_config_with_all_fields(self):
        cfg = {"powermem_url": "http://localhost:8080", "api_key": "key123", "agent_id": "myagent"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        try:
            result = onemem.load_config(path)
            self.assertEqual(result["powermem_url"], "http://localhost:8080")
            self.assertEqual(result["api_key"], "key123")
            self.assertEqual(result["agent_id"], "myagent")
        finally:
            os.unlink(path)

    def test_agent_id_defaults_to_onemem_when_missing(self):
        cfg = {"powermem_url": "http://localhost:8080", "api_key": "key123"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        try:
            result = onemem.load_config(path)
            self.assertEqual(result["agent_id"], "onemem")
        finally:
            os.unlink(path)

    def test_returns_none_when_file_missing(self):
        result = onemem.load_config("/nonexistent/path/settings.json")
        self.assertIsNone(result)

    def test_returns_none_when_powermem_url_missing(self):
        cfg = {"api_key": "key123"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        try:
            result = onemem.load_config(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_returns_none_when_api_key_missing(self):
        cfg = {"powermem_url": "http://localhost:8080"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        try:
            result = onemem.load_config(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they fail (no onemem module yet)**

```bash
python3 -m pytest tests/test_onemem.py::TestLoadConfig -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'onemem'`

- [ ] **Step 3: Create `scripts/onemem.py` with `load_config` implementation**

```python
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
import urllib.request
import urllib.error
from datetime import datetime, timezone
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_onemem.py::TestLoadConfig -v
```

Expected: 5 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/onemem.py tests/test_onemem.py
git commit -m "feat: add load_config with tests"
```

---

## Task 3: `get_project_id()` — derive project identity from git remote

**Files:**
- Modify: `scripts/onemem.py`
- Modify: `tests/test_onemem.py`

- [ ] **Step 1: Add failing tests for `get_project_id`**

Append to `tests/test_onemem.py`, inside the file after `TestLoadConfig`:

```python
class TestGetProjectId(unittest.TestCase):

    def test_returns_git_remote_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/user/myrepo.git"],
                cwd=tmpdir, capture_output=True
            )
            result = onemem.get_project_id(tmpdir)
            self.assertEqual(result, "https://github.com/user/myrepo.git")

    def test_falls_back_to_dirname_when_no_git_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            # No remote added
            result = onemem.get_project_id(tmpdir)
            self.assertEqual(result, Path(tmpdir).name)

    def test_falls_back_to_dirname_when_not_git_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = onemem.get_project_id(tmpdir)
            self.assertEqual(result, Path(tmpdir).name)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_onemem.py::TestGetProjectId -v 2>&1 | head -10
```

Expected: `AttributeError: module 'onemem' has no attribute 'get_project_id'`

- [ ] **Step 3: Implement `get_project_id` in `scripts/onemem.py`**

Add after `load_config`:

```python
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
```

- [ ] **Step 4: Run all tests so far**

```bash
python3 -m pytest tests/test_onemem.py -v
```

Expected: all 8 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/onemem.py tests/test_onemem.py
git commit -m "feat: add get_project_id with git remote fallback"
```

---

## Task 4: `extract_context_from_transcript()` — parse transcript.jsonl

**Files:**
- Modify: `scripts/onemem.py`
- Modify: `tests/test_onemem.py`

Background: Claude Code writes transcripts as newline-delimited JSON (jsonl). Each line is a JSON object. Lines with `"role": "assistant"` contain the assistant's responses. Within those, `content` is a list; entries with `"type": "text"` have the actual text. We want the last 10 such assistant turns, concatenated, capped at 8000 characters.

Example transcript line structure:
```json
{"role": "assistant", "content": [{"type": "text", "text": "I've implemented the feature..."}]}
```

- [ ] **Step 1: Add failing tests for `extract_context_from_transcript`**

Append to `tests/test_onemem.py`:

```python
class TestExtractContextFromTranscript(unittest.TestCase):

    def _write_transcript(self, lines, path):
        with open(path, "w") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")

    def test_extracts_last_assistant_messages(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            lines = [
                {"role": "user", "content": [{"type": "text", "text": "hello"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "response one"}]},
                {"role": "user", "content": [{"type": "text", "text": "follow up"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "response two"}]},
            ]
            self._write_transcript(lines, path)
            result = onemem.extract_context_from_transcript(path)
            self.assertIn("response one", result)
            self.assertIn("response two", result)
            self.assertNotIn("hello", result)
            self.assertNotIn("follow up", result)
        finally:
            os.unlink(path)

    def test_takes_only_last_10_assistant_messages(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            lines = []
            for i in range(15):
                lines.append({"role": "assistant", "content": [{"type": "text", "text": f"msg {i}"}]})
            self._write_transcript(lines, path)
            result = onemem.extract_context_from_transcript(path)
            # Should contain msgs 5-14 (last 10), not msgs 0-4
            self.assertIn("msg 14", result)
            self.assertIn("msg 5", result)
            self.assertNotIn("msg 0", result)
            self.assertNotIn("msg 4", result)
        finally:
            os.unlink(path)

    def test_truncates_to_8000_chars(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            # Create a message that will be very long
            big_text = "x" * 1000
            lines = [{"role": "assistant", "content": [{"type": "text", "text": big_text}]} for _ in range(10)]
            self._write_transcript(lines, path)
            result = onemem.extract_context_from_transcript(path)
            self.assertLessEqual(len(result), 8000)
        finally:
            os.unlink(path)

    def test_returns_empty_string_when_file_missing(self):
        result = onemem.extract_context_from_transcript("/nonexistent/transcript.jsonl")
        self.assertEqual(result, "")

    def test_returns_empty_string_when_no_assistant_messages(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            lines = [{"role": "user", "content": [{"type": "text", "text": "only user"}]}]
            self._write_transcript(lines, path)
            result = onemem.extract_context_from_transcript(path)
            self.assertEqual(result, "")
        finally:
            os.unlink(path)

    def test_handles_malformed_jsonl_gracefully(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not json\n")
            f.write(json.dumps({"role": "assistant", "content": [{"type": "text", "text": "valid"}]}) + "\n")
            path = f.name
        try:
            result = onemem.extract_context_from_transcript(path)
            self.assertIn("valid", result)
        finally:
            os.unlink(path)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_onemem.py::TestExtractContextFromTranscript -v 2>&1 | head -10
```

Expected: `AttributeError: module 'onemem' has no attribute 'extract_context_from_transcript'`

- [ ] **Step 3: Implement `extract_context_from_transcript` in `scripts/onemem.py`**

Add after `get_project_id`:

```python
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
```

- [ ] **Step 4: Run all tests**

```bash
python3 -m pytest tests/test_onemem.py -v
```

Expected: all 14 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/onemem.py tests/test_onemem.py
git commit -m "feat: add extract_context_from_transcript with tests"
```

---

## Task 5: PowerMem HTTP client functions

**Files:**
- Modify: `scripts/onemem.py`
- Modify: `tests/test_onemem.py`

We use Python's stdlib `urllib.request` only — no third-party deps. Tests use `unittest.mock.patch` to mock the HTTP calls.

- [ ] **Step 1: Add failing tests for `powermem_search` and `powermem_add`**

Append to `tests/test_onemem.py`:

```python
from unittest.mock import patch, MagicMock
import urllib.error


class TestPowerMemSearch(unittest.TestCase):

    def _make_response(self, body_dict, status=200):
        import io
        body = json.dumps(body_dict).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_first_result_content(self):
        response_body = {
            "data": {
                "results": [
                    {"memory_id": "m1", "content": "previous work context", "metadata": {}, "created_at": "2026-01-01T00:00:00Z"}
                ]
            }
        }
        with patch("urllib.request.urlopen", return_value=self._make_response(response_body)):
            results = onemem.powermem_search("http://localhost:8080", "key", "onemem", "user/repo")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "previous work context")

    def test_returns_empty_list_when_no_results(self):
        response_body = {"data": {"results": []}}
        with patch("urllib.request.urlopen", return_value=self._make_response(response_body)):
            results = onemem.powermem_search("http://localhost:8080", "key", "onemem", "user/repo")
        self.assertEqual(results, [])

    def test_returns_empty_list_on_http_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            results = onemem.powermem_search("http://localhost:8080", "key", "onemem", "user/repo")
        self.assertEqual(results, [])

    def test_sends_correct_request_body(self):
        response_body = {"data": {"results": []}}
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["data"] = json.loads(req.data.decode())
            captured["headers"] = dict(req.headers)
            return self._make_response(response_body)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            onemem.powermem_search("http://localhost:8080", "mykey", "myagent", "git@github.com:user/repo")

        self.assertEqual(captured["data"]["agent_id"], "myagent")
        self.assertEqual(captured["data"]["user_id"], "git@github.com:user/repo")
        self.assertEqual(captured["data"]["limit"], 1)
        self.assertIn("X-api-key", captured["headers"])
        self.assertEqual(captured["headers"]["X-api-key"], "mykey")


class TestPowerMemAdd(unittest.TestCase):

    def _make_response(self, status=200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_true_on_success(self):
        with patch("urllib.request.urlopen", return_value=self._make_response(200)):
            result = onemem.powermem_add("http://localhost:8080", "key", "onemem", "user/repo", "content", {})
        self.assertTrue(result)

    def test_returns_false_on_http_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = onemem.powermem_add("http://localhost:8080", "key", "onemem", "user/repo", "content", {})
        self.assertFalse(result)

    def test_sends_correct_request_body(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["data"] = json.loads(req.data.decode())
            return self._make_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            onemem.powermem_add(
                "http://localhost:8080", "key", "onemem", "user/repo",
                "my context", {"session_id": "s1"}
            )

        self.assertEqual(captured["data"]["content"], "my context")
        self.assertEqual(captured["data"]["agent_id"], "onemem")
        self.assertEqual(captured["data"]["user_id"], "user/repo")
        self.assertFalse(captured["data"]["infer"])
        self.assertEqual(captured["data"]["metadata"]["session_id"], "s1")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_onemem.py::TestPowerMemSearch tests/test_onemem.py::TestPowerMemAdd -v 2>&1 | head -10
```

Expected: `AttributeError: module 'onemem' has no attribute 'powermem_search'`

- [ ] **Step 3: Implement `powermem_search` and `powermem_add` in `scripts/onemem.py`**

Add after `extract_context_from_transcript`:

```python
def powermem_search(base_url, api_key, agent_id, user_id, limit=1):
    """
    POST /api/v1/memories/search.
    Returns list of result dicts from data.results, or [] on any error.
    """
    url = base_url.rstrip("/") + "/api/v1/memories/search"
    payload = {
        "query": "development context progress tasks",
        "agent_id": agent_id,
        "user_id": user_id,
        "limit": limit,
    }
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
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
```

- [ ] **Step 4: Run all tests**

```bash
python3 -m pytest tests/test_onemem.py -v
```

Expected: all 23 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/onemem.py tests/test_onemem.py
git commit -m "feat: add PowerMem HTTP client functions with tests"
```

---

## Task 6: `cmd_load()` and `cmd_save()` — orchestration commands

**Files:**
- Modify: `scripts/onemem.py`
- Modify: `tests/test_onemem.py`

- [ ] **Step 1: Add failing tests for `cmd_load` and `cmd_save`**

Append to `tests/test_onemem.py`:

```python
class TestCmdLoad(unittest.TestCase):

    def test_outputs_additional_context_when_memory_found(self):
        stdin_data = {"cwd": "/tmp/myproject", "session_id": "s1", "transcript_path": "/tmp/t.jsonl"}
        fake_config = {"powermem_url": "http://pm", "api_key": "k", "agent_id": "onemem"}
        fake_results = [{"content": "last session: working on auth module", "memory_id": "m1"}]

        with patch.object(onemem, "load_config", return_value=fake_config), \
             patch.object(onemem, "get_project_id", return_value="github.com/user/repo"), \
             patch.object(onemem, "powermem_search", return_value=fake_results):
            output = onemem.cmd_load(stdin_data)

        parsed = json.loads(output)
        self.assertIn("hookSpecificOutput", parsed)
        self.assertIn("additionalContext", parsed["hookSpecificOutput"])
        self.assertIn("last session: working on auth module", parsed["hookSpecificOutput"]["additionalContext"])

    def test_outputs_empty_json_when_config_missing(self):
        stdin_data = {"cwd": "/tmp/myproject", "session_id": "s1", "transcript_path": "/tmp/t.jsonl"}

        with patch.object(onemem, "load_config", return_value=None):
            output = onemem.cmd_load(stdin_data)

        self.assertEqual(json.loads(output), {})

    def test_outputs_empty_json_when_no_memory_found(self):
        stdin_data = {"cwd": "/tmp/myproject", "session_id": "s1", "transcript_path": "/tmp/t.jsonl"}
        fake_config = {"powermem_url": "http://pm", "api_key": "k", "agent_id": "onemem"}

        with patch.object(onemem, "load_config", return_value=fake_config), \
             patch.object(onemem, "get_project_id", return_value="github.com/user/repo"), \
             patch.object(onemem, "powermem_search", return_value=[]):
            output = onemem.cmd_load(stdin_data)

        self.assertEqual(json.loads(output), {})


class TestCmdSave(unittest.TestCase):

    def test_calls_powermem_add_with_extracted_context(self):
        stdin_data = {
            "cwd": "/tmp/myproject",
            "session_id": "s42",
            "transcript_path": "/tmp/t.jsonl",
        }
        fake_config = {"powermem_url": "http://pm", "api_key": "k", "agent_id": "onemem"}
        fake_context = "I implemented the login feature and wrote tests"

        add_calls = []

        def fake_add(base_url, api_key, agent_id, user_id, content, metadata):
            add_calls.append({"content": content, "metadata": metadata})
            return True

        with patch.object(onemem, "load_config", return_value=fake_config), \
             patch.object(onemem, "get_project_id", return_value="github.com/user/repo"), \
             patch.object(onemem, "extract_context_from_transcript", return_value=fake_context), \
             patch.object(onemem, "powermem_add", side_effect=fake_add):
            onemem.cmd_save(stdin_data)

        self.assertEqual(len(add_calls), 1)
        self.assertEqual(add_calls[0]["content"], fake_context)
        self.assertEqual(add_calls[0]["metadata"]["session_id"], "s42")

    def test_does_nothing_when_config_missing(self):
        stdin_data = {"cwd": "/tmp/myproject", "session_id": "s1", "transcript_path": "/tmp/t.jsonl"}

        with patch.object(onemem, "load_config", return_value=None), \
             patch.object(onemem, "powermem_add") as mock_add:
            onemem.cmd_save(stdin_data)

        mock_add.assert_not_called()

    def test_does_nothing_when_transcript_empty(self):
        stdin_data = {"cwd": "/tmp/myproject", "session_id": "s1", "transcript_path": "/tmp/t.jsonl"}
        fake_config = {"powermem_url": "http://pm", "api_key": "k", "agent_id": "onemem"}

        with patch.object(onemem, "load_config", return_value=fake_config), \
             patch.object(onemem, "get_project_id", return_value="proj"), \
             patch.object(onemem, "extract_context_from_transcript", return_value=""), \
             patch.object(onemem, "powermem_add") as mock_add:
            onemem.cmd_save(stdin_data)

        mock_add.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_onemem.py::TestCmdLoad tests/test_onemem.py::TestCmdSave -v 2>&1 | head -10
```

Expected: `AttributeError: module 'onemem' has no attribute 'cmd_load'`

- [ ] **Step 3: Implement `cmd_load`, `cmd_save`, and `main` in `scripts/onemem.py`**

Add at the end of `scripts/onemem.py`:

```python
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
    user_id = get_project_id(cwd)

    results = powermem_search(cfg["powermem_url"], cfg["api_key"], cfg["agent_id"], user_id)
    if not results:
        return json.dumps({})

    content = results[0].get("content", "")
    if not content:
        return json.dumps({})

    output = {
        "hookSpecificOutput": {
            "hook_event_name": "SessionStart",
            "additionalContext": f"## Previous Session Memory\n\n{content}",
        }
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
```

- [ ] **Step 4: Run all tests**

```bash
python3 -m pytest tests/test_onemem.py -v
```

Expected: all 30 tests PASSED

- [ ] **Step 5: Make the script executable**

```bash
chmod +x scripts/onemem.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/onemem.py tests/test_onemem.py
git commit -m "feat: add cmd_load, cmd_save, and main entry point"
```

---

## Task 7: End-to-end smoke test (manual)

**Files:**
- No code changes — validation only

This task verifies that the plugin script behaves correctly when invoked exactly as Claude Code would invoke it.

- [ ] **Step 1: Test `load` command with no config (should output `{}`)**

```bash
echo '{"cwd":"/tmp","session_id":"test","transcript_path":"/tmp/none.jsonl","hook_event_name":"SessionStart"}' \
  | python3 scripts/onemem.py load
```

Expected output: `{}`

- [ ] **Step 2: Create a test config file**

```bash
mkdir -p /tmp/onemem-test
cat > /tmp/onemem-test/settings.json << 'EOF'
{
  "powermem_url": "http://localhost:19999",
  "api_key": "test-key",
  "agent_id": "onemem-test"
}
EOF
```

- [ ] **Step 3: Test `load` command with config but unreachable PowerMem (should output `{}`)**

```bash
echo '{"cwd":"/tmp","session_id":"test","transcript_path":"/tmp/none.jsonl"}' \
  | ONEMEM_CONFIG=/tmp/onemem-test/settings.json python3 scripts/onemem.py load
```

Expected output: `{}` (PowerMem unreachable → empty result, no crash)

- [ ] **Step 4: Create a minimal test transcript**

```bash
cat > /tmp/test-transcript.jsonl << 'EOF'
{"role": "user", "content": [{"type": "text", "text": "implement auth"}]}
{"role": "assistant", "content": [{"type": "text", "text": "I implemented JWT auth with refresh tokens. Tests are passing."}]}
{"role": "user", "content": [{"type": "text", "text": "add logout"}]}
{"role": "assistant", "content": [{"type": "text", "text": "Added logout endpoint. Invalidates the refresh token in Redis."}]}
EOF
```

- [ ] **Step 5: Test `save` command (should exit silently)**

```bash
echo "{\"cwd\":\"/tmp\",\"session_id\":\"s1\",\"transcript_path\":\"/tmp/test-transcript.jsonl\"}" \
  | python3 scripts/onemem.py save
echo "exit code: $?"
```

Expected output:
```
exit code: 0
```

(No crash even though PowerMem is unreachable — error is swallowed silently.)

- [ ] **Step 6: Run full test suite one final time**

```bash
python3 -m pytest tests/test_onemem.py -v --tb=short
```

Expected: all 30 tests PASSED

---

## Task 8: README and CLAUDE.md

**Files:**
- Create: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# oneMem

Persistent cross-session memory for Claude Code, powered by [PowerMem](https://github.com/oceanbase/powermem).

## What it does

- **Session start:** loads the most recent development context for the current project and injects it into Claude's context
- **Session end:** saves the current session's assistant responses to PowerMem for future recall
- Project identity is based on `git remote get-url origin` (falls back to directory name for non-git projects)

## Installation

### 1. Add the marketplace

```
/plugin marketplace add YOUR_GITHUB_REPO
```

### 2. Install the plugin

```bash
claude plugin install onemem@onemem
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
```

- [ ] **Step 2: Update `CLAUDE.md`**

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add README and update CLAUDE.md"
```

---

## Task 9: Final validation

- [ ] **Step 1: Run the complete test suite**

```bash
python3 -m pytest tests/ -v --tb=short
```

Expected: all 30 tests PASSED, 0 failures

- [ ] **Step 2: Validate all JSON files**

```bash
for f in .claude-plugin/plugin.json .claude-plugin/marketplace.json hooks/hooks.json; do
  python3 -c "import json; json.load(open('$f')); print('✓ $f')"
done
```

Expected:
```
✓ .claude-plugin/plugin.json
✓ .claude-plugin/marketplace.json
✓ hooks/hooks.json
```

- [ ] **Step 3: Verify script is executable and runs**

```bash
echo '{}' | python3 scripts/onemem.py load
```

Expected: `{}`

- [ ] **Step 4: Final commit**

```bash
git add -A
git status  # verify no unexpected files
git commit -m "feat: complete oneMem v0.1.0 plugin implementation" --allow-empty-message || echo "nothing to commit"
```
