import gc
import unittest
from unittest.mock import Mock, patch

import context
from cc_balance_widget import balance
from cc_balance_widget.sources_dialog import SourcesDialog
import test_balance


class SourcesDialogTests(unittest.TestCase):
    """Synthetic database only; dialogs never call the supplier."""

    def setUp(self):
        gc.collect()
        test_balance.BalanceTests.setUp(self)
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.saved = Mock()
        self.dialog = SourcesDialog(self.root, {
            "database": str(self.db), "providers": {"claude": "claude", "codex": "codex"}
        }, self.saved)
        self.root.update()

    def test_selects_and_saves_exact_ids(self):
        with patch.object(balance, "query_all", side_effect=AssertionError("Network not allowed")):
            self.dialog.save()
        self.saved.assert_called_once_with({
            "database": str(self.db), "providers": {"claude": "claude", "codex": "codex"}
        })

    def test_modified_database_requires_reload(self):
        self.dialog.path.set(str(self.db.with_name("elsewhere.db")))
        self.dialog.save()
        self.saved.assert_not_called()
        self.assertTrue(self.dialog.status.get())

    def test_missing_database_is_error_not_created(self):
        path = self.db.with_name("missing.db")
        self.dialog.path.set(str(path))
        self.dialog.load()
        self.dialog.save()
        self.saved.assert_not_called()
        self.assertFalse(path.exists())

    def test_disabled_provider_not_saved(self):
        rows = self.dialog.rows["claude"]
        index = next(i for i, row in enumerate(rows) if row["id"] == "other")
        self.dialog.boxes["claude"].current(index)
        self.dialog.save()
        self.saved.assert_not_called()
