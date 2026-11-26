from __future__ import annotations

import re
import sqlite3
from typing import Any

from .catalog import search_catalog
from .utils import as_float, clean_text


def parse_quantity_and_query(text: str) -> tuple[str, float]:
    original = clean_text(text)
    quantity = 1.0
    query = original
    patterns = [
        re.compile(r"\b(?:qty|quantity)\s*[:=]?\s*(\d+(?:\.\d+)?)\b", re.I),
        re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[x×]\s*(.+)$", re.I),
        re.compile(r"^(.+?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*$", re.I),
    ]
    match = patterns[0].search(original)
    if match:
        quantity = as_float(match.group(1), 1.0)
        query = (original[: match.start()] + " " + original[match.end() :]).strip(" ,-:")
    else:
        match = patterns[1].match(original)
        if match:
            quantity = as_float(match.group(1), 1.0)
            query = clean_text(match.group(2))
        else:
            match = patterns[2].match(original)
            if match:
                query = clean_text(match.group(1))
                quantity = as_float(match.group(2), 1.0)
    return query or original, max(0.0, quantity)


def interpret_request(conn: sqlite3.Connection, text: str, limit: int = 12) -> dict[str, Any]:
    query, quantity = parse_quantity_and_query(text)
    candidates = search_catalog(conn, query, limit=max(limit, 12), recent_first=True)
    candidates.sort(key=lambda item: item.get("last_used_at", ""), reverse=True)
    return {
        "original": clean_text(text),
        "query": query,
        "quantity": quantity,
        "method": "local",
        "candidates": candidates[:limit],
        "confidence": _confidence(candidates),
    }


def _confidence(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "none"
    first = float(candidates[0].get("score", 0))
    second = float(candidates[1].get("score", 0)) if len(candidates) > 1 else 0
    if first >= 1000 or first - second >= 300:
        return "high"
    if first >= 550 or first - second >= 140:
        return "medium"
    return "review"
