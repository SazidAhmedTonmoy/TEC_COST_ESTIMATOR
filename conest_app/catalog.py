from __future__ import annotations
from .estimate_options import display_title, annotate_catalog

import sqlite3
import math
from difflib import SequenceMatcher
from typing import Any
from types import MappingProxyType
from uuid import uuid4

from .database import refresh_catalog_index
from .read_cache import catalog_read_cache
from .taxonomy import CATALOG_CATEGORIES, WORK_TYPES, catalog_data_status, catalog_family_key, catalog_quality_score, catalog_specification
from .utils import as_float, clean_text, normalize_text, stable_hash, utc_now


def _unit_totals(conn: sqlite3.Connection, catalog_item_id: int) -> dict[str, float]:
    row = conn.execute(
        """SELECT
               COALESCE(SUM(quantity_per_unit * unit_material * material_factor), 0) AS unit_material,
               COALESCE(SUM(CASE WHEN labor_pricing='hours' THEN quantity_per_unit * unit_hours * labor_factor ELSE 0 END), 0) AS unit_hours,
               COALESCE(SUM(CASE WHEN labor_pricing='fixed' THEN quantity_per_unit * unit_labor_price * labor_factor ELSE 0 END), 0) AS unit_labor_price
           FROM catalog_components WHERE catalog_item_id = ?""",
        (catalog_item_id,),
    ).fetchone()
    return {key: float(row[key]) for key in ("unit_material", "unit_hours", "unit_labor_price")}


def _source_summary(conn: sqlite3.Connection, catalog_item_id: int) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT s.file_name, s.sheet_name, s.project_name, so.source_row
           FROM source_occurrences so
           JOIN sources s ON s.id = so.source_id
           WHERE so.catalog_item_id = ?
           ORDER BY s.imported_at DESC, so.id DESC""",
        (catalog_item_id,),
    ).fetchall()
    return {
        "source_count": len(rows),
        "source_file": rows[0]["file_name"] if rows else "Manual catalog",
        "source_sheet": rows[0]["sheet_name"] if rows else "",
        "source_project": rows[0]["project_name"] if rows else "",
        "source_row": rows[0]["source_row"] if rows else None,
    }


def _quality(row: sqlite3.Row | dict[str, Any]) -> float:
    return catalog_quality_score(
        data_status=row["data_status"] or catalog_data_status(row["unit_material"], row["unit_hours"]),
        component_count=int(row["component_count"] or 0),
        source_count=int(row["occurrence_count"] or 0),
        source_type=row["source_type"] or "",
        is_manual=bool(row["is_manual"]),
        usage_count=int(row["usage_count"] or 0),
    )


def _row_score(
    row: sqlite3.Row,
    normalized: str,
    tokens: list[str],
    aliases: dict[int, list[tuple[str, float, str]]],
) -> tuple[float, str]:
    quality = _quality(row)
    if not normalized:
        return quality + min(int(row["usage_count"] or 0), 100) * 20 + (80 if row["is_manual"] else 0), ""

    code = normalize_text(row["code"])
    name = normalize_text(row["name"])
    description = normalize_text(row["description"])
    scope = normalize_text(row["scope"])
    search_text = row["search_text"] or ""
    exact_code = bool(code and code == normalized)
    score = 0.0
    best_alias = ""
    learned_bonus = 0.0

    # Exact catalog codes must beat codes that merely contain the same short
    # characters (for example B1 must rank above TB1).
    if exact_code:
        score += 3000
    elif code and code.startswith(normalized):
        score += 1150
    elif code and normalized in code:
        score += 600

    if not exact_code:
        if name == normalized:
            score += 2200
        elif normalized in name:
            score += 780
    if normalized in description and normalized != name:
        score += 560
    if normalized in scope:
        score += 320

    coverage = sum(1 for token in tokens if token in search_text)
    if tokens:
        score += 500 * coverage / len(tokens)
        if coverage == len(tokens):
            score += 230
    score += 280 * max(
        SequenceMatcher(None, normalized, code).ratio() if code else 0,
        SequenceMatcher(None, normalized, name).ratio() if name else 0,
    )

    for alias_text, weight, source in aliases.get(int(row["id"]), []):
        ratio = SequenceMatcher(None, normalized, alias_text).ratio()
        alias_score = ratio * 330 + min(weight, 20) * 8
        if alias_text == normalized:
            alias_score += 900
        elif normalized and normalized in alias_text:
            alias_score += 300
        if alias_score > score:
            score = alias_score
            best_alias = source
        if source == "selection":
            if alias_text == normalized:
                learned_bonus = max(learned_bonus, 700 + min(weight, 20) * 45)
            elif normalized and normalized in alias_text:
                learned_bonus = max(learned_bonus, 250 + min(weight, 20) * 20)
            else:
                learned_bonus = max(learned_bonus, ratio * min(weight, 20) * 14)
            if learned_bonus > 0:
                best_alias = "selection"

    score += learned_bonus
    score += quality * 0.45
    return score, best_alias


@catalog_read_cache
def catalog_overview(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT id, content_key, category, data_status, is_manual
           FROM catalog_items WHERE is_active=1"""
    ).fetchall()
    families: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        families.setdefault(row["content_key"] or f"item:{row['id']}", []).append(row)
    visible = {
        key: members
        for key, members in families.items()
        if any(member["data_status"] != "reference_only" or member["is_manual"] for member in members)
    }
    category_counts: dict[str, int] = {category: 0 for category in CATALOG_CATEGORIES}
    for members in visible.values():
        # A retained version may belong to a different explicit trade category.
        # Keep each applicable category available in the filter.
        for category in {member["category"] or "Other" for member in members}:
            category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "catalog_groups": len(families),
        "usable_catalog_groups": len(visible),
        "source_variants": len(rows),
        "reference_only_variants": sum(1 for row in rows if row["data_status"] == "reference_only"),
        "categories": [
            {"name": category, "count": category_counts[category]}
            for category in category_counts
            if category_counts[category]
        ],
    }


