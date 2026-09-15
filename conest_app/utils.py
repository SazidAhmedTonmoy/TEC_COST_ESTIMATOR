from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"\s+")
NON_SEARCH_RE = re.compile(r"[^a-z0-9]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return SPACE_RE.sub(" ", str(value).replace("\u00a0", " ").strip())


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return SPACE_RE.sub(" ", NON_SEARCH_RE.sub(" ", text)).strip()


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
        if not text or text.upper() in {"N/A", "NA", "TBC", "-"}:
            return default
        try:
            result = float(text)
        except (TypeError, ValueError):
            return default
    return result if math.isfinite(result) else default


def positive_float(value: Any, default: float = 0.0) -> float:
    return max(0.0, as_float(value, default))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def safe_filename(name: str, fallback: str = "workbook.xlsx") -> str:
    base = Path(name or fallback).name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return base or fallback


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def row_to_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None

