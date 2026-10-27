import json
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core


class ProfileTests(unittest.TestCase):
    def test_key_is_encrypted_and_switch_only_changes_requested_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = root / "settings.json"
            settings.write_text(json.dumps({"permissions": {"allow": ["Read"]},
                                            "env": {"OTHER": "keep", "ANTHROPIC_AUTH_TOKEN": "old"},
                                            "model": "old-model"}), encoding="utf-8")
            with patch.object(core, "APP_DIR", root), patch.object(core, "PROFILES_FILE", root / "profiles.json"), \
                 patch.object(core, "CLAUDE_SETTINGS", settings):
                profile = core.make_profile("备用", "https://gateway.example/v1/", "secret-123",
                                            "claude-test[1m]", "low")
                core.save_profiles([profile])
                saved = (root / "profiles.json").read_text(encoding="utf-8")
                self.assertNotIn("secret-123", saved)
                self.assertEqual(core.decrypt_key(core.load_profiles()[0]["key"]), "secret-123")
                core.activate(profile)
                actual = json.loads(settings.read_text(encoding="utf-8"))
                self.assertEqual(actual["permissions"], {"allow": ["Read"]})
                self.assertEqual(actual["env"]["OTHER"], "keep")
                self.assertEqual(actual["env"]["ANTHROPIC_AUTH_TOKEN"], "secret-123")
                self.assertEqual(actual["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "low")
                self.assertTrue(core.is_active(profile))
                another = core.make_profile("第二组", "https://second.example", "other-secret",
                                            "another-model", "auto")
                core.save_profiles([profile, another])
                self.assertEqual(len(core.load_profiles()), 2)
                core.activate(another)
                self.assertTrue(core.is_active(another))
                self.assertFalse(core.is_active(profile))
                self.assertNotIn("CLAUDE_CODE_EFFORT_LEVEL", core.read_settings()["env"])

    def test_invalid_url_is_rejected(self):
        with self.assertRaises(ValueError):
            core.validate("x", "file:///secret", "key", "model", "auto")
        with self.assertRaisesRegex(ValueError, "Base URL"):
            core.validate("x", "https://maas-api.cn-huabei-1.xf-yun.com/anthropic/v1/messages",
                          "key", "model", "auto")

    def test_gateway_can_be_saved_before_choosing_model(self):
        profile = core.make_profile("new", "https://gateway.example", "key", "", "auto",
                                    require_model=False)
        self.assertEqual(profile["model"], "")
        with self.assertRaises(ValueError):
            core.activate(profile)

    def test_model_list_reads_all_pages_and_deduplicates(self):
        profile = core.make_profile("x", "https://gateway.example/v1", "key", "model", "auto")
        pages = [BytesIO(json.dumps({"data": [{"id": "a"}], "has_more": True,
                                     "last_id": "a"}).encode()),
                 BytesIO(json.dumps({"data": [{"id": "a"}, {"id": "b"}],
                                     "has_more": False}).encode())]
        with patch.object(core, "urlopen", side_effect=pages) as mocked:
            self.assertEqual(core.list_models(profile), ["a", "b"])
            self.assertIn("after_id=a", mocked.call_args_list[1].args[0].full_url)

    def test_xf_maas_uses_documented_candidates_when_model_lists_fail(self):
        profile = core.make_profile("讯飞", core.XF_MAAS_ROOT + "/anthropic",
                                    "key", "", "auto", require_model=False)
        with patch.object(core, "list_models", side_effect=ValueError("HTTP 404")) as listing:
            models, source = core.model_candidates(profile)
        self.assertEqual(models, list(core.XF_SPARK_MODELS))
        self.assertIn("预置及手动候选", source)
        self.assertIn("非完整列表", source)
        self.assertEqual(listing.call_count, 2)
        self.assertEqual(listing.call_args_list[1].args[0]["url"], core.XF_MAAS_ROOT)

    def test_prices_use_only_the_matching_gateway_and_all_public_pages(self):
        self.assertIsNone(core.price_source("https://another.example"))
        self.assertEqual(core.get_model_prices("https://another.example"), {})
        pages = [BytesIO(json.dumps({"code": 0, "data": {"total": 2,
                    "models": [{"id": "a", "input_uncached_price": 2, "output_price": 8}]}}).encode()),
                 BytesIO(json.dumps({"code": 0, "data": {"total": 2,
                    "models": [{"id": "b", "input_uncached_price": 0, "output_price": 0}]}}).encode())]
        with patch.object(core, "urlopen", side_effect=pages) as mocked:
            prices = core.get_model_prices("https://discovery-api.intern-ai.org.cn")
        self.assertEqual(prices, {"a": (2, 8), "b": (0, 0)})
        self.assertIn("page=2", mocked.call_args_list[1].args[0].full_url)
        self.assertNotIn("Authorization", mocked.call_args_list[0].args[0].headers)

    def test_rate_limit_is_not_counted_as_permanent_failure(self):
        self.assertEqual(core.model_status("模型测试未通过：429 Channel rate limit reached"), "限流或拥塞")
        self.assertEqual(core.model_status("模型已实际回复：OK"), "可用")

    def test_batch_check_rejects_reply_from_another_model(self):
        profile = core.make_profile("x", "https://gateway.example", "key", "requested", "auto")

        class FakeProcess:
            returncode = 0

            def communicate(self, timeout):
                return json.dumps({"result": "OK", "is_error": False,
                                   "modelUsage": {"fallback": {}}}), ""

        with tempfile.TemporaryDirectory() as folder, patch.object(core, "APP_DIR", Path(folder)), \
             patch.object(core.shutil, "which", return_value="claude.cmd"), \
             patch.object(core.subprocess, "Popen", return_value=FakeProcess()):
            result = core.check_model(profile, require_model_match=True)
        self.assertIn("实际使用模型为 fallback", result)
        self.assertEqual(core.model_status(result), "失败")

    def test_launch_uses_selected_project_folder(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(core, "find_claude", return_value=r"C:\Tools\claude.cmd"), \
             patch.object(core.shutil, "which", return_value=r"C:\Windows\wt.exe"), \
             patch.object(core.subprocess, "Popen") as launched:
            self.assertEqual(core.launch_claude(folder), "Windows Terminal")
        command = launched.call_args.args[0]
        self.assertIn("-d", command)
        self.assertEqual(command[command.index("-d") + 1], str(Path(folder).resolve()))
        self.assertEqual(command[-3:], ["cmd.exe", "/k", r"C:\Tools\claude.cmd"])

    def test_launch_rejects_missing_folder(self):
        with self.assertRaises(ValueError):
            core.launch_claude(r"Z:\missing-claude-project")


if __name__ == "__main__":
    unittest.main()
