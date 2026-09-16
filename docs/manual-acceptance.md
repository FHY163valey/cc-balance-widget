# Windows desktop acceptance

Run separately from CI in an interactive desktop session. Do not test with real
credentials or change real startup settings. Use `Start.ps1 -Demo`, and temporary
synthetic databases for the data-source dialog.

Record Windows build, Python/Node versions, display resolution/DPI, monitor count,
taskbar position and auto-hide state. Restore cursor position and foreground window
after any native input automation. Do not count Tk `event_generate` as physical input.

## Required before a usable preview release

- [ ] Drag from both icons, a digit and a blank region; release saves position.
- [ ] Repeat native-input drag/refresh cycles ten times without missed clicks.
- [ ] Click refresh glyph and all padding edges; one request, no accidental dragging.
- [ ] During a slow query, drag, countdown and context menu remain responsive.
- [ ] Menu, color picker and Reset dialog are visible, operable and cancellable.
- [ ] Data source dialog handles invalid/locked DB, missing provider and disabled script.
- [ ] Switching DB/provider never displays an unrelated cached amount or old in-flight result.
- [ ] Activate the taskbar; enabled topmost recovers without changing foreground focus.
- [ ] Toggle topmost off and on; label/state/behavior agree.
- [ ] Changing color does not hide text or change brand icon colors.
- [ ] Restart with an isolated state file: settings and valid source cache survive.
- [ ] Simulated persistence errors remain visible in Query status.
- [ ] Missing Python/Node/Tk dependencies fail with actionable startup messages.

## Separate compatibility checks (do not imply tested unless recorded)

- [ ] 100%, 125%, 150% scaling.
- [ ] Multiple monitors, negative screen coordinates, unplugged saved monitor.
- [ ] Bottom/top/side taskbars and auto-hide.
- [ ] Taskbar menus, full-screen apps and Explorer restart.
- [ ] Current-user startup and uninstall in a disposable Windows user account.

Protected system interfaces may cover the strip. No security bypass is expected.
If essential drag/refresh checks remain unstable, publish only a development
repository and do not create a usable-preview tag/release.
