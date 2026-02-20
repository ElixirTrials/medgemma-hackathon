"""Generate docs/components/index.md from workspace member directories.

Scans services/, libs/, and apps/ for component directories and writes
a summary page with links to each component's docs (if present).

Called by: make docs-components-gen
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs" / "components"

COMPONENT_DIRS = [
    ("Services", ROOT / "services"),
    ("Libraries", ROOT / "libs"),
    ("Applications", ROOT / "apps"),
]


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / "index.md"

    lines: list[str] = [
        "# Components Overview",
        "",
        "Auto-generated list of workspace components.",
        "",
    ]

    for section_name, base_dir in COMPONENT_DIRS:
        if not base_dir.is_dir():
            continue
        children = sorted(
            p for p in base_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        if not children:
            continue

        lines.append(f"## {section_name}")
        lines.append("")
        lines.append("| Component | Has Docs | pyproject.toml |")
        lines.append("|-----------|----------|----------------|")

        for child in children:
            has_docs = (child / "docs").is_dir()
            has_pyproj = (child / "pyproject.toml").is_file()
            has_pkg = (child / "package.json").is_file()
            config = "yes" if (has_pyproj or has_pkg) else "no"
            docs_status = "yes" if has_docs else "no"
            rel = os.path.relpath(child, ROOT)
            lines.append(f"| `{rel}` | {docs_status} | {config} |")

        lines.append("")

    out.write_text("\n".join(lines) + "\n")
    print(f"Generated {out}")


if __name__ == "__main__":
    main()
