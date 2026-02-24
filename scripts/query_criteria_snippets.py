#!/usr/bin/env python3
"""Query the database for criteria text matching given substrings.

Useful to get exact criterion text for adding to test_snippets.json.
Usage: set -a && source .env && set +a && uv run python scripts/query_criteria_snippets.py
"""

from __future__ import annotations

import os
import sys
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import create_engine


def get_engine() -> Engine:
    """Create DB engine from DATABASE_URL."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print(
            "DATABASE_URL not set. Set env (e.g. source .env) and retry.",
            file=sys.stderr,
        )
        sys.exit(1)
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, connect_args=connect_args, echo=False)


def main() -> int:
    engine = get_engine()
    is_postgres = "postgresql" in (os.getenv("DATABASE_URL") or "")

    # Substrings we care about (venous blood, non-pregnant)
    patterns = ["venous blood", "non-pregnant"]
    if is_postgres:
        condition = " OR ".join(f"c.text ILIKE :p{i}" for i in range(len(patterns)))
        params = {f"p{i}": f"%{p}%" for i, p in enumerate(patterns)}
    else:
        condition = " OR ".join(f"c.text LIKE :p{i}" for i in range(len(patterns)))
        params = {f"p{i}": f"%{p}%" for i, p in enumerate(patterns)}

    sql = f"SELECT c.id, c.text FROM criteria c WHERE {condition}"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    if not rows:
        print("No criteria found. Use fallback text from the plan.")
        return 0

    for row in rows:
        print(f"id: {row[0]}")
        print(f"text: {row[1]}")
        print("---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
