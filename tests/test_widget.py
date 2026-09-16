import tempfile
import time
import threading
import gc
import unittest
from pathlib import Path
from unittest.mock import patch

import context
from cc_balance_widget import widget


class WidgetTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.json"
        self.patch = patch("cc_balance_widget.widget.balance.query_all", return_value={
            "claude": {"value": 79.34, "provider_id": "claude"},
            "codex": {"value": 89.61, "provider_id": "codex"},
        })
        self.query = self.patch.start()
        self.addCleanup(self.patch.stop)
        startup = patch.object(widget, "startup_enabled", return_value=False)
        startup.start()
        self.addCleanup(startup.stop)
        self.app = widget.App(state_path=self.path)
        self.addCleanup(self.app.close)

    def pump(self):
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            self.app.root.update()
            time.sleep(0.01)

    def test_startup_refresh_and_no_overlap(self):
        self.app.refresh()
        self.pump()
        self.assertEqual(self.query.call_count, 1)
        self.assertEqual(self.app.claude_text.get(), "$79.34|")
        self.assertIn("$89.61|Reset ", self.app.text.get())
        self.assertEqual(self.app.button.cget("state"), "normal")

    def test_button_refresh(self):
        self.pump()
        self.app.button.invoke()
        self.pump()
        self.assertEqual(self.query.call_count, 2)

    def test_blank_refresh_area_clicks_without_dragging(self):
        self.pump()
        surface = self.app.drag_surface
        self.assertEqual(surface.winfo_width(), self.app.root.winfo_width())
        x, y = self.app.root.winfo_x(), self.app.root.winfo_y()
        px = x + self.app.root.winfo_width() - 3
        surface.event_generate("<ButtonPress-1>", rootx=px, rooty=y+3)
        surface.event_generate("<ButtonRelease-1>", rootx=px, rooty=y+3)
        self.pump()
        self.assertEqual(self.query.call_count, 2)
        self.assertEqual([self.app.root.winfo_x(), self.app.root.winfo_y()], [x, y])

    def test_slow_refresh_shows_busy_and_keeps_ui_responsive(self):
        self.pump()
        release = threading.Event()
        self.query.side_effect = lambda *_: (release.wait(3), {})[1]
        original_width = self.app.root.winfo_width()
        try:
            self.app.button.invoke()
            self.assertEqual(self.app.button.cget("text"), "\u2026")
            self.pump()
            self.assertTrue(self.app.busy)
            self.assertEqual(self.app.root.winfo_width(), original_width)
            self.app.refresh()
            self.assertEqual(self.query.call_count, 2)
        finally:
            release.set()
            self.pump()
        self.assertEqual(self.app.button.cget("text"), "\u21bb")

    def test_refresh_interval(self):
        self.assertEqual(widget.REFRESH_MS, 600000)
        self.assertIsNotNone(self.app.refresh_timer)

    def test_scheduled_refresh_rearms_ten_minutes(self):
        self.pump()
        original = self.app.refresh_timer
        with patch.object(self.app.root, "after", return_value=original) as schedule:
            self.app.scheduled_refresh()
            schedule.assert_called_once_with(600000, self.app.scheduled_refresh)
        self.pump()
        self.assertEqual(self.query.call_count, 2)

    def test_failed_refresh_keeps_each_balance(self):
        self.pump()
        self.query.return_value = {"claude": {"error": "offline"},
                                  "codex": {"value": 80.0, "provider_id": "codex"}}
        self.app.button.invoke()
        self.pump()
        self.assertEqual(self.app.state["balances"], {"claude": 79.34, "codex": 80.0})

    def test_layout_and_topmost(self):
        self.pump()
        self.assertTrue(self.app.root.attributes("-topmost"))
        self.assertLessEqual(self.app.label.winfo_x() + self.app.label.winfo_width(), self.app.button.winfo_x())
        self.assertLessEqual(self.app.button.winfo_x() + self.app.button.winfo_width(), self.app.root.winfo_width())

    def test_tighter_layout_preserves_font_and_hit_target(self):
        self.pump()
        self.assertEqual(self.app.ui_font.cget("size"), 10)
        self.assertLessEqual(self.app.root.winfo_width(), 325)
        self.assertLessEqual(self.app.root.winfo_height(), 28)
        self.assertGreaterEqual(self.app.button.winfo_width(), 24)
        self.assertGreaterEqual(self.app.button.winfo_height(), 24)
        self.assertGreaterEqual(self.app.label.winfo_width(),
                                self.app.ui_font.measure(self.app.text.get()))

    def test_brand_icons_and_compact_width(self):
        self.pump()
        self.assertEqual(set(self.app.icon_images), {"claude", "codex"})
        for image in self.app.icon_images.values():
            self.assertEqual((image.width(), image.height()), (16, 16))
            self.assertTrue(any(not image.transparency_get(x, y) for x in range(16) for y in range(16)))
            self.assertTrue(image.transparency_get(0, 0))
        self.assertLess(self.app.root.winfo_width(), 290)
        self.assertNotIn("Claude", self.app.claude_text.get())
        self.assertNotIn("Codex", self.app.text.get())
        parts = [self.app.icon_labels["claude"], self.app.claude_label,
                 self.app.icon_labels["codex"], self.app.label, self.app.button]
        for left, right in zip(parts, parts[1:]):
            self.assertLessEqual(left.winfo_x() + left.winfo_width(), right.winfo_x())

    def test_icon_tooltips_use_provider_names(self):
        self.pump()
        from types import SimpleNamespace
        for app in ("claude", "codex"):
            label = self.app.icon_labels[app]
            event = SimpleNamespace(x_root=label.winfo_rootx()+4, y_root=label.winfo_rooty()+4)
            self.app.surface_hover(event)
            self.assertEqual(self.app.tooltip_kind, app)
            self.app.show_tooltip()
            self.assertEqual(self.app.tooltip.winfo_children()[0].cget("text"), app.title())
            self.app.hide_tooltip()

    def test_transparent_red_compact_style(self):
        self.pump()
        self.assertEqual(str(self.app.root.attributes("-transparentcolor")), widget.BG)
        self.assertEqual(self.app.label.cget("foreground"), "#ff3030")
        self.assertEqual(self.app.button.cget("foreground"), "#ff3030")
        self.assertLess(self.app.root.winfo_width(), 380)

    def test_reset_and_position_persist(self):
        with patch("cc_balance_widget.widget.simpledialog.askstring", return_value="08:30:00"):
            self.app.set_reset()
        self.app.root.geometry("+200+220")
        self.pump()
        self.app.save_position()
        state = widget.balance.load_state(self.path)
        self.assertEqual(state["reset"], "08:30:00")
        self.assertEqual(state["position"], [200, 220])

    def test_close_while_refreshing(self):
        self.app.close()
        self.assertTrue(self.app.closed)

    def test_choose_color_updates_and_persists(self):
        with patch("cc_balance_widget.widget.colorchooser.askcolor", return_value=((0, 255, 0), "#00ff00")):
            self.app.set_color()
        self.assertEqual(self.app.label.cget("foreground"), "#00ff00")
        self.assertEqual(self.app.button.cget("foreground"), "#00ff00")
        self.assertEqual(self.app.button.cget("activeforeground"), "#00ff00")
        self.assertEqual(widget.balance.load_state(self.path)["color"], "#00ff00")
        self.app.close()
        self.app = widget.App(state_path=self.path)
        self.addCleanup(self.app.close)
        self.assertEqual(self.app.label.cget("foreground"), "#00ff00")

    def test_cancel_color_keeps_current(self):
        with patch("cc_balance_widget.widget.colorchooser.askcolor", return_value=(None, None)):
            self.app.set_color()
        self.assertEqual(self.app.label.cget("foreground"), "#ff3030")

    def test_color_matching_transparency_key_stays_visible(self):
        with patch("cc_balance_widget.widget.colorchooser.askcolor", return_value=((1, 1, 1), widget.BG)):
            self.app.set_color()
        self.assertNotEqual(str(self.app.root.attributes("-transparentcolor")),
                            self.app.label.cget("foreground"))

    def test_no_layer_raise_during_color_dialog(self):
        def choose(**kwargs):
            with patch("cc_balance_widget.widget.raise_without_activation") as raise_window:
                self.app.maintain_topmost()
                raise_window.assert_not_called()
            return (None, None)
        with patch("cc_balance_widget.widget.colorchooser.askcolor", side_effect=choose):
            self.app.set_color()

    def test_no_layer_raise_while_context_menu_is_visible(self):
        with patch.object(self.app.menu, "winfo_ismapped", return_value=True), \
             patch.object(widget, "raise_without_activation") as raise_window:
            self.app.maintain_topmost()
            raise_window.assert_not_called()

    def test_refresh_button_right_click_opens_one_menu(self):
        self.pump()
        with patch.object(self.app.menu, "tk_popup") as popup:
            self.app.button.event_generate("<Button-3>", x=4, y=4)
            self.app.root.update()
        self.assertEqual(popup.call_count, 1)

    def test_native_topmost_respects_toggle(self):
        with patch("cc_balance_widget.widget.raise_without_activation") as raise_window:
            self.app.maintain_topmost()
            self.assertEqual(raise_window.call_count, 2)
            raise_window.reset_mock()
            self.app.topmost.set(False)
            self.app.maintain_topmost()
            raise_window.assert_not_called()

    def test_topmost_menu_states_are_explicit(self):
        self.assertIn("\u5df2\u5f00\u542f", self.app.menu.entrycget(1, "label"))
        self.app.menu.invoke(1)
        self.assertFalse(self.app.topmost.get())
        self.assertIn("\u70b9\u51fb\u5f00\u542f", self.app.menu.entrycget(1, "label"))
        with patch("cc_balance_widget.widget.raise_without_activation") as raise_window:
            self.app.menu.invoke(1)
            self.assertTrue(self.app.topmost.get())
            self.assertEqual(raise_window.call_count, 2)
        self.assertIn("\u70b9\u51fb\u5173\u95ed", self.app.menu.entrycget(1, "label"))
        self.assertTrue(widget.balance.load_state(self.path)["topmost"])

    def test_drag_surface_receives_blank_area(self):
        self.pump()
        surface = self.app.drag_surface
        self.assertGreater(surface.attributes("-alpha"), 0)
        self.assertLess(surface.attributes("-alpha"), 0.01)
        self.assertEqual(str(surface.attributes("-transparentcolor")), "")
        x, y = self.app.root.winfo_x(), self.app.root.winfo_y()
        surface.event_generate("<ButtonPress-1>", x=3, y=3, rootx=x+3, rooty=y+3)
        surface.event_generate("<B1-Motion>", x=3, y=3, rootx=x+43, rooty=y+33)
        self.pump()
        surface.event_generate("<ButtonRelease-1>", x=3, y=3)
        self.assertEqual(self.app.state["position"], [x+40, y+30])
        self.assertEqual(surface.winfo_x(), x+40)

    def test_demo_never_reads_or_writes_user_data(self):
        self.app.close()
        with patch.object(widget.balance, "load_state", side_effect=AssertionError("read")), \
             patch.object(widget.balance, "save_state", side_effect=AssertionError("write")), \
             patch.object(widget.balance, "query_all", side_effect=AssertionError("network")), \
             patch.object(widget, "startup_enabled", side_effect=AssertionError("startup read")), \
             patch.object(widget, "set_startup", side_effect=AssertionError("startup write")):
            demo = widget.App(demo=True)
            try:
                demo.refresh()
                demo.root.update()
                self.assertEqual(demo.state["balances"], {"claude": 12.34, "codex": 56.78})
                demo.persist()
                demo.toggle_startup()
            finally:
                demo.close()

    def test_source_change_discards_inflight_results(self):
        self.pump()
        self.app.busy = True
        old = self.app.source_revision
        sources = {"database": str(Path(self.tmp.name) / "new.db"),
                   "providers": {"claude": "new-a", "codex": "new-b"}}
        self.app.change_sources(sources)
        self.app.results.put((old, {"claude": {"value": 999, "provider_id": "old"}}))
        self.pump()
        self.assertNotEqual(self.app.state["balances"]["claude"], 999)

    def test_failed_persistence_retains_current_settings(self):
        with patch.object(widget.balance, "save_state", side_effect=PermissionError("denied")):
            self.app.state["color"] = "#abcdef"
            self.app.persist()
        self.assertEqual(self.app.state["color"], "#abcdef")
        self.assertIn("storage", self.app.state["errors"])

    def test_serialization_failure_does_not_stop_polling(self):
        self.app.results.put((self.app.source_revision, {}))
        with patch.object(widget.balance, "save_state", side_effect=ValueError("bad data")):
            self.pump()
        self.assertIn("storage", self.app.state["errors"])
        self.assertIsNotNone(self.app.poll_timer)

    def test_startup_command_preserves_custom_state(self):
        command = widget.startup_command(self.path)
        self.assertIn("--state-file", command)
        self.assertIn(str(self.path.resolve()), command)


if __name__ == "__main__":
    unittest.main()
