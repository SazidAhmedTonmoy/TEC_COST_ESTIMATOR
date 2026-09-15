from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from .catalog import search_catalog
from .utils import as_float, clean_text


# These are text-capable Gemini models that Google currently lists with a
# Standard Free Tier. Keeping a whitelist prevents the UI from accidentally
# switching this optional reranker to a paid-only model family.
FREE_TIER_GEMINI_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
DEFAULT_GEMINI_MODEL = FREE_TIER_GEMINI_MODELS[0]
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


def _setting_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key IN "
        "('llm_enabled', 'llm_model', 'llm_provider', 'gemini_api_key')"
    ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def _enabled(settings: dict[str, str]) -> bool:
    value = os.environ.get("CONEST_LLM_ENABLED", settings.get("llm_enabled", "0"))
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _model(settings: dict[str, str], override: str | None = None) -> str:
    requested = clean_text(
        override
        or os.environ.get("CONEST_LLM_MODEL")
        or settings.get("llm_model")
        or DEFAULT_GEMINI_MODEL
    )
    return requested if requested in FREE_TIER_GEMINI_MODELS else DEFAULT_GEMINI_MODEL


def _api_key(settings: dict[str, str], override: str | None = None) -> str:
    return clean_text(override or settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"))


def gemini_key_configured(conn: sqlite3.Connection) -> bool:
    return bool(_api_key(_setting_map(conn)))


def _extract_gemini_text(result: dict[str, Any]) -> str:
    pieces: list[str] = []
    for candidate in result.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            text = part.get("text")
            if isinstance(text, str):
                pieces.append(text)
    return "".join(pieces).strip()


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first >= 0 and last >= first:
        cleaned = cleaned[first : last + 1]
    return cleaned


def _gemini_generate(api_key: str, model: str, prompt: str, max_output_tokens: int = 180) -> str:
    if model not in FREE_TIER_GEMINI_MODELS:
        raise ValueError("Selected model is not in the app's free-tier model list")
    payload = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max(32, int(max_output_tokens)),
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model),
        data=payload,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = _extract_gemini_text(result)
    if not text:
        raise ValueError("Gemini returned no text")
    return text


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        message = clean_text((parsed.get("error") or {}).get("message"))
        if message:
            return message[:280]
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return f"Gemini returned HTTP {exc.code}"


def test_gemini_connection(
    conn: sqlite3.Connection,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    settings = _setting_map(conn)
    selected_model = _model(settings, model)
    selected_key = _api_key(settings, api_key)
    if not selected_key:
        return {
            "success": False,
            "model": selected_model,
            "message": "No Gemini API key is configured.",
        }
    try:
        text = _gemini_generate(selected_key, selected_model, "Reply with exactly OK.", max_output_tokens=64)
        return {
            "success": True,
            "model": selected_model,
            "message": "Gemini connection is working.",
            "response": text[:80],
        }
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            message = "Gemini free quota is currently exhausted (429). Local catalog search still works."
        else:
            message = _http_error_message(exc)
        return {"success": False, "model": selected_model, "status": exc.code, "message": message}
    except (OSError, ValueError, KeyError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "model": selected_model,
            "message": clean_text(str(exc)) or "Gemini connection failed.",
        }


def _optional_llm_rerank(
    conn: sqlite3.Connection, query: str, candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str]:
    settings = _setting_map(conn)
    api_key = _api_key(settings)
    model = _model(settings)
    if not _enabled(settings) or not api_key or len(candidates) < 2:
        return candidates, "local"

    compact = [
        {
            "id": candidate["id"],
            "code": candidate.get("code"),
            "name": candidate.get("name"),
            "phase": candidate.get("phase"),
            "source_project": candidate.get("source_project"),
        }
        for candidate in candidates[:8]
    ]
    prompt = (
        "You are reranking existing electrical estimating catalog matches. "
        "Rank only the candidate IDs supplied below. Never invent a new ID, cost, quantity, or component. "
        "Return JSON only in exactly this shape: {\"ids\":[integer,...]}.\n\n"
        f"Estimator query: {query}\nCandidates: {json.dumps(compact, ensure_ascii=False)}"
    )
    try:
        output_text = _gemini_generate(api_key, model, prompt, max_output_tokens=180)
        ranked_ids = json.loads(_clean_json_text(output_text)).get("ids", [])
        by_id = {int(candidate["id"]): candidate for candidate in candidates}
        reordered: list[dict[str, Any]] = []
        for item_id in ranked_ids:
            try:
                candidate = by_id.get(int(item_id))
            except (TypeError, ValueError):
                candidate = None
            if candidate and candidate not in reordered:
                reordered.append(candidate)
        reordered.extend(candidate for candidate in candidates if candidate not in reordered)
        return reordered, "gemini_rerank"
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return candidates, "local_free_quota"
        return candidates, "local_fallback"
    except (OSError, ValueError, KeyError, urllib.error.URLError, json.JSONDecodeError):
        return candidates, "local_fallback"


def interpret_request(conn: sqlite3.Connection, text: str, limit: int = 12) -> dict[str, Any]:
    query, quantity = parse_quantity_and_query(text)
    candidates = search_catalog(conn, query, limit=max(limit, 12))
    candidates, method = _optional_llm_rerank(conn, query, candidates)
    return {
        "original": clean_text(text),
        "query": query,
        "quantity": quantity,
        "method": method,
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
