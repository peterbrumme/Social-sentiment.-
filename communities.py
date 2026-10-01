"""Load a builder's community names from a CSV (CommunityName column) or a text file (one per line)."""
from __future__ import annotations

import csv
import re
from pathlib import Path


def parent_name(name: str) -> str:
    """'Yaupon Trails - The Executive Collection' -> 'Yaupon Trails' (Google lists the parent community)."""
    return re.split(r"\s+[-–—]\s+", name.strip(), maxsplit=1)[0].strip()


def load_communities(path: str) -> list[str]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"communities file not found: {p}")
    names: list[str] = []
    if p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            col = next((c for c in (reader.fieldnames or []) if c.strip().lower().replace(" ", "") in ("communityname", "community")), None)
            if not col:
                raise ValueError(f"no 'CommunityName' column in {p.name}; columns: {reader.fieldnames}")
            names = [row[col] for row in reader if (row.get(col) or "").strip()]
    else:
        names = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    seen: dict[str, str] = {}
    for n in names:
        parent = parent_name(n)
        seen.setdefault(re.sub(r"[^a-z0-9]", "", parent.lower()), parent)   # dedupe case/punctuation variants
    return sorted(seen.values())
