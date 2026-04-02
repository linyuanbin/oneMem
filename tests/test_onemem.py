import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

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

    def test_env_var_overrides_default_path(self):
        cfg = {"powermem_url": "http://env-override.example.com", "api_key": "envkey"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        try:
            with patch.dict(os.environ, {"ONEMEM_CONFIG": path}):
                result = onemem.load_config()  # no path argument — uses env var
            self.assertEqual(result["powermem_url"], "http://env-override.example.com")
            self.assertEqual(result["api_key"], "envkey")
        finally:
            os.unlink(path)

    def test_returns_none_when_json_invalid(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ not valid json }")
            path = f.name
        try:
            result = onemem.load_config(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)


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


class TestPowerMemSearch(unittest.TestCase):

    def _make_response(self, body_dict, status=200):
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


if __name__ == "__main__":
    unittest.main()
