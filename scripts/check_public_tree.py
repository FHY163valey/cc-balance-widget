"""Conservative pre-publication scan. Reports locations, never matched secrets."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "__pycache__", ".artifacts", "build", "dist"}
PATTERNS = [
    ("API key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("personal absolute path", re.compile(r"[A-Z]:[\\/]+Users[\\/]+(?!Public\b|Default\b)[^\\/\s\"']+", re.I)),
]


def scan():
    if (ROOT / ".git").exists():
        output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        paths = [ROOT / name for name in output.decode("utf-8").split("\0") if name]
    else:
        paths = [path for path in ROOT.rglob("*") if path.is_file() and
                 not any(part in SKIP or part.endswith(".egg-info") for part in path.relative_to(ROOT).parts)]
    findings = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".lnk", ".log"} or path.name in {"state.json", "state.tmp", ".env"}:
            findings.append((relative, "local data/artifact"))
        if path.suffix.lower() not in {".py", ".ps1", ".md", ".txt", ".cjs", ".json", ".yml", ".toml"}:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for label, pattern in PATTERNS:
            if pattern.search(text):
                findings.append((relative, label))
    for file, reason in findings:
        print(f"{file}: {reason}")
    print(f"Scanned {len(paths)} files; {len(findings)} findings.")
    return bool(findings)


if __name__ == "__main__":
    sys.exit(scan())
