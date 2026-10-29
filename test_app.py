from contextlib import ExitStack
import tempfile
import unittest
from unittest.mock import patch

import app
import core


class SwitcherFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        profiles = [
            core.make_profile("配置一", "https://one.example", "key-one", "model-one", "auto"),
            core.make_profile("配置二", "https://two.example", "key-two", "model-two", "auto"),
        ]
        self.stack.enter_context(patch.object(core, "load_profiles", return_value=profiles))
        self.stack.enter_context(patch.object(core, "save_profiles"))
        self.stack.enter_context(patch.object(core, "read_settings", return_value={}))
        self.stack.enter_context(patch.object(core, "is_active", return_value=False))
        self.load_models = self.stack.enter_context(patch.object(app.Switcher, "_load_models"))
        self.window = app.Switcher()
        self.window.update()
        self.addCleanup(self.window.destroy)

    def test_cancel_switch_keeps_unsaved_changes_and_selection(self):
        self.window.name.set("未保存名称")
        with patch.object(app.messagebox, "askyesno", return_value=False) as prompt:
            self.window.gateway_tree.selection_set("1")
            self.window.update()
        prompt.assert_called_once()
        self.assertEqual(self.window.selected, 0)
        self.assertEqual(self.window.gateway_tree.selection(), ("0",))
        self.assertEqual(self.window.name.get(), "未保存名称")

    def test_revealing_saved_key_does_not_count_as_an_edit(self):
        self.window._toggle_key_visibility()
        self.assertFalse(self.window._has_unsaved_changes())

    def test_new_configuration_loads_its_models_after_saving(self):
        self.window._new()
        self.window.name.set("新配置")
        self.window.url.set("https://three.example")
        self.window.key.set("key-three")
        self.window._save()
        self.window.update()
        self.assertEqual(self.window.selected, 2)
        self.assertEqual(self.load_models.call_args.args[0]["url"], "https://three.example")
        self.assertFalse(self.window._has_unsaved_changes())

    def test_batch_test_prevents_switching_to_another_configuration(self):
        self.window.batch_stop = object()
        self.window.gateway_tree.selection_set("1")
        self.window.update()
        self.assertEqual(self.window.selected, 0)
        self.assertEqual(self.window.gateway_tree.selection(), ("0",))
        self.assertIn("停止模型测试", self.window.status.get())
        self.assertIsNone(self.window._save())

    def test_double_click_sets_current_model(self):
        self.window._set_models(["first", "second"])
        self.window.update()
        bounds = self.window.model_list.bbox(1)
        for _ in range(2):
            self.window.model_list.event_generate("<ButtonPress-1>", x=10, y=bounds[1] + 1)
            self.window.model_list.event_generate("<ButtonRelease-1>", x=10, y=bounds[1] + 1)
        self.window.update()
        self.assertEqual(self.window.model.get(), "second")
        self.assertEqual(self.window.key.get(), "")

    def test_saving_changed_address_loads_new_models(self):
        self.window.url.set("https://changed.example")
        self.window._save()
        self.window.update()
        self.assertEqual(self.load_models.call_args.args[0]["url"], "https://changed.example")
        self.assertFalse(self.window._has_unsaved_changes())

    def test_minimum_size_keeps_main_controls_visible(self):
        self.window.geometry("1050x700")
        self.window.update()
        for widget in (self.window.model_box, self.window.model_list, self.window.batch_button,
                       self.window.interface_button, self.window.model_button, self.window.key_entry):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreaterEqual(widget.winfo_height(), 20)
        self.assertGreaterEqual(self.window.model_list.winfo_height(), 80)
        self.assertLessEqual(self.window.key_entry.master.winfo_height(),
                             self.window.url_entry.winfo_height() + 8)

    def test_repeated_launch_click_is_ignored_until_terminal_opens(self):
        self.window.workdir.set(tempfile.gettempdir())
        profile = self.window.profiles[0]
        with patch.object(core, "find_claude", return_value="claude.cmd"), \
             patch.object(self.window, "_activate", return_value=profile), \
             patch.object(core, "launch_claude", return_value="Windows Terminal") as launch:
            self.window._activate_and_launch()
            self.window._activate_and_launch()
        launch.assert_called_once()
        self.assertTrue(self.window._launch_pending)
        self.assertEqual(str(self.window.launch_button["state"]), "disabled")
        self.window._finish_launch()
        self.assertFalse(self.window._launch_pending)
        self.assertEqual(str(self.window.launch_button["state"]), "normal")


if __name__ == "__main__":
    unittest.main()
