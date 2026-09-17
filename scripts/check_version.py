from pathlib import Path
import re


root = Path(__file__).resolve().parents[1]
expected = (root / "VERSION").read_text().strip()
files = {
    "backend": root / "backend/app/version.py",
    "frontend": root / "frontend/src/version.js",
    "package": root / "frontend/package.json",
}

for label, path in files.items():
    content = path.read_text()
    if not re.search(rf'(?<![\w.-]){re.escape(expected)}(?![\w.-])', content):
        raise SystemExit(f"Version mismatch in {label}: expected {expected}")

print(f"Version {expected} is synchronized")
