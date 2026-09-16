# Verification status

Recorded on **2026-09-16**. This is a candidate source tree, not a published release.

## Local evidence

| Check | Result |
|---|---|
| Python offline suite | 54 tests passed |
| Node offline suite | 6 tests passed |
| Python compilation / JavaScript syntax | Passed |
| Windows PowerShell 5.1 dependency probe | Passed |
| Isolated demo CLI and source launcher | Passed |
| Fresh virtual environment: build wheel, install, load both PNG icons | Passed |
| Actual configured Claude/Codex provider queries | Both succeeded; amounts/IDs/credentials not recorded |
| Public tree scan | No flagged credentials, private paths, databases or shortcuts |
| Native mouse probe | Two successful 10-cycle runs; final run covers blank, both icons and digits, plus refresh padding corners |
| Foreground focus during native topmost operation | Unchanged |
| Taskbar activation then z-order recovery | Passed in this local desktop session |
| GitHub Actions | Definition added; not yet executed in GitHub |

Baseline: Python **3.12.10**, Node **22.18.0**, Windows OS API build
**10.0.26200**. This is not a claim of validation on every Windows 10/11 system.
The final local widget capture is **271×28** logical pixels.

The native probe uses Win32 hit testing and injected mouse input on an isolated
demo window, not Tk synthetic events. It restores cursor location and attempts
to restore foreground focus. It never accesses the real provider DB or startup keys.
Run it only on an idle interactive desktop:

```powershell
python scripts/desktop_probe.py --confirm-input --cycles 10
```

The offline suite separately checks source selection, stale-result discard,
cache identity, missing/locked DBs, invalid caches, refresh single-flight behavior,
color persistence, demo isolation, and menu/dialog topmost guards.
Final review regressions also cover overflowing integer caches and generated
shortcut arguments. Shortcuts use process-scoped execution-policy bypass and
request visible launcher error dialogs; no machine or user policy is changed.

## What still needs human acceptance

- Real interactions with native color/Reset dialogs and the context menu.
- Startup/uninstall in a disposable Windows user account.
- DPI scaling matrix, multiple monitors, alternate/auto-hidden taskbars,
  Explorer restart, full-screen applications.
- Confirm README instructions on another Windows installation.

Keep the repository marked as a development/preview candidate until the required
items in [manual-acceptance.md](manual-acceptance.md) have recorded results.
Do not infer these results from the automated tests, and do not publish a
usable-preview tag while a core interaction is unresolved.

## Presentation media

`docs/images/preview.png` and `demo.gif` are captures of the actual **demo-mode**
widget, placed on an explicitly labelled synthetic taskbar backdrop.
The displayed amounts are **12.34 / 56.78** only. The backdrop is not evidence
of native taskbar rendering or taskbar compatibility.

Regenerate with Pillow installed:

```powershell
python scripts/make_demo_media.py
```

No personal desktop screenshot, real balance, database or credential is included.
