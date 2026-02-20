"""Validate root mkdocs.yml navigation references.

Checks that all markdown files referenced in mkdocs.yml nav actually exist
in the docs/ directory. Prints warnings for missing files. Does NOT modify
mkdocs.yml -- the nav is hand-maintained.

Called by: make docs-nav-update
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
MKDOCS_YML = ROOT / "mkdocs.yml"


def main() -> None:
    content = MKDOCS_YML.read_text()

    # Extract .md file references from nav (match only the filename path, not the label)
    md_refs = re.findall(r":\s+(\S+\.md)\s*$", content, re.MULTILINE)

    missing = []
    for ref in md_refs:
        ref = ref.strip()
        path = DOCS_DIR / ref
        if not path.exists():
            missing.append(ref)

    if missing:
        print(f"WARNING: {len(missing)} nav reference(s) have no file yet:")
        for m in missing:
            print(f"  - docs/{m}")
    else:
        print("All nav references resolve to existing files.")


if __name__ == "__main__":
    main()
