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


def _summary(ws, a: TenderAnalysis, today: date, method: str = "Rule-based extraction") -> None:
    ws.title = "Summary"
    ws["A1"] = "Tender analysis"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (f"Generated {today:%d/%m/%Y} from {a.source} — {method.lower()}, "
                "verify against the source document.")
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
        ("Analysis method", method),
        ("Source file", a.source),
        ("Pages", a.pages),
        ("Language", {"FR": "French", "NL": "Dutch", "EN": "English", "DE": "German"}.get(a.language, a.language)),
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


def _bid_assessment(wb: Workbook, ai) -> None:
    b = ai.insights
    ws = wb.create_sheet("Bid assessment", 1)
    ws["A1"] = "Bid assessment (AI-generated — review before deciding)"
    ws["A1"].font = TITLE_FONT
    colors = {"Go": "C6EFCE", "Go with conditions": "FFEB9C", "No-go": "FFC7CE"}
    row = 3

    def label(text):
        nonlocal row
        ws.cell(row=row, column=1, value=text).font = LABEL_FONT
        return ws.cell(row=row, column=1)

    def put(text, value):
        nonlocal row
        label(text)
        c = ws.cell(row=row, column=2, value=value)
        c.alignment = WRAP
        row += 1
        return c

    c = put("Recommendation", b.recommendation)
    c.font = Font(bold=True, size=13)
    if b.recommendation in colors:
        c.fill = PatternFill("solid", fgColor=colors[b.recommendation])
    put("Why", b.recommendation_rationale)
    put("Executive summary", b.executive_summary)
    for title, items in [("Scope", b.scope_summary), ("Key risks", b.key_risks),
                         ("Next actions", b.next_actions),
                         ("Questions for the buyer", b.clarification_questions)]:
        put(title, "\n".join(f"• {x}" for x in items) if items else "—")

    row += 1
    if b.fit_assessment:
        ws.cell(row=row, column=1, value="Fit against company profile").font = LABEL_FONT
        row += 1
        for col, h in enumerate(["Requirement", "Status", "Rationale"], start=1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        fit_colors = {"Met": "C6EFCE", "Gap": "FFC7CE", "Unknown": "EDEDED"}
        for f in b.fit_assessment:
            row += 1
            for col, v in enumerate([f.requirement, f.status, f.rationale], start=1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.alignment, cell.border = WRAP, BORDER
            ws.cell(row=row, column=2).fill = PatternFill("solid", fgColor=fit_colors[f.status])
    else:
        put("Fit against company profile", "No company profile provided (use --profile).")

    if ai.run:
        row += 2
        r = ai.run
        cost = r.estimated_cost_usd
        put("Model", r.served_by or r.model)
        put("Tokens", f"{r.input_tokens:,} input + {r.cache_write_tokens:,} cache write + "
                      f"{r.cache_read_tokens:,} cache read, {r.output_tokens:,} output")
        if cost is not None:
            put("Estimated API cost", f"≈ ${cost:.2f}")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 110
    ws.column_dimensions["C"].width = 70


def write_report(a: TenderAnalysis, out_path: str | Path, today: date | None = None, ai=None) -> Path:
    """Write the workbook. `ai` is an optional ai.AIResult adding the bid assessment and AI columns."""
    today = today or date.today()
    wb = Workbook()
    _summary(wb.active, a, today, "AI analysis (Claude)" if ai else "Rule-based extraction")
    if ai:
        _bid_assessment(wb, ai)

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
    if ai and ai.award_details:
        _table(ws, ["Criterion", "Weight", "Page", "Scoring method", "Suggested win theme (AI)",
                    "KEYES win theme / proof points"],
               [[c.criterion, c.weight, c.page, c.scoring_method, c.win_theme, ""] for c in ai.award_details],
               [35, 10, 7, 60, 60, 50])
    else:
        _table(ws, ["Criterion", "Weight", "Page", "Section", "KEYES win theme / proof points"],
               [[c.criterion, c.weight, c.page, c.section, ""] for c in a.award_criteria], [50, 12, 7, 35, 60])

    # Compliance matrix
    ws = wb.create_sheet("Compliance matrix")
    summaries = ai.requirement_summaries if ai else {}
    headers = ["ID", "Requirement"] + (["Summary (EN)"] if summaries else []) + [
        "Category", "Level", "Doc?", "Page", "Section", "Status", "Owner", "KEYES response / evidence", "Comments"]
    rows = [[r.id, r.text] + ([summaries.get(r.id, "")] if summaries else []) +
            [r.category, r.level, "Yes" if r.is_document else "", r.page, r.section, "To review", "", "", ""]
            for r in a.requirements]
    widths = [9, 80] + ([45] if summaries else []) + [22, 11, 6, 6, 28, 18, 14, 50, 30]
    _table(ws, headers, rows, widths)
    level_col = headers.index("Level") + 1
    status = get_column_letter(headers.index("Status") + 1)
    for i, r in enumerate(a.requirements, start=2):
        ws.cell(row=i, column=level_col).fill = LEVEL_FILLS[r.level]
    if rows:
        last = len(rows) + 1
        dv = DataValidation(type="list", formula1='"' + ",".join(STATUS_OPTIONS) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        rng = f"{status}2:{status}{last}"
        dv.add(rng)
        for text, color in [("Compliant", "C6EFCE"), ("Partially compliant", "FFEB9C"),
                            ("Non-compliant", "FFC7CE"), ("Not applicable", "EDEDED")]:
            ws.conditional_formatting.add(
                rng, FormulaRule(formula=[f'${status}2="{text}"'], fill=PatternFill("solid", fgColor=color)))

    # Documents to provide
    ws = wb.create_sheet("Documents to provide")
    _table(ws, ["ID", "Document / proof requested", "Level", "Page", "Prepared? (Y/N)", "Owner"],
           [[r.id, r.text, r.level, r.page, "", ""] for r in a.documents], [9, 90, 11, 6, 15, 14])

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