class _ImmutableRows(tuple):
    def __deepcopy__(self, memo):
        return self


@catalog_read_cache
def _search_rows(conn):
    rows = conn.execute(
        """SELECT ci.id, ci.assembly_size, ci.code, ci.name, ci.description, ci.phase, ci.subphase, ci.scope,
                  ci.base_quantity, ci.base_uom, ci.source_type, ci.search_text, ci.is_manual,
                  ci.usage_count, ci.catalog_key, ci.content_key, ci.category, ci.data_status, ci.is_preferred, ci.work_type, ci.manual_revision,
                  ci.updated_at, COUNT(cc.id) AS component_count,
                  (SELECT COUNT(*) FROM source_occurrences so WHERE so.catalog_item_id=ci.id) AS occurrence_count,
                  COALESCE(SUM(cc.quantity_per_unit * cc.unit_material * cc.material_factor), 0) AS unit_material,
                  COALESCE(SUM(CASE WHEN cc.labor_pricing='hours' THEN cc.quantity_per_unit * cc.unit_hours * cc.labor_factor ELSE 0 END), 0) AS unit_hours,
                  COALESCE(SUM(CASE WHEN cc.labor_pricing='fixed' THEN cc.quantity_per_unit * cc.unit_labor_price * cc.labor_factor ELSE 0 END), 0) AS unit_labor_price
           FROM catalog_items ci
           LEFT JOIN catalog_components cc ON cc.catalog_item_id = ci.id
           WHERE ci.is_active = 1
           GROUP BY ci.id"""
    ).fetchall()
    return _ImmutableRows(MappingProxyType(dict(row)) for row in rows)


