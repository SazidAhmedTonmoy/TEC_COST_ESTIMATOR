from __future__ import annotations

from collections import Counter
from typing import Any

from .importer import ParsedAssembly, ParsedComponent, ParsedIssue, ParsedSheet, _formula_ratio_from_base, _formula_text
from .taxonomy import catalog_category
from .utils import as_float, clean_text, normalize_text


def is_component_master(ws: Any) -> bool:
    labels = {normalize_text(c.value) for c in ws[4]}
    return {"phase", "category", "unit", "special materials suppliers", "take off qty", "item id"}.issubset(labels)


def _category(phase: str, subcategory: str, name: str) -> str:
    text = normalize_text(phase)
    if "demoli" in text or "relocat" in text: return "Demolition & Relocation"
    if "communication" in text: return "Communications & Data"
    if "containment" in text: return "Containment & Underground"
    if "submain" in text or "consumer main" in text: return "Submains & Cabling"
    if "distribution board" in text or "switchboard" in text: return "Switchboards & Distribution"
    if "documentation" in text: return "General & Testing"
    if "earthing" in text: return "Earthing"
    if "emergency" in text: return "Emergency & Exit Lighting"
    if "lighting control" in text: return "Lighting Controls"
    if text == "lighting": return "Lighting"
    if text in {"power", "ex to remain"}: return "Power"
    return catalog_category(name=name, phase=phase, scope=subcategory)


def parse_component_master(values: Any, formulas: Any) -> ParsedSheet:
    parsed = ParsedSheet(values.title, "Component pricing master", "component_pricing_master", values.max_row, 1)
    parent_rows = [row for row in range(5, values.max_row + 1) if clean_text(values.cell(row, 5).value) and (
        clean_text(values.cell(row, 14).value) or values.cell(row, 6).value is not None
    )]
    ids = Counter(clean_text(values.cell(row, 14).value) for row in parent_rows)
    repeated = {code: count for code, count in ids.items() if code and count > 1}
    if ids.get(""):
        parsed.issues.append(ParsedIssue("info", "MISSING_ITEM_IDS", f"{ids['']} named assemblies without item IDs were imported using source rows and names."))
    if repeated:
        parsed.issues.append(ParsedIssue("info", "REUSED_ITEM_IDS", "Repeated source IDs were retained as separate named assemblies using source row and component content.", payload=repeated))
    if values.cell(2, 2).data_type == "e":
        parsed.issues.append(ParsedIssue("warning", "SOURCE_LABOUR_RATE_ERROR", "The source labour-rate cell is broken. Raw material rates and labour hours were imported; estimates use their own project labour rate.", 2))
    for position, parent in enumerate(parent_rows):
        end = parent_rows[position + 1] if position + 1 < len(parent_rows) else values.max_row + 1
        name = clean_text(values.cell(parent, 5).value)
        phase = clean_text(values.cell(parent, 1).value)
        subcategory = clean_text(values.cell(parent, 2).value)
        base = as_float(values.cell(parent, 6).value, 1)
        if base <= 0:
            parsed.issues.append(ParsedIssue("warning", "NON_POSITIVE_BASE_QUANTITY", "A base of 1 was used; connected quantity formulas define the reusable ratios.", parent))
            base = 1
        phase_norm = normalize_text(phase)
        work_type = "demolition" if "demoli" in phase_norm else "relocation" if "relocat" in phase_norm else "assembly"
        parent_notes = clean_text(values.cell(parent, 15).value)
        assembly = ParsedAssembly(
            code=clean_text(values.cell(parent, 14).value), name=name,
            description=name + (" — " + parent_notes if parent_notes else ""),
            phase=phase, subphase=subcategory, scope=" / ".join(filter(None, (phase, subcategory))),
            base_quantity=base, base_uom=clean_text(values.cell(parent, 4).value) or "EA",
            source_row=parent, source_type="component_master", work_type=work_type,
            category_override=_category(phase, subcategory, name),
        )
        children = [row for row in range(parent + 1, end) if clean_text(values.cell(row, 5).value)]
        rows = children[:]
        # A parent with raw unit prices is a genuine direct cost row, whereas
        # summary SUM formulas in total columns must never be charged twice.
        if not children or values.cell(parent, 8).value is not None or values.cell(parent, 10).value is not None:
            rows.insert(0, parent)
        for row in rows:
            description = clean_text(values.cell(row, 5).value)
            if not description: continue
            qty_formula = _formula_text(formulas.cell(row, 7).value)
            ratio = _formula_ratio_from_base(values, qty_formula, 6, parent, row) if qty_formula else None
            if ratio is None:
                quantity = as_float(values.cell(row, 7).value, float("nan"))
                if quantity == quantity:
                    ratio = quantity / base
                elif row == parent and not qty_formula:
                    ratio = 1
                else:
                    parsed.issues.append(ParsedIssue("warning", "UNRESOLVED_COMPONENT_QUANTITY", "Component quantity could not be read; retained at zero for review.", row, {"formula": qty_formula}))
                    ratio = 0
            notes = clean_text(values.cell(row, 15).value)
            if parent_notes and row != parent and not assembly.components:
                notes = " | ".join(filter(None, (parent_notes, notes)))
            component = ParsedComponent(
                line_order=len(assembly.components), item_no="", description=description,
                quantity_per_unit=max(0, ratio), source_quantity=max(0, ratio) * base,
                uom=clean_text(values.cell(row, 4).value) or assembly.base_uom,
                size=clean_text(values.cell(row, 3).value),
                unit_material=max(0, as_float(values.cell(row, 8).value)),
                unit_hours=max(0, as_float(values.cell(row, 10).value)),
                is_parent=int(not assembly.components), source_row=row, quantity_formula=qty_formula, notes=notes,
            )
            if component.source_quantity > 0:
                # Some newly entered one-line allowances have totals but no
                # unit-rate cells. Recover their explicit one-item rates.
                if values.cell(row, 8).value is None and isinstance(formulas.cell(row, 9).value, (int, float)):
                    markup = as_float(values.cell(2, 5).value, 0)
                    component.unit_material = max(0, as_float(values.cell(row, 9).value) / component.source_quantity / (1 + markup))
                if values.cell(row, 10).value is None and isinstance(formulas.cell(row, 11).value, (int, float)):
                    component.unit_hours = max(0, as_float(values.cell(row, 11).value) / component.source_quantity)
            assembly.components.append(component)
        assembly.source_material_total = sum(c.source_quantity * c.unit_material for c in assembly.components)
        assembly.source_labor_hours = sum(c.source_quantity * c.unit_hours for c in assembly.components)
        if assembly.components: parsed.assemblies.append(assembly)
    return parsed
