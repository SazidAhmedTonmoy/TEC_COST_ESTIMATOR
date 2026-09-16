from __future__ import annotations

from typing import Any

from .utils import clean_text, normalize_text, stable_hash


CATALOG_CATEGORIES = (
    "Lighting",
    "Emergency & Exit Lighting",
    "Lighting Controls",
    "Power",
    "Submains & Cabling",
    "Containment & Underground",
    "Earthing",
    "Switchboards & Distribution",
    "Communications & Data",
    "Fire & Security",
    "Demolition & Relocation",
    "General & Testing",
    "Other",
)


WORK_TYPES = {
    "assembly": "Assembly",
    "supply_install": "Supply & installation",
    "supply_only": "Supply only",
    "installation_only": "Installation only",
    "relocation": "Relocation",
    "demolition": "Demolition",
    "relocation_demolition": "Relocation and Demolition",
}


def scope_sort_key(value: Any) -> tuple:
    """One category order for the website, scope summary and Excel export."""
    label = clean_text(value) or 'Other'
    key = normalize_text(label)
    standard = {normalize_text(name): index for index, name in enumerate(CATALOG_CATEGORIES)}
    if key in standard:
        rank = standard[key] if key != 'other' else len(CATALOG_CATEGORIES) + 1
    else:
        rank = len(CATALOG_CATEGORIES)
    return rank, key


def catalog_content_key(item: Any, components: list[dict[str, Any]]) -> str:
    """Identify identical reusable allowances across manual and imported copies.

    Provenance, take-off quantities and category labels do not change the
    allowance. Codes and source phases are reference metadata, not identity.
    Names, specifications, units, component quantities and prices do matter.
    """
    work = item["work_type"] or "assembly"
    if work == "assembly":
        material = any(float(c.get("unit_material") or 0) for c in components)
        labour = any(float(c.get("unit_hours") or 0) or float(c.get("unit_labor_price") or 0) for c in components)
        work = "supply_install" if material and labour else "supply_only" if material else "installation_only" if labour else "assembly"
    details = []
    for c in components:
        detail = {
            **{key: normalize_text(c.get(key)) for key in ("description", "uom", "size", "notes")},
            **{key: round(float(c.get(key) or 0), 8) for key in ("quantity_per_unit", "unit_material", "material_factor", "unit_hours", "labor_factor", "unit_labor_price")},
            "labor_pricing": c.get("labor_pricing") or "hours",
        }
        if c.get("is_supply_copy"):detail["is_supply_copy"]=True
        if c.get("fixed_quantity"):detail["fixed_quantity"]=True
        details.append(detail)
    details.sort(key=stable_hash)
    return stable_hash({"name": normalize_text(item["name"]),
                        "unit": normalize_text(item["base_uom"] or "EA"), "work_type": work, "components": details})


def catalog_specification(name: str, components: list[dict[str, Any]]) -> str:
    """A short, meaningful size label instead of a source code."""
    words = set(normalize_text(name).split()) - {"and", "the", "supply", "installation", "of"}
    sized = [c for c in components if any(char.isdigit() for char in clean_text(c.get("size")))]
    matching = [c for c in sized if words.intersection(normalize_text(c.get("description")).split())]
    sizes = dict.fromkeys(clean_text(c.get("size")) for c in (matching or sized))
    return " · ".join(list(sizes)[:3])


def catalog_family_key(code: Any, name: Any, work_type: Any = "assembly", base_uom: Any = "", manual: bool = False) -> str:
    """Group structural source variants without deleting their audit history."""
    key = f"{normalize_text(code)}::{normalize_text(name)}"
    # Explicit manual scopes and measurement units must not collapse into a
    # different price basis. Keep legacy imported family keys unchanged.
    if manual or (work_type and work_type != "assembly"):
        key += f"::{normalize_text(work_type)}::{normalize_text(base_uom)}"
    return key


def catalog_category(
    code: Any = "",
    name: Any = "",
    description: Any = "",
    phase: Any = "",
    scope: Any = "",
) -> str:
    code_text = normalize_text(code)
    text = normalize_text(" ".join(clean_text(value) for value in (name, description, phase, scope)))

    if any(term in text for term in ("emergency", "exit sign", "spitfire")) or code_text.startswith(("em", "ex")):
        return "Emergency & Exit Lighting"
    if any(term in text for term in ("lighting control", "dali control", "c bus", "knx", "motion sensor", "daylight sensor")):
        return "Lighting Controls"
    if any(term in text for term in ("fire alarm", "security", "cctv", "access control", "intercom", "fip", "fdcie")):
        return "Fire & Security"
    if any(term in text for term in ("communications", "communication", "data outlet", "data cabling", "fobot", "patch panel", "wap", "cat6")):
        return "Communications & Data"
    if any(term in text for term in ("demolition", "demolish", "remove existing", "relocation", "relocate", "reinstall")):
        return "Demolition & Relocation"
    if code_text.startswith("cid") or any(term in text for term in ("submain", "sub main", "consumer main", "feeder", "mains cable", "lv cable")):
        return "Submains & Cabling"
    if any(term in text for term in ("switchboard", "distribution board", "main switch board", "main switchboard", "meter panel")):
        return "Switchboards & Distribution"
    if any(term in text for term in ("general lighting", "external lighting", "luminaire", "light fitting", "pendant light", "downlight", "batten", "led strip", "bollard")):
        return "Lighting"
    if any(term in text for term in ("power", "gpo", "isolator", "outlet", "floor box", "socket", "dedicated supply")):
        return "Power"
    if any(term in text for term in ("testing", "test and commission", "commissioning", "certification", "preliminaries", "documentation", "project management")):
        return "General & Testing"
    return "Other"


def catalog_data_status(unit_material: Any, unit_hours: Any, unit_labor_price: Any = 0) -> str:
    material = abs(float(unit_material or 0.0)) > 1e-9
    hours = abs(float(unit_hours or 0.0)) > 1e-9 or abs(float(unit_labor_price or 0.0)) > 1e-9
    if material and hours:
        return "ready"
    if material:
        return "material_only"
    if hours:
        return "labour_only"
    return "reference_only"


def catalog_quality_score(
    *,
    data_status: str,
    component_count: int = 0,
    source_count: int = 0,
    source_type: str = "",
    is_manual: bool = False,
    usage_count: int = 0,
) -> float:
    status_score = {
        "ready": 420.0,
        "material_only": 290.0,
        "labour_only": 270.0,
        "reference_only": 0.0,
    }.get(data_status, 0.0)
    return (
        status_score
        + min(max(int(component_count), 0), 30) * 2.0
        + min(max(int(source_count), 0), 15) * 4.0
        + (35.0 if source_type == "sample" else 0.0)
        + (55.0 if is_manual else 0.0)
        + min(max(int(usage_count), 0), 100) * 8.0
    )
