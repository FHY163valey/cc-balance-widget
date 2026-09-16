"""Choose provider IDs; never show or edit credentials."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import balance


class SourcesDialog:
    def __init__(self, parent, sources, on_save):
        self.sources = sources
        self.on_save = on_save
        self.rows = {app: [] for app in balance.APPS}
        self.loaded_path = None
        self.window = tk.Toplevel(parent)
        self.window.title("\u6570\u636e\u6e90\u8bbe\u7f6e")
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="CC Switch \u6570\u636e\u5e93").grid(row=0, column=0, sticky="w")
        self.path = tk.StringVar(value=sources["database"])
        ttk.Entry(frame, textvariable=self.path, width=58).grid(row=1, column=0, columnspan=2, pady=(4, 10))
        ttk.Button(frame, text="\u6d4f\u89c8", command=self.browse).grid(row=1, column=2, padx=(6, 0))
        self.boxes = {}
        for index, app in enumerate(balance.APPS):
            ttk.Label(frame, text=app.title()).grid(row=2 + index * 2, column=0, sticky="w")
            box = ttk.Combobox(frame, state="readonly", width=67)
            box.grid(row=3 + index * 2, column=0, columnspan=3, pady=(4, 10))
            self.boxes[app] = box
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=480).grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Button(frame, text="\u8bfb\u53d6\u5217\u8868", command=self.load).grid(row=7, column=0, pady=(12, 0))
        ttk.Button(frame, text="\u53d6\u6d88", command=self.window.destroy).grid(row=7, column=1, pady=(12, 0))
        ttk.Button(frame, text="\u4fdd\u5b58", command=self.save).grid(row=7, column=2, pady=(12, 0))
        self.window.update_idletasks()
        self.window.grab_set()
        self.load()

    def browse(self):
        path = filedialog.askopenfilename(parent=self.window, title="CC Switch database",
                                         filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if path:
            self.path.set(path)
            self.load()

    def load(self):
        self.loaded_path = None
        for box in self.boxes.values():
            box.set("")
            box["values"] = ()
        try:
            self.rows = balance.list_providers(self.path.get())
        except balance.QueryError as exc:
            self.status.set(str(exc))
            return
        self.loaded_path = self.path.get()
        for app, rows in self.rows.items():
            self.boxes[app]["values"] = [
                f"{row['name']} [{row['id']}]" + ("" if row["enabled"] else " (\u811a\u672c\u672a\u542f\u7528)")
                for row in rows]
            candidates = [i for i, row in enumerate(rows)
                          if row["id"] == self.sources["providers"].get(app)]
            if not candidates:
                candidates = [i for i, row in enumerate(rows) if row["name"] == "OpenRouter ICU"]
            if len(candidates) == 1:
                self.boxes[app].current(candidates[0])
        self.status.set("\u4ec5\u8fd0\u884c\u4f60\u4fe1\u4efb\u7684\u672c\u5730 usage \u811a\u672c\uff1b\u9700\u8fd4\u56de\u5355\u9879 USD remaining\u3002")

    def save(self):
        if self.loaded_path != self.path.get():
            self.status.set("\u6570\u636e\u5e93\u8def\u5f84\u5df2\u53d8\u66f4\uff0c\u8bf7\u5148\u8bfb\u53d6\u5217\u8868\u3002")
            return
        selected = {}
        try:
            for app in balance.APPS:
                index = self.boxes[app].current()
                if index < 0:
                    raise balance.QueryError("Select a provider for " + app)
                row = self.rows[app][index]
                # Validate stored configuration without making any network request.
                balance.load_provider(self.loaded_path, app, row["id"])
                selected[app] = row["id"]
        except balance.QueryError as exc:
            self.status.set(str(exc))
            return
        self.on_save({"database": self.loaded_path, "providers": selected})
        self.window.destroy()
