# Contributing

Keep the strip small: two app balances and a configurable reset countdown.
Do not add vendor-specific API implementations, analytics, or unrelated dashboards.

1. Use Python 3.12 and Node 22 as the baseline.
2. Add a failing offline test for behavior changes. Never use a personal API key
   or database in tests, snapshots, fixtures, or CI.
3. Run `python -m unittest discover -s tests -v`,
   `node --test tests/test_usage_runner.cjs`, and `python scripts/check_public_tree.py`.
4. For window/input changes, run the manual acceptance checklist in an interactive
   Windows session. State which DPI and taskbar setup were tested.
5. Describe user-facing behavior, failure handling and verification in the PR.

Source is in `src/cc_balance_widget`, tests in `tests`, developer utilities in
`scripts`. Runtime has no third-party Python packages; Pillow is only needed to
rebuild presentation media (`python -m pip install Pillow`).

Development screenshots must come from `--demo`; never submit real balances,
credentials, provider IDs, full database files, startup shortcuts or personal paths.
Do not claim broad Windows compatibility from a single successful test run.