def search_catalog(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 20,
    *,
    category: str = "",
    include_incomplete: bool = False,
    group_variants: bool = True,
    recent_first: bool = False,
) -> list[dict[str, Any]]:
    query = clean_text(query)
    normalized = normalize_text(query)
    category = clean_text(category)
    limit = max(1, min(int(limit or 20), 100))
    rows = _search_rows(conn)
    recent = {int(row[0]): row[1] for row in conn.execute(
        "SELECT catalog_item_id, MAX(created_at) FROM project_lines WHERE catalog_item_id IS NOT NULL GROUP BY catalog_item_id"
    )} if recent_first else {}
    tokens = normalized.split()
    content_sizes: dict[str, dict[str, int]] = {}
    for row in rows:
        key = (row["content_key"] or f"item:{row['id']}",row["assembly_size"])
        summary = content_sizes.setdefault(key, {"variants": 0, "sources": 0, "incomplete": 0})
        summary["variants"] += 1
        summary["sources"] += int(row["occurrence_count"] or 0)
        summary["incomplete"] += int(row["data_status"] == "reference_only")

    scored: list[tuple[float, float, sqlite3.Row, str]] = []
    for row in rows:
        if category and row["category"] != category:
            continue
        if not include_incomplete and row["data_status"] == "reference_only" and not row["is_manual"]:
            continue
        title=normalize_text(display_title(row['name']))
        if normalized and not all(token in title for token in tokens):continue
        score=1200 if normalized==title else 850 if title.startswith(normalized) else 600 if normalized in title else 400
        best_alias='title' 
        if normalized and score < 190:
            continue
        scored.append((score, _quality(row), row, best_alias))

    if group_variants:
        # Only identical allowances collapse. A source code must never hide
        # a different size, price, work type or component build-up.
        best_by_content = {}
        for candidate in scored:
            row = candidate[2]
            key = (row["content_key"] or f"item:{row['id']}",row["assembly_size"])
            current = best_by_content.get(key)
            rank = (recent.get(int(row["id"]), ""), row["manual_revision"], candidate[0], candidate[1], int(row["id"]))
            if current is None or rank > (recent.get(int(current[2]["id"]), ""), current[2]["manual_revision"], current[0], current[1], int(current[2]["id"])):
                best_by_content[key] = candidate
        scored = list(best_by_content.values())

    if normalized:
        scored.sort(key=lambda item: (-item[0], -item[1], -int(item[2]["usage_count"]), item[2]["name"], item[2]["unit_material"]))
    else:
        scored.sort(
            key=lambda item: (
                -int(item[2]["usage_count"]),
                0 if item[2]["is_manual"] else 1,
                clean_text(item[2]["name"]),
                -item[1],
            )
        )
    if recent_first:
        scored.sort(key=lambda item: recent.get(int(item[2]["id"]), ""), reverse=True)
    results: list[dict[str, Any]] = []
    for score, quality, row, alias_source in scored[:limit]:
        item = dict(row)
        item.pop("search_text", None)
        if recent_first: item["last_used_at"] = recent.get(int(row["id"]), "")
        item["score"] = round(score, 2)
        item["quality_score"] = round(quality, 2)
        item["matched_by_learning"] = alias_source == "selection"
        item["unit_material"] = float(row["unit_material"] or 0.0)
        item["unit_hours"] = float(row["unit_hours"] or 0.0)
        source = _source_summary(conn, int(row["id"]))
        family_key = row["catalog_key"] or catalog_family_key(row["code"], row["name"])
        family = content_sizes[(row["content_key"] or f"item:{row['id']}", row["assembly_size"])]
        item.update(source)
        item["catalog_key"] = family_key
        item["variant_count"] = family["variants"]
        item["source_count"] = family["sources"] or source["source_count"]
        item["incomplete_variant_count"] = family["incomplete"]
        item["specification"] = _specification(conn, item["id"], item["name"])
        item["is_recommended"] = True
        annotate_catalog(item,[dict(c) for c in conn.execute('SELECT * FROM catalog_components WHERE catalog_item_id=? ORDER BY line_order,id',(item['id'],))])
        results.append(item)
    return results


def _specification(conn: sqlite3.Connection, item_id: int, name: str) -> str:
    components = [dict(row) for row in conn.execute(
        "SELECT description, size FROM catalog_components WHERE catalog_item_id=? ORDER BY line_order, id", (item_id,))]
    return catalog_specification(name, components)


