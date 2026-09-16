"""Opt-in real mouse probe. Never run in CI; no credentials/startup changes."""
import argparse
import ctypes
from ctypes import wintypes
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cc_balance_widget.widget import App, raise_without_activation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-input", action="store_true", help="Allow temporary cursor motion on this desktop")
    parser.add_argument("--cycles", type=int, default=10)
    args = parser.parse_args()
    if not args.confirm_input:
        parser.error("This moves your cursor. Use --confirm-input on an idle interactive desktop.")
    user = ctypes.windll.user32
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.WindowFromPoint.argtypes = [wintypes.POINT]
    user.WindowFromPoint.restype = wintypes.HWND
    user.GetForegroundWindow.restype = wintypes.HWND
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    class Mouse(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
    class Union(ctypes.Union):
        _fields_ = [("mouse", Mouse)]
    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("data", Union)]
    user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = wintypes.UINT
    old_cursor = wintypes.POINT()
    user.GetCursorPos(ctypes.byref(old_cursor))
    foreground = user.GetForegroundWindow()
    app = App(demo=True)
    events = []
    for window in (app.root, app.drag_surface):
        window.bind("<ButtonPress-1>", lambda e: events.append(["down", e.x_root, e.y_root]), add=True)
        window.bind("<ButtonRelease-1>", lambda e: events.append(["up", e.x_root, e.y_root]), add=True)
    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.root.update()
            time.sleep(0.008)
    def cursor(x, y):
        if not user.SetCursorPos(x, y):
            raise RuntimeError("SetCursorPos denied; desktop may be locked")
        now = wintypes.POINT()
        user.GetCursorPos(ctypes.byref(now))
        if (now.x, now.y) != (x, y):
            raise RuntimeError(f"Cursor interference or coordinate mismatch: {(now.x, now.y)} != {(x, y)}")
    def mouse(flags):
        data = Input(0, Union(mouse=Mouse(0, 0, 0, flags, 0, 0)))
        if user.SendInput(1, ctypes.byref(data), ctypes.sizeof(data)) != 1:
            raise RuntimeError("SendInput rejected")
    try:
        app.move(200, 220)
        pump(0.8)
        hwnd = user.GetAncestor(app.root.winfo_id(), 2)
        surface = user.GetAncestor(app.drag_surface.winfo_id(), 2)
        for cycle in range(args.cycles):
            x, y = app.root.winfo_x(), app.root.winfo_y()
            origins = [
                (3, 3),
                (app.icon_labels["claude"].winfo_x() + 8, 14),
                (app.icon_labels["codex"].winfo_x() + 8, 14),
                (app.claude_label.winfo_x() + 10, 14),
            ]
            offset_x, offset_y = origins[cycle % len(origins)]
            start = wintypes.POINT(x + offset_x, y + offset_y)
            app.maintain_topmost()
            pump(0.06)
            hit = user.GetAncestor(user.WindowFromPoint(start), 2)
            if hit not in (hwnd, surface):
                raise RuntimeError("Native hit-test missed the demo; no input sent")
            cursor(start.x, start.y)
            mouse(0x0002)
            pump(0.1)
            for delta in range(5, 31, 5):
                cursor(start.x + delta, start.y + delta)
                pump(0.04)
            mouse(0x0004)
            pump(0.12)
            if app.state["position"] != [x + 30, y + 30]:
                raise RuntimeError(f"Drag mismatch: expected {[x+30,y+30]}, got {app.state['position']}; events={events[-4:]}")
            x, y = app.root.winfo_x(), app.root.winfo_y()
            app.maintain_topmost()
            pump(0.04)
            refresh_edges = [(app.button.winfo_x() + 1, 3),
                             (app.root.winfo_width() - 3, 3),
                             (app.button.winfo_x() + 1, app.root.winfo_height() - 3),
                             (app.root.winfo_width() - 3, app.root.winfo_height() - 3)]
            px, py = refresh_edges[cycle % len(refresh_edges)]
            point = wintypes.POINT(x + px, y + py)
            if user.GetAncestor(user.WindowFromPoint(point), 2) not in (hwnd, surface):
                raise RuntimeError("Refresh hit-test missed; no input sent")
            cursor(point.x, point.y)
            mouse(0x0002)
            pump(0.06)
            mouse(0x0004)
            pump(0.06)
            if not app.busy:
                raise RuntimeError("Native refresh click was not received")
            pump(0.55)
            if app.busy:
                raise RuntimeError("Demo query did not complete")
            app.move(200, 220)
            pump(0.06)
        before = user.GetForegroundWindow()
        raise_without_activation(app.root)
        if user.GetForegroundWindow() != before:
            raise RuntimeError("Topmost operation stole foreground focus")
        taskbar = user.FindWindowW("Shell_TrayWnd", None)
        taskbar_activated = bool(user.SetForegroundWindow(taskbar)) if taskbar else False
        pump(0.7)
        window, above = hwnd, False
        while window:
            if window == taskbar:
                above = True
                break
            window = user.GetWindow(window, 2)
        print(json.dumps({"cycles": args.cycles, "native_drag_refresh": "pass",
                          "no_focus_steal": "pass", "taskbar_activation_accepted": taskbar_activated,
                          "above_taskbar": above, "size": app._size}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"native_desktop_probe": "not passed", "reason": str(exc)}, indent=2))
        return 1
    finally:
        try:
            mouse(0x0004)
        finally:
            user.SetCursorPos(old_cursor.x, old_cursor.y)
            app.close()
            if foreground:
                user.SetForegroundWindow(foreground)


if __name__ == "__main__":
    sys.exit(main())
