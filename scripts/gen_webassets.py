#!/usr/bin/env python3
"""Генерирует crm/webassets.py с встроенными фронтенд-ассетами (repr-литералы)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
assets = [
    ("INDEX_HTML", ROOT / "crm" / "templates" / "index.html"),
    ("APP_JS", ROOT / "crm" / "static" / "app.js"),
    ("STYLE_CSS", ROOT / "crm" / "static" / "style.css"),
]

lines = ['"""Встроенные ассеты фронтенда (не зависят от файлов на диске)."""', ""]
for name, path in assets:
    content = path.read_text(encoding="utf-8")
    lines.append(f"{name} = {content!r}")
    lines.append("")

target = ROOT / "crm" / "webassets.py"
target.write_text("\n".join(lines), encoding="utf-8")
print(f"generated {target} ({target.stat().st_size} bytes)")
