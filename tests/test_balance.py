import json
import errno
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import context
from cc_balance_widget import balance


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "cc.db"
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("CREATE TABLE providers(id TEXT, app_type TEXT, name TEXT, settings_config TEXT, meta TEXT)")
            for app in ("codex", "claude"):
                settings = ({"auth": {"OPENAI_API_KEY": app},
                             "config": 'model_provider="icu"\n[model_providers.icu]\nbase_url="https://example.com"'}
                            if app == "codex" else
                            {"env": {"ANTHROPIC_BASE_URL": "https://example.com", "ANTHROPIC_AUTH_TOKEN": app}})
                con.execute("INSERT INTO providers VALUES(?,?,?,?,?)",
                            (app, app, "OpenRouter ICU", json.dumps(settings),
                             json.dumps({"usage_script": {"enabled": True, "code": "({})", "timeout": 10}})))
            con.execute("INSERT INTO providers VALUES(?,?,?,?,?)", ("other", "claude", "Other", "{}", "{}"))

    def test_exact_app_selection(self):
        for app in ("claude", "codex"):
            data = balance.load_provider(self.db, app)
            self.assertEqual(data["apiKey"], app)
            self.assertEqual(data["baseUrl"], "https://example.com")
            self.assertEqual(data["code"], "({})")

    def test_duplicate_rejected(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("INSERT INTO providers SELECT * FROM providers WHERE app_type='claude' AND name='OpenRouter ICU'")
        with self.assertRaises(balance.QueryError):
            balance.load_provider(self.db, "claude")

    def test_missing_database_not_created(self):
        path = Path(self.tmp.name) / "absent.db"
        with self.assertRaises(balance.QueryError):
            balance.load_provider(path, "claude")
        self.assertFalse(path.exists())

    def test_disabled_script_rejected(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE providers SET meta='{}' WHERE app_type='claude'")
        with self.assertRaises(balance.QueryError):
            balance.load_provider(self.db, "claude")

    def test_usd_zero(self):
        self.assertEqual(balance.usd_remaining({"remaining": 0, "unit": "USD"}), 0)

    def test_reject_ambiguous_or_invalid_amount(self):
        for value in ({"remaining": True, "unit": "USD"},
                      {"remaining": float("nan"), "unit": "USD"},
                      {"remaining": 10**400, "unit": "USD"},
                      {"remaining": 10, "unit": "CNY"},
                      {"used": 1, "unit": "USD"},
                      [{"remaining": 1, "unit": "USD"}, {"remaining": 2, "unit": "USD"}]):
            with self.subTest(value=value), self.assertRaises(balance.QueryError):
                balance.usd_remaining(value)

    def test_independent_failures_preserve_old_value(self):
        state = {"balances": {"claude": 79.34, "codex": 89.61}}
        balance.merge_results(state, {"claude": {"error": "failed"}, "codex": {"value": 0, "provider_id": "codex"}})
        self.assertEqual(state["balances"], {"claude": 79.34, "codex": 0})

    def test_reset_rollover(self):
        self.assertEqual(balance.countdown("00:00:00", datetime(2026, 9, 15, 23, 59, 59)), "00:00:01")
        self.assertEqual(balance.countdown("00:00:00", datetime(2026, 9, 16, 0, 0, 0)), "24:00:00")
        self.assertEqual(balance.countdown("08:00:00", datetime(2026, 9, 15, 1, 36, 19)), "06:23:41")

    def test_beijing_reset_from_moscow(self):
        moscow = timezone(timedelta(hours=3))
        self.assertEqual(balance.countdown("00:00:00", datetime(2026, 9, 15, 16, 30, tzinfo=moscow)), "02:30:00")
        self.assertEqual(balance.countdown("00:00:00", datetime(2026, 9, 15, 19, 0, tzinfo=moscow)), "24:00:00")

    def test_atomic_state_roundtrip(self):
        path = Path(self.tmp.name) / "state.json"
        data = balance.load_state(path)
        data["reset"] = "12:34:56"
        data["position"] = [-300, 300]
        balance.save_state(path, data)
        self.assertEqual(balance.load_state(path)["position"], [-300, 300])
        self.assertEqual(balance.load_state(path)["reset"], "12:34:56")

    def test_cross_volume_redirect_save(self):
        path = Path(self.tmp.name) / "state.json"
        state = balance.load_state(path)
        state["position"] = [123, 456]
        with patch.object(balance.os, "replace", side_effect=OSError(errno.EXDEV, "Cross-device link")):
            balance.save_state(path, state)
        self.assertEqual(balance.load_state(path)["position"], [123, 456])

    def test_bad_state_defaults(self):
        path = Path(self.tmp.name) / "state.json"
        path.write_text('{"reset":"bad","balances":{"claude":true},"position":["bad",null]}', encoding="utf-8")
        state = balance.load_state(path)
        self.assertEqual(state["reset"], "00:00:00")
        self.assertIsNone(state["balances"]["claude"])
        self.assertIsNone(state["position"])

    def test_invalid_color_defaults(self):
        path = Path(self.tmp.name) / "state.json"
        for value in (None, "", "bad", 12, "#fff", "#gg0000"):
            path.write_text(json.dumps({"color": value}), encoding="utf-8")
            self.assertEqual(balance.load_state(path)["color"], "#ff3030")

    def test_select_by_id_and_reject_cross_app(self):
        data = balance.load_provider(self.db, "claude", "claude")
        self.assertEqual(data["provider_id"], "claude")
        with self.assertRaises(balance.QueryError):
            balance.load_provider(self.db, "claude", "codex")

    def test_list_providers_excludes_credentials(self):
        rows = balance.list_providers(self.db)
        self.assertEqual(len(rows["claude"]), 2)
        self.assertEqual(set(rows["claude"][0]), {"id", "name", "enabled"})
        self.assertNotIn("apiKey", json.dumps(rows))

    def test_identity_cache_and_corrupt_legacy_balance(self):
        state = balance.default_state()
        first = {"database": str(self.db), "providers": {"claude": "claude", "codex": "codex"}}
        balance.set_sources(state, first)
        balance.merge_results(state, {"claude": {"value": 12, "provider_id": "claude"}})
        second = {"database": str(self.db), "providers": {"claude": "other", "codex": "codex"}}
        balance.set_sources(state, second)
        self.assertIsNone(state["balances"]["claude"])
        balance.set_sources(state, first)
        self.assertEqual(state["balances"]["claude"], 12)
        balance.set_sources(state, {**first, "database": str(self.db.with_name("another.db"))})
        self.assertIsNone(state["balances"]["claude"])

    def test_corrupt_nested_settings_do_not_crash(self):
        path = Path(self.tmp.name) / "state.json"
        for data in ({"cache": None, "sources": []}, {"errors": [], "last_success": "bad"},
                     {"sources": {"database": None, "providers": 5}}):
            path.write_text(json.dumps(data), encoding="utf-8")
            state = balance.load_state(path)
            self.assertIsInstance(state["sources"]["providers"], dict)
            self.assertEqual(state["balances"], {"claude": None, "codex": None})

    def test_unused_nonfinite_cache_is_discarded(self):
        path = Path(self.tmp.name) / "state.json"
        path.write_text(json.dumps({"cache": {
            str(i) * 64: {"value": value}
            for i, value in enumerate((float("nan"), float("inf"), 10**400))
        }}), encoding="utf-8")
        state = balance.load_state(path)
        self.assertEqual(state["cache"], {})
        balance.save_state(path, state)

    def test_query_errors_do_not_leak_runner_stderr(self):
        import subprocess
        fake = subprocess.CompletedProcess([], 1, "", "secret credential in unexpected stderr")
        with patch.object(balance.subprocess, "run", return_value=fake):
            with self.assertRaises(balance.QueryError) as error:
                balance.query("claude", self.db)
        self.assertNotIn("secret", str(error.exception))

    def test_locked_db_fails_without_mutation(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("BEGIN EXCLUSIVE")
            try:
                with self.assertRaises(balance.QueryError):
                    balance.load_provider(self.db, "claude")
            finally:
                con.rollback()


if __name__ == "__main__":
    unittest.main()
