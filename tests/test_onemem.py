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
