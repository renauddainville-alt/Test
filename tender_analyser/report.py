"""Write a TenderAnalysis to a formatted Excel workbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .extract import TenderAnalysis, days_until

NAVY = "1F3A5F"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=NAVY)
LABEL_FONT = Font(bold=True, color=NAVY)
THIN = Side(style="thin", color="D0D7E2")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

LEVEL_FILLS = {
    "Critical": PatternFill("solid", fgColor="F8D7DA"),
    "Mandatory": PatternFill("solid", fgColor="FFF3CD"),
    "Desirable": PatternFill("solid", fgColor="E2F0D9"),
}
STATUS_OPTIONS = ["To review", "Compliant", "Partially compliant", "Non-compliant", "Not applicable"]


def _table(ws, headers: list[str], rows: list[list], widths: list[int], start_row: int = 1) -> None:
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for r, row in enumerate(rows, start=start_row + 1):
        for c, val in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.alignment, cell.border = WRAP, BORDER
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(headers))}{start_row + len(rows)}"


def _summary(ws, a: TenderAnalysis, today: date) -> None:
    ws.title = "Summary"
    ws["A1"] = "Tender analysis"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Generated {today:%d/%m/%Y} from {a.source} — automatic extraction, verify against the source document."
    ws["A2"].font = Font(italic=True, color="666666")

    sub = a.submission_deadline
    if sub:
        left = days_until(sub.when, today)
        sub_txt = f"{sub.when:%d/%m/%Y}" + (f" {sub.when:%H:%M}" if sub.has_time else "")
        sub_txt += f"  ({left} days left)" if left >= 0 else "  (passed)"
    else:
        sub_txt = "Not found — check the document"

    counts = {lvl: sum(1 for r in a.requirements if r.level == lvl) for lvl in LEVEL_FILLS}
    rows = [
        ("Source file", a.source),
        ("Pages", a.pages),
        ("Language", {"FR": "French", "NL": "Dutch", "EN": "English"}.get(a.language, a.language)),
        *[(k, v) for k, v in a.info.items()],
        ("Submission deadline", sub_txt),
        ("Lots", len(a.lots) or a.lots_note or "None found"),
        ("Award criteria found", len(a.award_criteria)),
        ("Requirements found", len(a.requirements)),
        ("  of which critical (exclusion risk)", counts["Critical"]),
        ("  of which mandatory", counts["Mandatory"]),
        ("  of which desirable", counts["Desirable"]),
        ("Documents to provide", len(a.documents)),
    ]
    for i, (k, v) in enumerate(rows, start=4):
        ws.cell(row=i, column=1, value=k).font = LABEL_FONT
        c = ws.cell(row=i, column=2, value=v)
        c.alignment = WRAP
        if k == "Submission deadline":
            c.font = Font(bold=True, color="B00020" if sub and days_until(sub.when, today) <= 14 else "000000")
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 90


def write_report(a: TenderAnalysis, out_path: str | Path, today: date | None = None) -> Path:
    today = today or date.today()
    wb = Workbook()
    _summary(wb.active, a, today)

    # Deadlines
    ws = wb.create_sheet("Deadlines")
    _table(ws, ["Type", "Date", "Time", "Days left", "Page", "Context"],
           [[d.kind, d.when.date(), d.when.strftime("%H:%M") if d.has_time else "",
             days_until(d.when, today), d.page, d.context] for d in a.deadlines],
           [30, 12, 8, 10, 7, 100])
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for c in row:
            c.number_format = "DD/MM/YYYY"
    for r, d in enumerate(a.deadlines, start=2):
        if d.kind == "Submission of offers":
            for c in ws[r]:
                c.font = Font(bold=True)

    # Lots
    ws = wb.create_sheet("Lots")
    _table(ws, ["Lot", "Title", "Page", "Bid? (Y/N)", "Comments"],
           [[l.number, l.title, l.page, "", ""] for l in a.lots], [6, 80, 7, 11, 40])

    # Award criteria
    ws = wb.create_sheet("Award criteria")
    _table(ws, ["Criterion", "Weight", "Page", "Section", "KEYES win theme / proof points"],
           [[c.criterion, c.weight, c.page, c.section, ""] for c in a.award_criteria], [50, 12, 7, 35, 60])

    # Compliance matrix
    ws = wb.create_sheet("Compliance matrix")
    headers = ["ID", "Requirement", "Category", "Level", "Doc?", "Page", "Section",
               "Status", "Owner", "KEYES response / evidence", "Comments"]
    rows = [[r.id, r.text, r.category, r.level, "Yes" if r.is_document else "", r.page, r.section,
             "To review", "", "", ""] for r in a.requirements]
    _table(ws, headers, rows, [9, 80, 22, 11, 6, 6, 28, 18, 14, 50, 30])
    for i, r in enumerate(a.requirements, start=2):
        ws.cell(row=i, column=4).fill = LEVEL_FILLS[r.level]
    if rows:
        last = len(rows) + 1
        dv = DataValidation(type="list", formula1='"' + ",".join(STATUS_OPTIONS) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"H2:H{last}")
        rng = f"H2:H{last}"
        for text, color in [("Compliant", "C6EFCE"), ("Partially compliant", "FFEB9C"),
                            ("Non-compliant", "FFC7CE"), ("Not applicable", "EDEDED")]:
            ws.conditional_formatting.add(
                rng, FormulaRule(formula=[f'$H2="{text}"'], fill=PatternFill("solid", fgColor=color)))

    # Documents to provide
    ws = wb.create_sheet("Documents to provide")
    _table(ws, ["ID", "Document / proof requested", "Level", "Page", "Prepared? (Y/N)", "Owner"],
           [[r.id, r.text, r.level, r.page, "", ""] for r in a.documents], [9, 90, 11, 6, 15, 14])

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
