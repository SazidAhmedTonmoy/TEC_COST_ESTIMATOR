from __future__ import annotations

import sqlite3
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.page import PageMargins

from .projects import calculate_project
from .taxonomy import WORK_TYPES
from .utils import safe_filename


DARK_NAVY = "0B1F33"
NAVY = "173B55"
TEAL = "087F75"
TEAL_DARK = "08776F"
TEAL_LIGHT = "EDF7F5"
GREEN = "173B55"
GREEN_LIGHT = "F4F8FA"
LIME = "E8F4F1"
YELLOW = "EAF1F5"
CREAM = "FFF7E4"
BLUE_LIGHT = "DDEBF7"
GRAY_100 = "F1F5F9"
GRAY_300 = "DEE7EC"
GRAY_600 = "475569"
DARK = "0F172A"
WHITE = "FFFFFF"
INPUT_BLUE = "1D548A"
LINK_GREEN = "405D6D"


def _currency_format(currency: str) -> str:
    symbol = "$" if currency.upper() in {"AUD", "USD", "CAD", "NZD"} else f'"{currency} "'
    return f'{symbol}#,##0.00;[Red]({symbol}#,##0.00);{symbol}-'


def _set_widths(ws: Any, widths: dict[str, float]) -> None:
    for column, width in widths.items():
        ws.column_dimensions[column].width = width


def _outline_border(color: str = GRAY_300, style: str = "thin") -> Border:
    side = Side(style=style, color=color)
    return Border(left=side, right=side, top=side, bottom=side)


def _row_border(color: str = GRAY_300) -> Border:
    return Border(bottom=Side(style="thin", color=color))


def _sum_cells(column: str, rows: list[int]) -> str:
    return "=0" if not rows else "=SUM(" + ",".join(f"{column}{row}" for row in rows) + ")"


def _count_cells(column: str, rows: list[int]) -> str:
    return "=0" if not rows else "=COUNT(" + ",".join(f"{column}{row}" for row in rows) + ")"