def get_catalog_item(conn: sqlite3.Connection, catalog_item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM catalog_items WHERE id = ?", (catalog_item_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["components"] = [
        dict(component)
        for component in conn.execute(
            """SELECT id, line_order, item_no, description, quantity_per_unit, source_quantity, uom,
                      q_m, size, unit_material, material_factor, unit_hours, labor_factor, is_parent,
                      source_row, quantity_formula, notes, labor_pricing, unit_labor_price, is_supply_copy, fixed_quantity
               FROM catalog_components WHERE catalog_item_id = ? ORDER BY line_order, id""",
            (catalog_item_id,),
        )
    ]
    item["occurrences"] = [
        dict(occurrence)
        for occurrence in conn.execute(
            """SELECT so.*, s.file_name, s.sheet_name, s.project_name, s.imported_at
               FROM source_occurrences so JOIN sources s ON s.id = so.source_id
               WHERE so.catalog_item_id = ? ORDER BY s.imported_at DESC, so.id DESC""",
            (catalog_item_id,),
        )
    ]
    item["aliases"] = [
        dict(alias)
        for alias in conn.execute(
            "SELECT alias, weight, source FROM catalog_aliases WHERE catalog_item_id = ? ORDER BY weight DESC, alias",
            (catalog_item_id,),
        )
    ]
    item.update(_unit_totals(conn, catalog_item_id))
    family_key = item.get("catalog_key") or catalog_family_key(item.get("code"), item.get("name"))
    variant_rows = conn.execute(
        """SELECT ci.id, ci.assembly_size, ci.code, ci.name, ci.content_key, ci.category, ci.data_status, ci.is_preferred,
                  ci.source_type, ci.is_manual, ci.usage_count, ci.updated_at, ci.work_type, ci.base_uom,
                  COUNT(cc.id) AS component_count,
                  COALESCE(SUM(cc.quantity_per_unit * cc.unit_material * cc.material_factor), 0) AS unit_material,
                  COALESCE(SUM(CASE WHEN cc.labor_pricing='hours' THEN cc.quantity_per_unit * cc.unit_hours * cc.labor_factor ELSE 0 END), 0) AS unit_hours,
                  COALESCE(SUM(CASE WHEN cc.labor_pricing='fixed' THEN cc.quantity_per_unit * cc.unit_labor_price * cc.labor_factor ELSE 0 END), 0) AS unit_labor_price,
                  (SELECT COUNT(*) FROM source_occurrences so WHERE so.catalog_item_id=ci.id) AS occurrence_count
           FROM catalog_items ci LEFT JOIN catalog_components cc ON cc.catalog_item_id=ci.id
           WHERE ci.is_active=1 AND ci.catalog_key IN (
               SELECT catalog_key FROM catalog_items WHERE catalog_key=? OR content_key=?
           ) GROUP BY ci.id""",
        (family_key, item.get("content_key")),
    ).fetchall()
    variants = []
    for variant in variant_rows:
        summary = dict(variant)
        summary["unit_material"] = float(variant["unit_material"] or 0.0)
        summary["unit_hours"] = float(variant["unit_hours"] or 0.0)
        summary["quality_score"] = _quality(variant)
        summary.update(_source_summary(conn, int(variant["id"])))
        variants.append(summary)
    variants.sort(
        key=lambda variant: (
            variant["id"] != catalog_item_id,
            -float(variant["quality_score"]),
            -int(variant["usage_count"] or 0),
            -int(variant["id"]),
        )
    )
    distinct = {}
    for variant in variants:
        key = (variant["content_key"] or f"item:{variant['id']}", variant["assembly_size"])
        if key not in distinct:
            variant["source_ids"] = []
            variant["specification"] = variant["assembly_size"] or _specification(conn, variant["id"], variant["name"])
            distinct[key] = variant
        distinct[key]["source_ids"].append(variant["id"])
    item["specification"] = catalog_specification(item["name"], item["components"])
    item["catalog_key"] = family_key
    item["variant_count"] = len(variants)
    item["variants"] = list(distinct.values())
    return annotate_catalog(item,item["components"])


def _nonnegative(value: Any, label: str, default: float = 0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a non-negative number") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a finite, non-negative number")
    return number


