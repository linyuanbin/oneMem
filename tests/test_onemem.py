import json
import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