def _safe_formula_factor(value: Any, default: float = 1.0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return f"{max(number, 0.0):.10g}"


def _merge_value(
    ws: Any,
    cell_range: str,
    value: Any,
    *,
    fill: str | None = None,
    color: str = DARK,
    size: float = 10,
    bold: bool = False,
    horizontal: str = "left",
    border: Border | None = None,
    number_format: str | None = None,
) -> Any:
    ws.merge_cells(cell_range)
    cell = ws[cell_range.split(":")[0]]
    cell.value = value
    cell.font = Font(name="Aptos", size=size, bold=bold, color=color)
    cell.alignment = Alignment(horizontal=horizontal, vertical="center", wrap_text=True, indent=1 if horizontal != "center" else 0)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    if border:
        for row in ws[cell_range]:
            for bordered in row:
                bordered.border = border
                if fill:
                    bordered.fill = PatternFill("solid", fgColor=fill)
    if number_format:
        cell.number_format = number_format
    return cell


def _section_title(ws: Any, row: int, title: str, fill: str = TEAL) -> None:
    cell = _merge_value(
        ws,
        f"A{row}:N{row}",
        title,
        fill=fill,
        color=WHITE,
        size=10.5,
        bold=True,
        border=_outline_border(fill),
    )
    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 25


def export_project(conn: sqlite3.Connection, project_id: int, output_path: str | Path) -> Path:
    data = calculate_project(conn, project_id, include_components=True)
    project = data["project"]
    lines = data["lines"]
    has_fixed_labor = any(c.get("labor_pricing") == "fixed" for line in lines for c in line["components"])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "COST ESTIMATE"
    overview = ws
    detail = wb.create_sheet("CONNECTED COST DETAIL")
    detail_ref = "'CONNECTED COST DETAIL'!"
    settings_ref = "'COST ESTIMATE'!"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 80
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"

    currency = project.get("currency") or "AUD"
    money = _currency_format(currency)
    percent = "0.0%"
    hours = '0.00" hrs";[Red](0.00" hrs");-'
    quantity = '0.00;[Red](0.00);-'
    days = '0.00" Days";[Red](0.00" Days");-'
    border = _outline_border()

    detail_title_row = 4
    detail_header_row = detail_title_row + 1
    # Keep item prices visible; a numeric include flag gates only roll-up totals.
    inclusion_flag_column = 16
    included_columns = {"G": "Q", "I": "R", "J": "S", "K": "T", "L": "U"}

    _merge_value(ws, "A1:N1", '=B2&" — COST ESTIMATE"', fill=DARK_NAVY, color=WHITE, size=18, bold=True)
    ws.row_dimensions[1].height = 44
    metadata = [
        ("A2", "PROJECT", "B2:F2", project["name"]),
        ("G2", "BUILDERS", "H2:K2", "\n".join(project.get("builders") or [])),
        ("L2", "CURRENCY", "M2:N2", "=C7"),
    ]
    for label_cell, label, value_range, value in metadata:
        ws[label_cell] = label
        ws[label_cell].font = Font(name="Aptos", size=10, bold=True, color=GRAY_600)
        ws[label_cell].alignment = Alignment(vertical="center")
        cell = _merge_value(ws, value_range, value, size=10.5)
        if label in {"PROJECT", "BUILDERS"}:
            cell.fill = PatternFill("solid", fgColor=CREAM)
            cell.font = Font(name="Aptos", size=10.5, color=INPUT_BLUE)
            cell.protection = Protection(locked=False)
            cell.data_type = "s"  # Builder/project names are text, never formulas.
    _merge_value(
        ws,
        "A3:J3",
        "Pale gold cells are editable. Open the detail tab to change items, categories, quantities and component prices.",
        color=GRAY_600,
        size=10,
    )
    ws["K3"] = "GENERATED"
    ws["K3"].font = Font(name="Aptos", size=9.5, bold=True, color=GRAY_600)
    _merge_value(ws, "L3:N3", datetime.now().strftime("%Y-%m-%d %H:%M"), color=GRAY_600, size=10, horizontal="right")

    cards = (("A4:C4", "PRICING", TEAL), ("D4:F4", "LABOUR", NAVY), ("G4:I4", "CREW PLAN", GREEN), ("J4:N4", "ESTIMATE TOTALS", DARK_NAVY))
    for cell_range, label, fill in cards:
        _merge_value(ws, cell_range, label, fill=fill, color=WHITE, size=10, bold=True, horizontal="center", border=border)

    settings_rows = (
        ("A5:B5", "Material mark-up", "C5", float(project["material_markup"]), percent),
        ("A6:B6", "Final mark-up", "C6", float(project["overhead_markup"]), percent),
        ("A7:B7", "Currency", "C7", currency, "@"),
        ("D5:E5", "Labour rate / hr", "F5", float(project["labor_rate"]), money),
        ("D6:E6", "Hrs / person / day", "F6", float(project.get("hours_per_day",8)), '0.00" hrs"'),
        ("D7:E7", "Labour hour mark-up", "F7", float(project.get("labor_hours_markup",0)), percent),
        ("G5:H5", "Crew size", "I5", int(project.get("crew_size",2)), "0"),
        ("G6:H6", "Crew hrs / day", "I6", "=I5*F6", "0.00"),
        ("G7:H7", "Working days", "I7", "=IF(I6=0,0,M7/I6)", days),
    )
    editable = {"C5", "C6", "F5", "F6", "F7", "I5"}
    for label_range, label, value_cell, value, number_format in settings_rows:
        _merge_value(ws, label_range, label, fill=GRAY_100, size=10, bold=True, border=border)
        cell = ws[value_cell]
        cell.value = value
        cell.number_format = number_format
        cell.fill = PatternFill("solid", fgColor=CREAM if value_cell in editable else GREEN_LIGHT)
        cell.font = Font(name="Aptos", size=10, bold=True, color=INPUT_BLUE if value_cell in editable else DARK)
        cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True, indent=1)
        cell.border = border
        if value_cell in editable:
            cell.protection = Protection(locked=False)
            cell.comment = Comment("Editable estimate assumption. All connected formulas recalculate from this cell.", "User")

    total_labels = ("Total material", "Total labour", "Total labour hrs", "Direct cost", "INCLUDED ESTIMATE TOTAL")
    total_formats = (money, money, hours, money, money)
    for index, (label, number_format) in enumerate(zip(total_labels, total_formats), start=5):
        fill = TEAL if index == 9 else GRAY_100
        label_color = WHITE if index == 9 else DARK
        _merge_value(ws, f"J{index}:L{index}", label, fill=fill, color=label_color, size=10, bold=True, border=border)
        value = _merge_value(ws, f"M{index}:N{index}", 0, fill=fill if index == 9 else GREEN_LIGHT, color=WHITE if index == 9 else DARK, size=10 if index == 9 else 9, bold=True, horizontal="right", border=border, number_format=number_format)
        if index == 9:
            value.font = Font(name="Aptos", size=11, bold=True, color=WHITE)
    for row in range(4, 10):
        ws.row_dimensions[row].height = 28
    _merge_value(ws, "A8:F8", "OPTIONAL QUOTED COST", fill=CREAM, bold=True, border=border)
    _merge_value(ws, "G8:I8", 0, fill=CREAM, bold=True, horizontal="right", border=border, number_format=money)
    _merge_value(ws, "A9:I9", "Optional costs are excluded from the estimate total.", color=GRAY_600, size=10)
    ws.row_dimensions[9].height = 34

    ws = detail
    _merge_value(ws, "A1:N1", f'={settings_ref}B2&" — CONNECTED COST DETAIL"',
                 fill=DARK_NAVY, color=WHITE, size=18, bold=True)
    ws.row_dimensions[1].height = 44
    _merge_value(ws, "A2:N2", "Pale gold cells are editable. Optional cost items keep their prices and are excluded from the estimate total. Set Cost treatment to 1 for Included or 0 for Optional cost.",
                 color=GRAY_600, size=9)
    jump = _merge_value(ws, "A3:N3", "← Return to cost summary and project rates", color=TEAL_DARK, size=9)
    jump.hyperlink = "#'COST ESTIMATE'!A1"
    ws.row_dimensions[2].height = 30
    ws.row_dimensions[3].height = 24
    _section_title(ws, detail_title_row, "CONNECTED COST DETAIL", NAVY)
    headers = [
        "Scope / Category", "Item / component", "Size / specification", "Qty / per item", "Total Qty",
        "Material / unit\nSupply · installation", "Material total", "Hours / fixed price" if has_fixed_labor else "Hours / unit", "Total hours", "Labour total", "Direct cost",
        "Quoted total", "Quoted / unit", "Notes",
    ]
    for column, label in enumerate(headers, 1):
        cell = ws.cell(detail_header_row, column, label)
        cell.fill = PatternFill("solid", fgColor=YELLOW)
        cell.font = Font(name="Aptos", size=10, bold=True, color=DARK)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    ws.row_dimensions[detail_header_row].height = 40

    current_row = detail_header_row + 1
    parent_rows: list[int] = []
    line_parent_rows: list[tuple[dict[str, Any], int]] = []

    for line in lines:
        parent_row = current_row
        parent_rows.append(parent_row)
        line_parent_rows.append((line, parent_row))
        scope = line["category_key"]
        components = list(line.get("components") or []) or [{
            "item_no": "", "description": line.get("name_snapshot") or "Manual item", "quantity_per_unit": 1.0,
            "uom": line.get("uom") or "EA", "unit_material": 0.0, "material_factor": 1.0,
            "unit_hours": 0.0, "labor_factor": 1.0, "size": "", "notes": "",
        }]
        detail_start = parent_row + 1
        detail_end = detail_start + len(components) - 1

        values = {
            1: scope, 2: (line.get("display_name") or line.get("name_snapshot") or "") + ("\nRef: " + line["reference_name"] if line.get("reference_name") else ""), 3:line.get("size_snapshot") or "",
            4: float(line.get("quantity") or 0), 5: f"=D{parent_row}",
            6: f'=IF(D{parent_row}=0,0,G{parent_row}/D{parent_row})', 7: f"=SUM(G{detail_start}:G{detail_end})",
            8: f'=IF(D{parent_row}=0,0,I{parent_row}/D{parent_row})', 9: f"=SUM(I{detail_start}:I{detail_end})",
            10: f"=SUM(J{detail_start}:J{detail_end})", 11: f"=SUM(K{detail_start}:K{detail_end})",
            12: f"=SUM(L{detail_start}:L{detail_end})", 13: f'=IF(D{parent_row}=0,0,L{parent_row}/D{parent_row})',
            14: " · ".join(filter(None, [WORK_TYPES.get(line.get("pricing_work_type") or line.get("work_type_snapshot"), ""), line.get("notes")])),
        }
        for column, value in values.items():
            ws.cell(parent_row, column, value)
            if column in (1, 2, 3, 14):
                ws.cell(parent_row, column).data_type = "s"
        for cell in ws[parent_row][:14]:
            cell.fill = PatternFill("solid", fgColor=TEAL_LIGHT)
            cell.font = Font(name="Aptos", size=10, bold=True, color=DARK)
            cell.border = Border(top=Side(style="thin", color="ABCFC7"), bottom=Side(style="thin", color="CBDDD8"))
            cell.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
        for column in (1, 2, 3, 4):
            ws.cell(parent_row, column).fill = PatternFill("solid", fgColor=CREAM)
            ws.cell(parent_row, column).font = Font(name="Aptos", size=10, bold=True, color=INPUT_BLUE)
            ws.cell(parent_row, column).protection = Protection(locked=False)
        ws.cell(parent_row, 1).comment = Comment("Editable scope/category for the whole assembly. The COST ESTIMATE summary regroups automatically, including newly typed categories.", "User")

        ws.cell(parent_row, 2).comment = Comment("Editable item name. A project-only lighting reference appears on the next line in this same cell; it is not a catalogue item.", "User")
        ws.cell(parent_row, 4).comment = Comment("Editable take-off quantity. All component rows below scale from this cell.", "User")
        ws.row_dimensions[parent_row].height = max(40, 15 * max(
            sum(max(1, len(textwrap.wrap(part, width=width))) for part in str(values.get(column, "")).split("\n"))
            for column, width in ((1, 25), (2, 47), (3, 20), (14, 26))) + 12)

        material_ref = '0' if line.get('exclude_material_markup') else f'{settings_ref}$C$5'
        hours_ref = '0' if line.get('exclude_hours_markup') else f'{settings_ref}$F$7'
        final_ref = '0' if line.get('exclude_final_markup') else f'{settings_ref}$C$6'
        excluded = [label for key,label in [('exclude_material_markup','Material'),('exclude_hours_markup','Labour hours'),('exclude_final_markup','Final')] if line.get(key)]
        if excluded:
            ws.cell(parent_row,14, str(values[14] or '') + ' · Excluded mark-ups: ' + ', '.join(excluded))
        for offset, component in enumerate(components):
            row = detail_start + offset
            description = component.get("description") or ""
            size = component.get("size") or ""

            ratio = max(0.0, float(component.get("quantity_per_unit") or 0.0))
            ws.cell(row, 2, description)
            ws.cell(row, 3, size)
            ws.cell(row, 4, ratio)
            ws.cell(row, 4).comment = Comment("Editable component quantity per one parent unit. Scaled quantity = parent take-off × this ratio.", "User")
            ws.cell(row, 5, f"=$D${parent_row}*D{row}")
            if component.get('fixed_quantity'):
                ws.cell(row,5,f'=D{row}')
                ws.cell(row,4).comment=Comment('Fixed total quantity. Does not multiply by the parent take-off quantity.','User')
            if component.get('supply_quantity_is_overridden'):
                ws.cell(row,4,float(component['scaled_quantity']))
                ws.cell(row,5,f'=D{row}')
                ws.cell(row,4).comment=Comment('Total fitting supply quantity, independent of installation quantity.','User')
            ws.cell(row, 6, max(0.0, float(component.get("unit_material") or 0.0)))
            ws.cell(row, 7, f"=E{row}*F{row}*{_safe_formula_factor(component.get('material_factor'))}*(1+{material_ref})")
            ws.cell(row, 8, max(0.0, float(component.get("unit_hours") or 0.0)))
            ws.cell(row, 9, f"=E{row}*H{row}*{_safe_formula_factor(component.get('labor_factor'))}*(1+{hours_ref})")
            ws.cell(row, 10, f"=I{row}*{settings_ref}$F$5")
            if component.get("labor_pricing") == "fixed":
                ws.cell(row, 8, float(component.get("unit_labor_price") or 0))
                ws.cell(row, 9, "=0")
                ws.cell(row, 10, f"=E{row}*H{row}*{_safe_formula_factor(component.get('labor_factor'))}")
                ws.cell(row, 8).comment = Comment("Fixed labour/work price per component unit, before final mark-up. Independent of the hourly rate. No labour hours are inferred.", "User")
            if component.get('supply_quantity_is_overridden'):
                labor_base=str(ratio) if component.get('fixed_quantity') else f'$D${parent_row}*{ratio}'
                if component.get('labor_pricing')=='fixed':ws.cell(row,10,f'={labor_base}*H{row}*{_safe_formula_factor(component.get("labor_factor"))}')
                else:
                    ws.cell(row,9,f'={labor_base}*H{row}*{_safe_formula_factor(component.get("labor_factor"))}*(1+{hours_ref})')
            ws.cell(row, 11, f"=G{row}+J{row}")
            ws.cell(row, 12, f"=K{row}*(1+{final_ref})")
            ws.cell(row, 14, " · ".join(filter(None, [
                "Fixed labour price; hours not provided" if component.get("labor_pricing") == "fixed" else "",
                "Fixed total quantity" if component.get("fixed_quantity") else "",
                component.get("notes"),
            ])))
            for cell in ws[row][:14]:
                cell.font = Font(name="Aptos", size=9.5, color=DARK)
                cell.fill = PatternFill("solid", fgColor=WHITE if offset % 2 == 0 else "F8FAFB")
                cell.border = _row_border()
                cell.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
            ws.cell(row, 2).font = Font(name="Aptos", size=9.5, bold=False, color=LINK_GREEN)
            for column in (4, 6, 8):
                ws.cell(row, column).fill = PatternFill("solid", fgColor=CREAM)
                ws.cell(row, column).font = Font(name="Aptos", size=9.5, color=INPUT_BLUE)
                ws.cell(row, column).protection = Protection(locked=False)

            ws.cell(row, 2).alignment = Alignment(vertical="center", indent=1, wrap_text=True)
            ws.row_dimensions[row].outlineLevel = 1
            ws.row_dimensions[row].height = max(25, 14 * max(
                len(textwrap.wrap(description, width=46)),
                len(textwrap.wrap(size, width=20)),
                len(textwrap.wrap(str(ws.cell(row, 14).value or ""), width=28))) + 10)
        current_row = detail_end + 1

    for line, parent_row in line_parent_rows:
        flag=ws.cell(parent_row,inclusion_flag_column,int(line.get('included_in_total',True)))
        flag.number_format='[=1]"Included";[=0]"Optional cost";General'
        flag.fill=PatternFill('solid',fgColor=CREAM)
        flag.font=Font(name='Aptos',bold=True,color=INPUT_BLUE)
        flag.alignment=Alignment(horizontal='center',vertical='center')
        flag.protection=Protection(locked=False)
        flag.comment=Comment('Included (1) adds this item to estimate totals. Optional cost (0) retains its prices and quantities in a separate subtotal. The initial value follows its section in TEC ConEst.','TEC ConEst')
        for source,target in included_columns.items():
            ws[f'{target}{parent_row}']=f'={source}{parent_row}*P{parent_row}'
        ws.conditional_formatting.add(f'A{parent_row}:P{parent_row}',FormulaRule(
            formula=[f'$P{parent_row}=0'],fill=PatternFill('solid',fgColor='E9E5DC')))
    for column in included_columns.values():ws.column_dimensions[column].hidden=True
    total_row = current_row
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=5)
    ws.cell(total_row, 1, "INCLUDED ESTIMATE TOTAL")
    ws.cell(total_row, 7, _sum_cells("Q", parent_rows))
    ws.cell(total_row, 9, _sum_cells("R", parent_rows))
    ws.cell(total_row, 10, _sum_cells("S", parent_rows))
    ws.cell(total_row, 11, _sum_cells("T", parent_rows))
    ws.cell(total_row, 12, _sum_cells("U", parent_rows))
    for cell in ws[total_row][:14]:
        cell.fill = PatternFill("solid", fgColor=DARK_NAVY)
        cell.font = Font(name="Aptos", size=10, bold=True, color=WHITE)
        cell.border = border
        cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[total_row].height = 30
    optional_total_row = total_row + 1
    _merge_value(ws, f"A{optional_total_row}:E{optional_total_row}", "OPTIONAL COST TOTAL (excluded)",
                 fill=CREAM, bold=True, border=border)
    for source in ("G", "I", "J", "K", "L"):
        # Parent rows already contain every component once, with the same line
        # mark-ups as the included estimate. Subtract its included roll-up so
        # editing an item's cost treatment updates both totals immediately.
        ws[f'{source}{optional_total_row}'] = _sum_cells(source, parent_rows) + f'-{source}{total_row}'
    for cell in ws[optional_total_row][:16]:
        cell.fill = PatternFill("solid", fgColor=CREAM)
        cell.font = Font(name="Aptos", size=10, bold=True, color=DARK)
        cell.border = border
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[optional_total_row].height = 32

    overview["M5"] = f"={detail_ref}G{total_row}"
    overview["M6"] = f"={detail_ref}J{total_row}"
    overview["M7"] = f"={detail_ref}I{total_row}"
    overview["M8"] = f"={detail_ref}K{total_row}"
    overview["M9"] = f"={detail_ref}L{total_row}"
    overview["G8"] = f"={detail_ref}L{optional_total_row}"
    overview["G8"].number_format = money
    for address, number_format in (("M5", money), ("M6", money), ("M7", hours), ("M8", money), ("M9", money)):
        overview[address].number_format = number_format

    for row in range(detail_header_row + 1, optional_total_row + 1):
        for column in (4, 5):
            ws.cell(row, column).number_format = quantity
        for column in (6, 7, 10, 11, 12, 13):
            ws.cell(row, column).number_format = money
        for column in (8, 9):
            ws.cell(row, column).number_format = hours
        for column in range(4, 14):
            ws.cell(row, column).alignment = Alignment(horizontal="right", vertical="center", wrap_text=True, indent=1)

    def unit_format(unit: str) -> str:
        return '0.00" ' + unit.replace('\\', '\\\\').replace('"', '\\"') + '"'

    for line, parent_row in line_parent_rows:
        for column in (4, 5):
            ws.cell(parent_row, column).number_format = unit_format(line.get("uom") or "EA")
        for offset, component in enumerate(line["components"], 1):
            ws.cell(parent_row + offset, 5).number_format = unit_format(component.get("uom") or "EA")
            if component.get("labor_pricing") == "fixed":
                ws.cell(parent_row + offset, 8).number_format = money

    # Scalar helper formulas keep category grouping compatible with older Excel
    # too. One hidden row per parent prevents child costs being counted twice.
    helper_first_row = optional_total_row + 2
    helper_last_row = helper_first_row + len(parent_rows)*2 - 1
    for index,(line,parent_row) in enumerate(line_parent_rows):
        components=line.get('components') or []
        final_ref='0' if line.get('exclude_final_markup') else f'{settings_ref}$C$6'
        supply_offset=next((i for i,c in enumerate(components) if c.get('is_parent')),0)
        supply_row=parent_row+1+supply_offset
        supply_rows=[parent_row+1+i for i,c in enumerate(components) if i==supply_offset or c.get('is_supply_copy')]
        supply_formula='G'+str(supply_row) if len(supply_rows)==1 else 'SUM('+','.join(f'G{r}' for r in supply_rows)+')'
        lighting=f'OR(A{parent_row}="Lighting",A{parent_row}="Emergency & Exit Lighting")'
        # Parent material rates are shown as two linked values in the same column.
        # Component F cells remain numeric inputs, preserving the connected workbook.
        supply_unit=f'IF(D{parent_row}=0,0,IF({lighting},{supply_formula}/D{parent_row},0))'
        install_unit=f'IF(D{parent_row}=0,0,(G{parent_row}-IF({lighting},{supply_formula},0))/D{parent_row})'
        ws.cell(parent_row,6,f'="Supply "&TEXT({supply_unit},"#,##0.00")&CHAR(10)&"Install "&TEXT({install_unit},"#,##0.00")')
        ws.cell(parent_row,6).comment=Comment('Supply = lighting fitting material per estimate unit. Install = remaining installation materials per unit. Both include material mark-up; labour is separate. Edit component material prices below.','TEC ConEst')
        for part in range(2):
            row=helper_first_row+index*2+part
            if part==0:
                ws.cell(row,1,f'=IF({lighting},A{parent_row}&" / Supply cost",IF(A{parent_row}="","(Unassigned)",A{parent_row}))')
                formulas={3:f'IF({lighting},{supply_formula},G{parent_row})',4:f'IF({lighting},0,I{parent_row})',
                    5:f'IF({lighting},0,J{parent_row})',6:f'IF({lighting},{supply_formula}*(1+{final_ref}),L{parent_row})',7:f'IF({lighting},0,1)'}
            else:
                ws.cell(row,1,f'=IF({lighting},A{parent_row}&" / Installation cost","")')
                formulas={3:f'IF({lighting},G{parent_row}-C{row-1},0)',4:f'IF({lighting},I{parent_row},0)',
                    5:f'IF({lighting},J{parent_row},0)',6:f'IF({lighting},L{parent_row}-F{row-1},0)',7:f'IF({lighting},1,0)'}
            excluded_condition=f'P{parent_row}=0' if part==0 else f'AND(P{parent_row}=0,{lighting})'
            ws.cell(row,1,ws.cell(row,1).value+f'&IF({excluded_condition}," [Optional cost]","")')
            ws.cell(row,2,'=1' if row==helper_first_row else f'=IF(A{row}="",0,IF(SUMPRODUCT(--($A${helper_first_row}:A{row}=A{row}))=1,MAX($B${helper_first_row}:B{row-1})+1,0))')
            for col,formula in formulas.items():ws.cell(row,col,'='+formula)
            ws.row_dimensions[row].hidden=True

    ws = overview
    scope_title_row = 11
    scope_header_row = scope_title_row + 1
    scope_first_row = scope_header_row + 1
    scope_last_row = scope_first_row + len(parent_rows)*2
    _section_title(ws, scope_title_row, "SCOPE COST SUMMARY", GREEN)
    scope_headers = (("A", "C", "Scope / Category"), ("D", "E", "Assemblies"),
                     ("F", "H", "Total Material"), ("I", "J", "Total Hours"),
                     ("K", "L", "Total Labour"), ("M", "N", "Quoted Total"))
    for start, end, label in scope_headers:
        _merge_value(ws, f"{start}{scope_header_row}:{end}{scope_header_row}", label,
                     fill=YELLOW, size=10, bold=True, horizontal="center", border=border)
    ws.row_dimensions[scope_header_row].height = 30
    categories = f"{detail_ref}$A${helper_first_row}:$A${helper_last_row}"
    scope_numbers = f"{detail_ref}$B${helper_first_row}:$B${helper_last_row}"
    assembly_count = "SUM("+",".join(f"{detail_ref}P{parent}" for parent in parent_rows)+")" if parent_rows else "0"
    for index, row in enumerate(range(scope_first_row, scope_last_row + 1), 1):
        is_total = f"{index}=MAX({scope_numbers})+1" if parent_rows else "TRUE"
        label = f'=IFERROR(INDEX({categories},MATCH({index},{scope_numbers},0)),IF({is_total},"INCLUDED TOTAL",""))' if parent_rows else "INCLUDED TOTAL"
        _merge_value(ws, f"A{row}:C{row}", label, size=10)
        for start, end, source, total, fmt in (
            ("D", "E", None, assembly_count, "0"),
            ("F", "H", "C", f"{detail_ref}G{total_row}", money),
            ("I", "J", "D", f"{detail_ref}I{total_row}", hours),
            ("K", "L", "E", f"{detail_ref}J{total_row}", money),
            ("M", "N", "F", f"{detail_ref}L{total_row}", money),
        ):
            # Equality compares category text literally, including * ? and ~.
            match = f'({categories}=A{row})'
            aggregate = f'SUMPRODUCT({match}*{detail_ref}$G${helper_first_row}:$G${helper_last_row})' if source is None else f'SUMPRODUCT({match}*{detail_ref}${source}${helper_first_row}:${source}${helper_last_row})'
            formula = f'=IF(A{row}="","",IF({is_total},{total},{aggregate}))' if parent_rows else f"={total}"
            _merge_value(ws, f"{start}{row}:{end}{row}", formula, size=10,
                         bold=start == "M", horizontal="right", number_format=fmt)
        ws.row_dimensions[row].height = 40
        ws.conditional_formatting.add(f"A{row}:N{row}", FormulaRule(
            formula=[f'$A{row}="INCLUDED TOTAL"'], fill=PatternFill("solid", fgColor=TEAL),
            font=Font(name="Aptos", size=10, bold=True, color=WHITE), stopIfTrue=True))
        ws.conditional_formatting.add(f"A{row}:N{row}", FormulaRule(
            formula=[f'AND($A{row}<>"",MOD(ROW(),2)=0)'], fill=PatternFill("solid", fgColor=GREEN_LIGHT)))
    jump = _merge_value(ws, "A10:N10", "Open connected cost detail →  |  Category and quantity edits on the detail tab update this summary.",
                        color=TEAL_DARK, size=9)
    jump.hyperlink = "#'CONNECTED COST DETAIL'!A1"
    ws.row_dimensions[10].height = 24

    def nonnegative_validation(sheet: Any) -> DataValidation:
        rule = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1=0, allow_blank=False)
        rule.errorTitle = "Use a non-negative number"
        rule.error = "Enter a quantity or price of zero or greater."
        rule.showErrorMessage = True
        sheet.add_data_validation(rule)
        return rule

    settings_validation = nonnegative_validation(overview)
    for address in ("C5", "C6", "F5", "F6", "F7", "I5"):
        settings_validation.add(overview[address])
    detail_validation = nonnegative_validation(detail)
    for line, parent_row in line_parent_rows:
        detail_validation.add(detail.cell(parent_row, 4))
        for offset in range(1, max(1, len(line["components"])) + 1):
            for column in (4, 6, 8):
                detail_validation.add(detail.cell(parent_row + offset, column))

    for sheet in (overview, detail):
        _set_widths(sheet, {
            "A": 27, "B": 18, "C": 40, "D": 12, "E": 12, "F": 14, "G": 16,
            "H": 14, "I": 13, "J": 15, "K": 15, "L": 16, "M": 15, "N": 30,
        })
        sheet.sheet_view.showGridLines = False
        sheet.sheet_view.zoomScale = 80
        sheet.sheet_properties.outlinePr.summaryBelow = False
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_margins = PageMargins(left=0.25, right=0.25, top=0.35, bottom=0.45, header=0.15, footer=0.2)
        sheet.print_options.horizontalCentered = True
        sheet.oddFooter.center.text = "Page &[Page] of &[Pages]"
        sheet.oddFooter.right.text = "Generated by TEC ConEst"
        sheet.sheet_properties.pageSetUpPr.autoPageBreaks = False
    _set_widths(overview, {"A": 13, "B": 13, "C": 18, "D": 10, "E": 10, "F": 14, "G": 10,
                           "H": 10, "I": 12, "J": 12, "K": 12, "L": 12, "M": 13, "N": 13})
    overview.freeze_panes = f"A{scope_first_row}"
    overview.print_title_rows = f"${scope_header_row}:${scope_header_row}"
    overview.print_area = f"A1:N{scope_last_row}"
    overview.sheet_properties.tabColor = GREEN
    detail.column_dimensions["F"].width = 21
    detail.column_dimensions["B"].width = 49
    detail.column_dimensions["C"].width = 21
    detail.freeze_panes = f"A{detail_header_row + 1}"
    detail.print_title_rows = f"${detail_header_row}:${detail_header_row}"
    detail.print_area = f"A1:N{total_row}"
    detail.sheet_properties.tabColor = TEAL

    # Work classification is editable on parent rows and formula-linked to the summary.
    work_labels=['Installation','Supply only','Supply & installation','Relocation','Demolition','Relocation and Demolition']
    detail.cell(detail_header_row,15,'Work type').font=Font(name='Aptos',bold=True,color=DARK)
    detail.column_dimensions['O'].width=30
    detail.cell(detail_header_row,16,'Cost treatment').font=Font(name='Aptos',bold=True,color=DARK)
    detail.cell(detail_header_row,16).alignment=Alignment(wrap_text=True)
    detail.column_dimensions['P'].width=20
    include_rule=DataValidation(type='whole',operator='between',formula1=0,formula2=1,allow_blank=False)
    include_rule.errorTitle='Choose a cost treatment';include_rule.error='Enter 1 for Included or 0 for Optional cost.';include_rule.showErrorMessage=True
    detail.add_data_validation(include_rule)
    for _,parent in line_parent_rows:include_rule.add(detail.cell(parent,16))
    for line,parent in line_parent_rows:
        kind=line.get('work_type_snapshot') or 'assembly'
        label='Installation' if kind in ('assembly','installation_only') else WORK_TYPES.get(kind,'Installation')
        cell=detail.cell(parent,15,label)
        cell.fill=PatternFill('solid',fgColor=CREAM)
        cell.font=Font(name='Aptos',color=INPUT_BLUE)
        cell.protection=Protection(locked=False)
    rule=DataValidation(type='list',formula1='"'+','.join(work_labels)+'"')
    rule.errorTitle='Choose a work type';rule.error='Use a work type from the list.';rule.showErrorMessage=True
    detail.add_data_validation(rule)
    for _,parent in line_parent_rows:rule.add(detail.cell(parent,15))
    row=scope_last_row
    overview.print_area=f'A1:N{row}'
    detail.print_area=f'A1:P{optional_total_row}'

    builder_lines = sum(max(1, (len(name) + 39) // 40) for name in project.get('builders') or [])
    overview.row_dimensions[2].height = max(overview.row_dimensions[2].height or 30, min(409, 16 * builder_lines + 12))
    from .estimate_areas import excel
    excel(wb,line_parent_rows,data.get('area_names',[]))
    optional_formula=overview['G8'].value
    for merged in list(overview.merged_cells.ranges):
        if merged.min_row==8 and merged.max_col<=9:overview.unmerge_cells(str(merged))
    for col in range(1,10):overview.cell(8,col).value=None
    for merged in list(overview.merged_cells.ranges):
        if merged.min_row<=10<=merged.max_row:overview.unmerge_cells(str(merged))
    overview.merge_cells('A10:I10')
    _merge_value(overview,'J10:L10','OPTIONAL QUOTED COST',fill=CREAM,bold=True)
    _merge_value(overview,'M10:N10',optional_formula,fill=CREAM,bold=True,number_format=money)

    wb.save(output)
    return output


def default_export_name(project_name: str) -> str:
    return safe_filename(f"{project_name} - Cost Estimate.xlsx")