def _manual_options(payload: dict[str, Any]) -> tuple[str, str]:
    work_type = clean_text(payload.get("work_type") or "assembly")
    if work_type not in WORK_TYPES:
        raise ValueError("Select a supported work type")
    category = clean_text(payload.get("category_override"))
    if len(category) > 120:
        raise ValueError("Category must be 120 characters or fewer")
    return work_type, category


def _validated_components(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("components") or []
    if not isinstance(rows, list):
        raise ValueError("components must be a list")
    if not rows:
        rows = [
            {
                "description": payload.get("name") or payload.get("description") or "Manual item",
                "quantity_per_unit": 1,
                "unit_material": payload.get("unit_material", 0),
                "unit_hours": payload.get("unit_hours", 0),
                "uom": payload.get("base_uom") or "EA",
                "labor_pricing": payload.get("labor_pricing", "hours"),
                "unit_labor_price": payload.get("unit_labor_price", 0),
                "is_parent": 1,
            }
        ]
    result = []
    parent_index = next((i for i,c in enumerate(rows) if isinstance(c,dict) and c.get("is_parent")),0)
    for index, component in enumerate(rows):
        if not isinstance(component, dict):
            raise ValueError(f"Component {index + 1} must be an object")
        description = clean_text(component.get("description"))
        if not description:
            raise ValueError(f"Component {index + 1} needs a description")
        labor_pricing = clean_text(component.get("labor_pricing") or "hours")
        if labor_pricing not in {"hours", "fixed"}:
            raise ValueError(f"Component {index + 1}: choose hours or fixed labour pricing")
        quantity = _nonnegative(component.get("quantity_per_unit"), "Quantity per unit")
        material = _nonnegative(component.get("unit_material"), "Unit material price")
        hours = _nonnegative(component.get("unit_hours"), "Unit labour hours")
        price = _nonnegative(component.get("unit_labor_price"), "Unit labour price")
        work_type = payload.get("work_type", "assembly")
        if work_type == "installation_only" and material:
            raise ValueError("Installation-only items must have zero material price; use Supply & installation to include materials")
        if work_type == "supply_only" and (hours or price):
            raise ValueError("Supply-only items must have zero labour; use Supply & installation to include labour")
        result.append(
            {
                "line_order": index,
                "item_no": clean_text(component.get("item_no")),
                "description": description,
                "quantity_per_unit": quantity,
                "source_quantity": _nonnegative(component.get("source_quantity", quantity), "Original quantity", quantity),
                "fixed_quantity": 1 if component.get("fixed_quantity") else 0,
                "uom": clean_text(component.get("uom") or "EA"),
                "q_m": clean_text(component.get("q_m")),
                "size": clean_text(component.get("size")),
                "unit_material": material,
                "material_factor": _nonnegative(component.get("material_factor"), "Material factor", 1),
                "unit_hours": hours if labor_pricing == "hours" else 0.0,
                "labor_factor": _nonnegative(component.get("labor_factor"), "Labour factor", 1),
                "labor_pricing": labor_pricing,
                "unit_labor_price": price if labor_pricing == "fixed" else 0.0,
                "is_parent": 1 if index == parent_index else 0,
                "is_supply_copy": 1 if component.get("is_supply_copy") else 0,
                "notes": clean_text(component.get("notes")),
            }
        )
    return result


def create_manual_catalog_item(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    name = clean_text(payload.get("name"))
    if not name:
        raise ValueError("name is required")
    work_type, category = _manual_options(payload)
    components = _validated_components(payload)
    code = clean_text(payload.get("code"))
    description = clean_text(payload.get("description") or name)
    phase = clean_text(payload.get("phase") or "Manual items")
    subphase = clean_text(payload.get("subphase"))
    scope = clean_text(payload.get("scope") or phase)
    base_uom = clean_text(payload.get("base_uom") or "EA")
    now = utc_now()
    fingerprint = stable_hash({"manual": uuid4().hex, "code": code, "name": name, "components": components})
    search_fields = [code, name, description, phase, subphase, scope, category, WORK_TYPES[work_type], base_uom]
    for component in components:
        search_fields.extend([component["item_no"], component["description"], component["size"]])
    cursor = conn.execute(
        """INSERT INTO catalog_items
           (code, name, description, phase, subphase, scope, base_quantity, base_uom, source_type,
            fingerprint, search_text, is_manual, is_active, created_at, updated_at, work_type, category_override)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'manual', ?, ?, 1, 1, ?, ?, ?, ?)""",
        (code, name, description, phase, subphase, scope, base_uom, fingerprint, normalize_text(" ".join(search_fields)), now, now, work_type, category),
    )
    item_id = int(cursor.lastrowid)
    conn.execute("UPDATE catalog_items SET manual_revision=(SELECT COALESCE(MAX(manual_revision),0)+1 FROM catalog_items) WHERE id=?", (item_id,))
    _replace_components(conn, item_id, components)
    for alias in {code, name, description}:
        normalized = normalize_text(alias)
        if normalized:
            conn.execute(
                """INSERT OR IGNORE INTO catalog_aliases
                   (catalog_item_id, alias, normalized_alias, weight, source, created_at)
                   VALUES (?, ?, ?, 2, 'manual', ?)""",
                (item_id, alias, normalized, now),
            )
    if 'assembly_size' in payload:
        size=clean_text(payload['assembly_size'])
        if len(size)>250:raise ValueError('Size must be 250 characters or fewer')
        conn.execute('UPDATE catalog_items SET assembly_size=? WHERE id=?',(size,item_id))
    refresh_catalog_index(conn)
    return get_catalog_item(conn, item_id)  # type: ignore[return-value]


def _replace_components(conn: sqlite3.Connection, item_id: int, components: list[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM catalog_components WHERE catalog_item_id = ?", (item_id,))
    for component in components:
        conn.execute(
            """INSERT INTO catalog_components
               (catalog_item_id, line_order, item_no, description, quantity_per_unit, source_quantity,
                uom, q_m, size, unit_material, material_factor, unit_hours, labor_factor, is_parent, notes, labor_pricing, unit_labor_price, is_supply_copy, fixed_quantity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                component["line_order"],
                component["item_no"],
                component["description"],
                component["quantity_per_unit"],
                component["source_quantity"],
                component["uom"],
                component["q_m"],
                component["size"],
                component["unit_material"],
                component["material_factor"],
                component["unit_hours"],
                component["labor_factor"],
                component["is_parent"],
                component["notes"],
                component["labor_pricing"],
                component["unit_labor_price"],
                component.get("is_supply_copy",0),
                component.get("fixed_quantity",0),
            ),
        )


def update_manual_catalog_item(conn: sqlite3.Connection, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    current = conn.execute("SELECT * FROM catalog_items WHERE id = ?", (item_id,)).fetchone()
    if not current:
        raise LookupError("Catalog item not found")
    if payload.get("create_version"):
        base = get_catalog_item(conn, item_id)
        assert base is not None
        return create_manual_catalog_item(
            conn,
            {
                "code": payload.get("code", base["code"]),
                "name": payload.get("name", base["name"]),
                "description": payload.get("description", base["description"]),
                "phase": payload.get("phase", base["phase"]),
                "subphase": payload.get("subphase", base["subphase"]),
                "scope": payload.get("scope", base["scope"]),
                "base_uom": payload.get("base_uom", base["base_uom"]),
                "work_type": payload.get("work_type", base["work_type"]),
                "category_override": payload.get("category_override", base["category_override"]),
                "components": payload.get("components", base["components"]),
            },
        )
    merged = dict(current)
    merged.update(payload)
    if "components" not in payload:
        merged["components"] = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM catalog_components WHERE catalog_item_id = ? ORDER BY line_order, id",
                (item_id,),
            )
        ]
    name = clean_text(merged.get("name"))
    if not name:
        raise ValueError("name is required")
    work_type, category = _manual_options(merged)
    components = _validated_components(merged)
    code = clean_text(merged.get("code"))
    description = clean_text(merged.get("description") or name)
    phase = clean_text(merged.get("phase") or "Manual items")
    subphase = clean_text(merged.get("subphase"))
    scope = clean_text(merged.get("scope") or phase)
    base_uom = clean_text(merged.get("base_uom") or "EA")
    now = utc_now()
    search_fields = [code, name, description, phase, subphase, scope, category, WORK_TYPES[work_type], base_uom]
    for component in components:
        search_fields.extend([component["item_no"], component["description"], component["size"]])
    conn.execute(
        """UPDATE catalog_items SET code=?, name=?, description=?, phase=?, subphase=?, scope=?,
           base_uom=?, fingerprint=?, search_text=?, updated_at=?, work_type=?, category_override=?,
           manual_revision=(SELECT COALESCE(MAX(manual_revision),0)+1 FROM catalog_items) WHERE id=?""",
        (
            code,
            name,
            description,
            phase,
            subphase,
            scope,
            base_uom,
            stable_hash({"manual": item_id, "updated": now, "components": components}),
            normalize_text(" ".join(search_fields)),
            now,
            work_type,
            category,
            item_id,
        ),
    )
    _replace_components(conn, item_id, components)
    conn.execute("DELETE FROM catalog_aliases WHERE catalog_item_id=? AND source='manual'", (item_id,))
    for alias in {code, name, description}:
        if normalize_text(alias):
            conn.execute(
                """INSERT OR IGNORE INTO catalog_aliases
                   (catalog_item_id, alias, normalized_alias, weight, source, created_at)
                   VALUES (?, ?, ?, 2, 'manual', ?)""",
                (item_id, alias, normalize_text(alias), now),
            )
    if 'assembly_size' in payload:
        size=clean_text(payload['assembly_size'])
        if len(size)>250:raise ValueError('Size must be 250 characters or fewer')
        conn.execute('UPDATE catalog_items SET assembly_size=? WHERE id=?',(size,item_id))
    refresh_catalog_index(conn)
    return get_catalog_item(conn, item_id)  # type: ignore[return-value]


def record_selection(conn: sqlite3.Connection, query: str, catalog_item_id: int) -> None:
    normalized = normalize_text(query)
    if not normalized:
        return
    item = conn.execute("SELECT id FROM catalog_items WHERE id = ?", (catalog_item_id,)).fetchone()
    if not item:
        raise LookupError("Catalog item not found")
    now = utc_now()
    conn.execute(
        "INSERT INTO selection_feedback(query, normalized_query, catalog_item_id, selected_at) VALUES (?, ?, ?, ?)",
        (clean_text(query), normalized, catalog_item_id, now),
    )
    conn.execute("UPDATE catalog_items SET usage_count = usage_count + 1, updated_at = ? WHERE id = ?", (now, catalog_item_id))
    conn.execute(
        """INSERT INTO catalog_aliases
           (catalog_item_id, alias, normalized_alias, weight, source, created_at)
           VALUES (?, ?, ?, 2, 'selection', ?)
           ON CONFLICT(catalog_item_id, normalized_alias)
           DO UPDATE SET weight = weight + 1, alias = excluded.alias, source = 'selection'""",
        (catalog_item_id, clean_text(query), normalized, now),
    )


def list_sources(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sources ORDER BY imported_at DESC, file_name, sheet_name"
        )
    ]


def list_import_issues(conn: sqlite3.Connection, unresolved_only: bool = False, limit: int = 500) -> list[dict[str, Any]]:
    sql = """SELECT i.*, s.file_name, s.sheet_name
             FROM import_issues i LEFT JOIN sources s ON s.id = i.source_id"""
    params: list[Any] = []
    if unresolved_only:
        sql += " WHERE i.resolved = 0"
    sql += " ORDER BY CASE i.severity WHEN 'error' THEN 0 ELSE 1 END, i.id DESC LIMIT ?"
    params.append(max(1, min(limit, 2000)))
    return [dict(row) for row in conn.execute(sql, params)]


def delete_catalog_item(conn, item_id):
    """Delete one selected catalogue version; estimate snapshots survive via SET NULL."""
    row=conn.execute('SELECT id,name FROM catalog_items WHERE id=?',(item_id,)).fetchone()
    if not row:raise LookupError('Catalog item not found')
    conn.execute('DELETE FROM catalog_items WHERE id=?',(item_id,))
    refresh_catalog_index(conn)
    return {'deleted_id':item_id,'name':row['name']}
