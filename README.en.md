# CC Balance Widget

A compact, unofficial Windows balance strip for CC Switch.

[中文](README.md) · [Manual acceptance](docs/manual-acceptance.md)

![Synthetic demo balances](docs/images/preview.png)

Claude and Codex icons, two USD balances, a configurable daily reset countdown.
Drag it, change the text color, refresh manually, and optionally enable startup.
No token charts or history dashboard.

This is an independent project, not an official CC Switch, Anthropic, or OpenAI
component. `v0.1.0-beta.1` is a source preview candidate, not a claim that release
acceptance has passed. See [verification status](docs/verification.md).

## Run from source

Windows, Python 3.12+ with Tkinter, and Node.js 22+ are required for real queries.
There are no third-party Python runtime packages. No EXE is provided.

```powershell
.\Start.ps1 -Demo
.\Start.ps1
.\Start.ps1 -Check
```

Demo mode uses fake balances, never reads the provider database, never queries a
supplier, and never reads/writes personal settings or startup entries.
`-Check` without `-Demo` performs real queries but does not print credentials.

If PowerShell policy blocks scripts, use `python run.py --demo` or
`python run.py` without weakening the system-wide execution policy.
Optional editable install: `python -m pip install -e .`, then
`python -m cc_balance_widget --demo`.

## Configure

Right-click the strip and choose **数据源设置** (Data sources). Select a database,
load the list, and select one provider for each app. The default database is
`%USERPROFILE%\.cc-switch\cc-switch.db`; the default provider name in each app
is `OpenRouter ICU`. Explicit selection stores provider IDs, not list positions.
Missing or ambiguous defaults are errors, never guesses.

Refresh occurs on launch and every ten minutes. The right button refreshes
balances, **not** account quotas. Busy queries show dots and do not stack.
Failures preserve each source's last good value; switching sources switches caches.

**修改颜色** changes text color; **设置 Reset 时间** changes the Beijing-time daily
reset target; **查询状态** shows sanitized errors and last-success times.
The countdown defaults to midnight UTC+8 and is **not a supplier-confirmed reset**.

## Trust and privacy

The database is read-only. The app executes the selected provider's existing
JavaScript `request` / `extractor`, not a replacement vendor API implementation.
Only same-origin HTTPS GET without redirects is supported. The extractor must
return one finite numeric `remaining` value with `unit: "USD"`.
OAuth quota flows and multi-plan aggregation are not supported.

Run only trusted local scripts. **Node VM is not a security sandbox.**
Credentials go through memory and stdin, not argv or settings. No added telemetry.
Settings and cached balances live under `%LOCALAPPDATA%\CCBalanceWidget`.
They are not encrypted and include local paths and provider IDs; redact before sharing.

Topmost maintenance is best-effort, not privilege elevation. The near-transparent
hit surface receives mouse input across the strip and is not click-through.
Taskbar menus, secure desktops, full-screen windows, DPI and monitor changes
require separate validation. See [manual acceptance](docs/manual-acceptance.md).

## Development

```powershell
python -m unittest discover -s tests -v
node --test tests/test_usage_runner.cjs
python scripts/check_public_tree.py
```

Tests and Windows CI are offline. Real mouse/taskbar validation is separate.
See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), [CHANGELOG](CHANGELOG.md).

MIT code; brand asset notices and upstream license are in
`src/cc_balance_widget/assets`. CC Switch supplies the data convention and icon
geometry. README presentation references CodexBar, Claude Code Usage Monitor, and
TrafficMonitor; no endorsement is implied.
