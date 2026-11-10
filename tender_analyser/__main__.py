"""Command line: python -m tender_analyser <tender.pdf> [more.pdf ...] [-o output.xlsx]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .extract import analyse_pdf, days_until
from .report import write_report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="tender_analyser",
        description="Extract deadlines, lots, award criteria and requirements from a tender PDF "
                    "into an Excel compliance matrix (FR / NL / EN).",
    )
    p.add_argument("pdf", nargs="+", type=Path, help="Tender PDF file(s)")
    p.add_argument("-o", "--output", type=Path,
                   help="Output .xlsx (only with a single PDF; default: <pdf name>_analysis.xlsx)")
    args = p.parse_args(argv)

    if args.output and len(args.pdf) > 1:
        p.error("--output can only be used with a single PDF")

    for pdf in args.pdf:
        if not pdf.is_file():
            print(f"✗ File not found: {pdf}", file=sys.stderr)
            return 1
        a = analyse_pdf(pdf)
        out = args.output or pdf.with_name(f"{pdf.stem}_analysis.xlsx")
        write_report(a, out)

        print(f"\n✓ {pdf.name}  ({a.pages} pages, language: {a.language})")
        for k, v in a.info.items():
            if v:
                print(f"  {k:<22} {v}")
        sub = a.submission_deadline
        if sub:
            print(f"  {'Submission deadline':<22} {sub.when:%d/%m/%Y %H:%M}  ({days_until(sub.when)} days left)")
        else:
            print(f"  {'Submission deadline':<22} not found — check manually")
        crit = sum(r.level == "Critical" for r in a.requirements)
        print(f"  {'Lots':<22} {len(a.lots) or a.lots_note or 0}")
        print(f"  {'Award criteria':<22} {len(a.award_criteria)}")
        print(f"  {'Requirements':<22} {len(a.requirements)} ({crit} critical)")
        print(f"  {'Documents to provide':<22} {len(a.documents)}")
        print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
