"""Minimal Windows balance strip. Background workers never call Tk."""
import argparse
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import copy
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import colorchooser, font, messagebox, simpledialog

from . import balance

REFRESH_MS = 600_000
STATE_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CCBalanceWidget" / "state.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "CCSwitchBalanceWidget"
BG = "#010101"
FG = "#ff3030"

def raise_without_activation(root):
    user = ctypes.windll.user32
    user.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user.GetAncestor.restype = ctypes.c_void_p
    user.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user.SetWindowPos.restype = ctypes.c_int
    hwnd = user.GetAncestor(root.winfo_id(), 2)
    # NOMOVE | NOSIZE | NOACTIVATE: restore z-order without disturbing input.
    return bool(user.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x13))


def startup_command(state_path=STATE_PATH):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    entry = Path(__file__).resolve().parents[2] / "run.py"
    command = [str(pythonw)]
    command += [str(entry)] if entry.is_file() else ["-m", "cc_balance_widget"]
    command += ["--state-file", str(Path(state_path).resolve())]
    return subprocess.list2cmdline(command)


def startup_enabled(state_path=STATE_PATH):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
            return value == startup_command(state_path)
    except OSError:
        return False


def set_startup(enabled, state_path=STATE_PATH):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command(state_path))
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


class App:
    def __init__(self, state_path=STATE_PATH, demo=False):
        self.demo = demo
        self.state_path = Path(state_path)
        self.state = balance.default_state() if demo else balance.load_state(self.state_path)
        if demo:
            self.state["balances"] = {"claude": 12.34, "codex": 56.78}
        self.source_revision = 0
        self.results = queue.Queue()
        self.busy = False
        self.refresh_pressed = False
        self.closed = False
        self.color_dialog_open = False
        self.source_dialog = None
        self.demo_timer = None
        self.root = tk.Tk()
        self.root.title("CC Balance Widget" + (" - Demo" if demo else ""))
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self.state["topmost"])
        self.root.attributes("-transparentcolor", BG)
        self.root.configure(background=BG, highlightthickness=0)
        # Nonzero alpha accepts clicks where the color-key window has holes.
        self.drag_surface = tk.Toplevel(self.root)
        self.drag_surface.title("CC Switch Balance Drag")
        self.drag_surface.overrideredirect(True)
        self.drag_surface.configure(background="black", cursor="fleur")
        self.drag_surface.attributes("-alpha", 1 / 255)
        self.drag_surface.attributes("-topmost", self.state["topmost"])
        self.drag_surface.bind("<ButtonPress-1>", self.drag_start)
        self.drag_surface.bind("<B1-Motion>", self.drag_move)
        self.drag_surface.bind("<ButtonRelease-1>", self.save_position)
        self.drag_surface.bind("<Button-3>", self.show_menu)
        self.drag_surface.bind("<Motion>", self.surface_hover)
        self.drag_surface.bind("<Leave>", self.hide_tooltip)
        self.root.bind("<Configure>", self.sync_drag_surface)
        self.ui_font = font.Font(family="Consolas", size=10)
        self.text = tk.StringVar()
        self.claude_text = tk.StringVar()
        self.icon_images = {
            app: tk.PhotoImage(master=self.root, file=str(Path(__file__).parent / "assets" / f"{app}.png"))
            for app in ("claude", "codex")}
        self.icon_labels = {
            app: tk.Label(self.root, image=image, background=BG, borderwidth=0, padx=0, pady=0)
            for app, image in self.icon_images.items()}
        self.icon_labels["claude"].pack(side="left", padx=(3, 2))
        self.claude_label = tk.Label(self.root, textvariable=self.claude_text, font=self.ui_font,
                                    foreground=FG, background=BG, padx=0, pady=3)
        self.claude_label.pack(side="left")
        self.icon_labels["codex"].pack(side="left", padx=(2, 2))
        self.label = tk.Label(self.root, textvariable=self.text, font=self.ui_font,
                              foreground=FG, background=BG, padx=0, pady=3)
        self.label.pack(side="left", fill="both", expand=True)
        self.button = tk.Button(self.root, text="\u21bb", command=self.refresh,
                                font=("Segoe UI Symbol", 13), foreground=FG,
                                background=BG, activebackground=BG, activeforeground=FG,
                                relief="flat", borderwidth=0, highlightthickness=0,
                                cursor="hand2", takefocus=True, width=2, padx=2)
        self.button.pack(side="right", padx=(0, 2), fill="y", before=self.label)
        self.apply_color()
        self.topmost = tk.BooleanVar(value=self.state["topmost"])
        self.autostart = tk.BooleanVar(value=False if demo else startup_enabled(self.state_path))
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="\u7acb\u5373\u5237\u65b0", command=self.refresh)
        self.menu.add_checkbutton(label=self.topmost_label(), variable=self.topmost, command=self.toggle_topmost)
        self.menu.add_checkbutton(label="\u5f00\u673a\u81ea\u542f", variable=self.autostart, command=self.toggle_startup)
        self.menu.add_command(label="\u8bbe\u7f6e Reset \u65f6\u95f4", command=self.set_reset)
        self.menu.add_command(label="\u4fee\u6539\u989c\u8272", command=self.set_color)
        self.menu.add_command(label="\u6570\u636e\u6e90\u8bbe\u7f6e", command=self.set_data_sources,
                              state="disabled" if demo else "normal")
        self.menu.add_command(label="\u67e5\u8be2\u72b6\u6001", command=self.show_status)
        if demo:
            self.menu.entryconfigure(2, state="disabled")
        self.menu.add_separator()
        self.menu.add_command(label="\u9000\u51fa", command=self.close)
        self.tooltip = None
        self.tooltip_timer = None
        self.tooltip_kind = None
        self.button.bind("<Enter>", self.schedule_tooltip)
        self.button.bind("<Leave>", self.hide_tooltip)
        self.button.bind("<ButtonPress-1>", self.hide_tooltip, add=True)
        # Child labels already dispatch through the root bindtag; do not bind twice.
        for target in (self.root,):
            target.bind("<ButtonPress-1>", self.drag_start)
            target.bind("<B1-Motion>", self.drag_move)
            target.bind("<ButtonRelease-1>", self.save_position)
        for target in (self.root,):
            target.bind("<Button-3>", self.show_menu)
        for target in self.icon_labels.values():
            target.bind("<Motion>", self.surface_hover)
            target.bind("<Leave>", self.hide_tooltip)
        self.render()
        self.root.update_idletasks()
        self.position_initial()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_timer = self.root.after(50, self.poll)
        self.tick_timer = self.root.after(1000, self.tick)
        self.refresh_timer = self.root.after(REFRESH_MS, self.scheduled_refresh)
        self.layer_timer = self.root.after(500, self.layer_tick)
        self.refresh()
        self.idle_timer = self.root.after_idle(self.sync_drag_surface)

    def maintain_topmost(self):
        if (not self.closed and not self.color_dialog_open and self.source_dialog is None
                and self.topmost.get() and self.root.grab_current() is None
                and not self.menu.winfo_ismapped()):
            raise_without_activation(self.drag_surface)
            raise_without_activation(self.root)

    def sync_drag_surface(self, event=None):
        if self.closed or not hasattr(self, "label"):
            return
        if event is not None and event.widget is not self.root:
            return
        width = max(1, self.root.winfo_width())
        self.drag_surface.geometry(
            f"{width}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    def layer_tick(self):
        self.maintain_topmost()
        if not self.closed:
            self.layer_timer = self.root.after(500, self.layer_tick)

    def render(self):
        def money(app):
            value = self.state["balances"].get(app)
            return "$--" if value is None else f"${value:.2f}"
        self.claude_text.set(f"{money('claude')}|")
        self.text.set(f"{money('codex')}|Reset {balance.countdown(self.state['reset'])}")
        # Fit normal balances closely; expand only if additional digits need room.
        sample = "$99.99|$99.99|Reset 24:00:00"
        width = max(self.ui_font.measure(sample),
                    self.ui_font.measure(self.claude_text.get() + self.text.get())) + 75
        height = max(28, self.ui_font.metrics("linespace") + 10)
        if getattr(self, "_size", None) != (width, height):
            self._size = width, height
            self.root.geometry(f"{width}x{height}")

    def position_initial(self):
        width, height = self.root.winfo_width(), self.root.winfo_height()
        x, y = self.state["position"] or [60, max(60, self.root.winfo_screenheight() - height - 90)]
        # Keep a saved strip visible after a monitor is unplugged.
        class Rect(ctypes.Structure):
            _fields_ = [(n, ctypes.c_long) for n in ("left", "top", "right", "bottom")]
        rect = Rect(x, y, x + width, y + height)
        if not ctypes.windll.user32.MonitorFromRect(ctypes.byref(rect), 0):
            x, y = 60, 100
        self.move(x, y)

    def move(self, x, y):
        # Tk's +-N form means an absolute negative coordinate, not right anchoring.
        self.root.geometry(f"+{x}+{y}")

    def persist(self):
        if self.demo:
            return
        try:
            self.state.setdefault("errors", {}).pop("storage", None)
            balance.save_state(self.state_path, self.state)
        except (OSError, ValueError, TypeError) as exc:
            self.state.setdefault("errors", {})["storage"] = f"Could not save widget settings ({type(exc).__name__})"

    def refresh(self):
        if self.busy or self.closed:
            return
        self.busy = True
        self.button.configure(state="disabled", text="\u2026")
        self.menu.entryconfigure(0, state="disabled")
        if self.demo:
            self.demo_timer = self.root.after(450, self.finish_demo_refresh)
            return
        results_queue = self.results
        sources = copy.deepcopy(self.state["sources"])
        revision = self.source_revision
        def worker():
            try:
                result = balance.query_all(sources["database"], sources["providers"])
            except Exception:
                result = {app: {"error": "Query failed"} for app in balance.APPS}
            results_queue.put((revision, result))
        threading.Thread(target=worker, daemon=True, name="cc-usage").start()

    def finish_demo_refresh(self):
        self.demo_timer = None
        if self.closed:
            return
        self.state["balances"] = {"claude": 12.34, "codex": 56.78}
        self.busy = False
        self.button.configure(state="normal", text="\u21bb")
        self.menu.entryconfigure(0, state="normal")
        self.render()

    def poll(self):
        if self.closed:
            return
        try:
            revision, result = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.button.configure(state="normal", text="\u21bb")
            self.menu.entryconfigure(0, state="normal")
            if revision == self.source_revision:
                try:
                    balance.merge_results(self.state, result)
                    self.persist()
                    self.render()
                except (balance.QueryError, ValueError, TypeError, KeyError):
                    self.state["errors"]["storage"] = "Invalid query result; please refresh again"
            else:
                self.refresh()
        self.poll_timer = self.root.after(50, self.poll)

    def scheduled_refresh(self):
        self.refresh()
        self.refresh_timer = self.root.after(REFRESH_MS, self.scheduled_refresh)

    def tick(self):
        self.render()
        self.tick_timer = self.root.after(1000, self.tick)

    def in_refresh_area(self, event):
        x = event.x_root - self.root.winfo_x()
        y = event.y_root - self.root.winfo_y()
        return self.button.winfo_x() <= x < self.root.winfo_width() and 0 <= y < self.root.winfo_height()

    def surface_hover(self, event):
        over_button = self.in_refresh_area(event)
        self.drag_surface.configure(cursor="hand2" if over_button else "fleur")
        kind = "refresh" if over_button else None
        for app, label in self.icon_labels.items():
            if (label.winfo_rootx() <= event.x_root < label.winfo_rootx() + label.winfo_width()
                    and label.winfo_rooty() <= event.y_root < label.winfo_rooty() + label.winfo_height()):
                kind = app
        if kind != self.tooltip_kind:
            self.hide_tooltip()
            if kind:
                self.schedule_tooltip(kind=kind)

    def drag_start(self, event):
        if event.widget is self.button:
            return
        self.hide_tooltip()
        self.refresh_pressed = self.in_refresh_area(event)
        if self.refresh_pressed:
            event.widget.grab_set()
            return
        self.drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        event.widget.grab_set()

    def drag_move(self, event):
        if self.refresh_pressed or event.widget is self.button or not hasattr(self, "drag_offset"):
            return
        self.move(event.x_root - self.drag_offset[0], event.y_root - self.drag_offset[1])

    def save_position(self, event=None):
        if event is not None and self.root.grab_current() is not None:
            self.root.grab_current().grab_release()
        if event is not None and self.refresh_pressed:
            self.refresh_pressed = False
            if self.in_refresh_area(event):
                self.refresh()
            return
        self.state["position"] = [self.root.winfo_x(), self.root.winfo_y()]
        self.persist()

    def show_menu(self, event):
        self.hide_tooltip()
        self.autostart.set(False if self.demo else startup_enabled(self.state_path))
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def topmost_label(self):
        return ("\u7f6e\u9876\uff08\u5df2\u5f00\u542f\uff0c\u70b9\u51fb\u5173\u95ed\uff09" if self.topmost.get()
                else "\u7f6e\u9876\uff08\u5df2\u5173\u95ed\uff0c\u70b9\u51fb\u5f00\u542f\uff09")

    def toggle_topmost(self):
        self.state["topmost"] = self.topmost.get()
        self.root.attributes("-topmost", self.topmost.get())
        self.drag_surface.attributes("-topmost", self.topmost.get())
        self.menu.entryconfigure(1, label=self.topmost_label())
        self.maintain_topmost()
        self.persist()

    def toggle_startup(self):
        if self.demo:
            return
        try:
            set_startup(self.autostart.get(), self.state_path)
        except OSError:
            self.autostart.set(startup_enabled(self.state_path))
            messagebox.showerror("CC Switch Balance", "\u65e0\u6cd5\u66f4\u65b0\u5f00\u673a\u542f\u52a8\u9879", parent=self.root)

    def set_reset(self):
        value = simpledialog.askstring(
            "Reset", "\u6bcf\u65e5\u91cd\u7f6e\u65f6\u95f4\uff08\u5317\u4eac\u65f6\u95f4 UTC+8\uff0cHH:MM:SS\uff09",
            initialvalue=self.state["reset"], parent=self.root)
        if value is None:
            return
        if not balance.valid_reset(value.strip()):
            messagebox.showerror("Reset", "\u8bf7\u8f93\u5165 00:00:00 \u81f3 23:59:59", parent=self.root)
            return
        self.state["reset"] = value.strip()
        self.persist()
        self.render()

    def show_status(self):
        lines = []
        for app in balance.APPS:
            last = self.state["last_success"].get(app, "\u5c1a\u65e0\u6210\u529f\u67e5\u8be2")
            error = self.state["errors"].get(app, "")
            lines.append(f"{app.title()}: {last}\n{error or ''}")
        if self.state["errors"].get("storage"):
            lines.append(self.state["errors"]["storage"])
        self.color_dialog_open = True
        try:
            messagebox.showinfo("\u67e5\u8be2\u72b6\u6001", "\n\n".join(lines), parent=self.root)
        finally:
            self.color_dialog_open = False

    def change_sources(self, sources):
        self.source_revision += 1
        balance.set_sources(self.state, sources)
        self.persist()
        self.render()
        self.refresh()

    def set_data_sources(self):
        if self.demo or self.source_dialog is not None:
            return
        from .sources_dialog import SourcesDialog
        self.hide_tooltip()
        self.source_dialog = SourcesDialog(self.root, self.state["sources"], self.change_sources)
        try:
            self.root.wait_window(self.source_dialog.window)
        finally:
            self.source_dialog = None

    def apply_color(self):
        color = self.state["color"]
        # Keep every selectable text color distinct from the transparency key.
        background = "#020202" if color == BG else BG
        self.root.attributes("-transparentcolor", background)
        self.root.configure(background=background)
        self.label.configure(foreground=color, background=background)
        self.claude_label.configure(foreground=color, background=background)
        for label in self.icon_labels.values():
            label.configure(background=background)
        self.button.configure(foreground=color, activeforeground=color,
                              disabledforeground=color, background=background,
                              activebackground=background)

    def set_color(self):
        self.hide_tooltip()
        self.color_dialog_open = True
        try:
            _, color = colorchooser.askcolor(
                color=self.state["color"], title="\u4fee\u6539\u989c\u8272",
                parent=self.root)
        finally:
            self.color_dialog_open = False
        if color is not None:
            self.state["color"] = color.lower()
            self.apply_color()
            self.persist()

    def schedule_tooltip(self, event=None, kind="refresh"):
        self.hide_tooltip()
        self.tooltip_kind = kind
        self.tooltip_timer = self.root.after(500, self.show_tooltip)

    def show_tooltip(self):
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
        self.tooltip_timer = None
        if self.closed:
            return
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        self.tooltip.attributes("-topmost", True)
        lines = ["\u6b63\u5728\u5237\u65b0\u4f59\u989d\u2026" if self.busy else "\u7acb\u5373\u5237\u65b0\u4f59\u989d"]
        if self.tooltip_kind in self.icon_labels:
            lines = [self.tooltip_kind.title()]
        else:
            for app in balance.APPS:
                if self.state.get("errors", {}).get(app):
                    lines.append(f"{app.title()}: \u67e5\u8be2\u5931\u8d25\uff0c\u4fdd\u7559\u4e0a\u6b21\u6570\u503c")
        tk.Label(self.tooltip, text="\n".join(lines), bg="#ffffe1", fg="#202124", padx=6, pady=4).pack()
        self.tooltip.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() - self.tooltip.winfo_width()
        y = max(0, self.root.winfo_y() - self.tooltip.winfo_height() - 4)
        self.tooltip.geometry(f"+{x}+{y}")

    def hide_tooltip(self, event=None):
        self.tooltip_kind = None
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def close(self):
        if self.closed:
            return
        self.save_position()
        self.closed = True
        self.hide_tooltip()
        for timer in (self.poll_timer, self.tick_timer, self.refresh_timer, self.layer_timer,
                      self.idle_timer, self.demo_timer):
            if timer:
                self.root.after_cancel(timer)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--demo", action="store_true", help="No database, network, real settings or startup changes")
    parser.add_argument("--state-file", type=Path, default=STATE_PATH, help="Alternate local settings file")
    args = parser.parse_args()
    if args.check:
        if args.demo:
            print(json.dumps({"claude": {"value": 12.34}, "codex": {"value": 56.78}}))
            return 0
        state = balance.load_state(args.state_file)
        sources = state["sources"]
        results = balance.query_all(sources["database"], sources["providers"])
        print(json.dumps(results, indent=2))
        return 1 if any("error" in value for value in results.values()) else 0
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex_name = "Local\\CCBalanceWidget" + ("Demo" if args.demo else "")
    mutex = kernel.CreateMutexW(None, False, mutex_name)
    if kernel.GetLastError() == 183:
        kernel.CloseHandle(ctypes.c_void_p(mutex))
        return 0
    try:
        App(state_path=args.state_file, demo=args.demo).root.mainloop()
    finally:
        kernel.CloseHandle(ctypes.c_void_p(mutex))
    return 0


if __name__ == "__main__":
    sys.exit(main())
