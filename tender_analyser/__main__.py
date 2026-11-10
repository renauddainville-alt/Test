"""Command line.

  python -m tender_analyser tender.pdf                      rule-based, offline
  python -m tender_analyser tender.pdf annex.pdf --ai       Claude analysis (one tender, several files)
  python -m tender_analyser tender.pdf --ai --profile company_profile.md
  python -m tender_analyser tender.pdf --ask "Quel est le chiffre d'affaires minimum ?"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .extract import TenderAnalysis, analyse_pdf, days_until
from .report import write_report


def _print_summary(a: TenderAnalysis, out: Path, label: str) -> None:
    print(f"\n✓ {label}  ({a.pages} pages, language: {a.language})")
    for k, v in a.info.items():
        if v:
            print(f"  {k:<22} {v}")
    sub = a.submission_deadline
    if sub:
        when = f"{sub.when:%d/%m/%Y}" + (f" {sub.when:%H:%M}" if sub.has_time else "")
        print(f"  {'Submission deadline':<22} {when}  ({days_until(sub.when)} days left)")
    else:
        print(f"  {'Submission deadline':<22} not found — check manually")
    crit = sum(r.level == "Critical" for r in a.requirements)
    print(f"  {'Lots':<22} {len(a.lots) or a.lots_note or 0}")
    print(f"  {'Award criteria':<22} {len(a.award_criteria)}")
    print(f"  {'Requirements':<22} {len(a.requirements)} ({crit} critical)")
    print(f"  {'Documents to provide':<22} {len(a.documents)}")
    print(f"  → {out}")


def _confirm_upload(pdfs: list[Path], assume_yes: bool) -> bool:
    if assume_yes:
        return True
    names = ", ".join(p.name for p in pdfs)
    print(f"AI mode sends {names} to the Anthropic API.\n"
          "Check the tender's confidentiality clause and your company policy first.")
    try:
        return input("Continue? [y/N] ").strip().lower() in ("y", "yes", "o", "oui", "j", "ja")
    except EOFError:
        return False


def _progress():
    count = 0

    def tick():
        nonlocal count
        count += 1
        if count % 150 == 0:
            print(".", end="", flush=True)
    return tick


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="tender_analyser",
        description="Turn a tender PDF into an Excel compliance matrix (FR / NL / EN). "
                    "Rule-based and offline by default; --ai adds a Claude analysis and a bid assessment.",
    )
    p.add_argument("pdf", nargs="+", type=Path, help="Tender PDF file(s)")
    p.add_argument("-o", "--output", type=Path,
                   help="Output .xlsx (default: <first pdf name>_analysis.xlsx, or _ai_analysis.xlsx with --ai)")
    ai = p.add_argument_group("AI mode (Claude API — the PDFs are sent to Anthropic)")
    ai.add_argument("--ai", action="store_true",
                    help="Analyse with Claude; all PDFs are treated as one tender (main document + annexes)")
    ai.add_argument("--ask", metavar="QUESTION", help="Ask a question about the tender; answer with page references")
    ai.add_argument("--profile", type=Path,
                    help="Company profile (Markdown/text) for the go/no-go fit assessment "
                         "(or set TENDER_COMPANY_PROFILE)")
    ai.add_argument("--model", default=None, help="Claude model (default: claude-opus-5-5)")
    ai.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default=None,
                    help="Reasoning effort (default: high for --ai, medium for --ask)")
    ai.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation before uploading")
    args = p.parse_args(argv)

    for pdf in args.pdf:
        if not pdf.is_file():
            print(f"✗ File not found: {pdf}", file=sys.stderr)
            return 1

    if args.ai or args.ask:
        from . import ai as ai_mod

        if not _confirm_upload(args.pdf, args.yes):
            print("Cancelled — nothing was sent.")
            return 1
        model = args.model or ai_mod.DEFAULT_MODEL
        try:
            if args.ask:
                answer, cites, run = ai_mod.ask(args.pdf, args.ask, model=model, effort=args.effort or "medium")
                print(f"\n{answer}\n")
                if cites:
                    print("Sources: " + "; ".join(f"{t} p.{pg}" if pg else t for t, pg in cites))
                cost = run.estimated_cost_usd
                if cost is not None:
                    print(f"(≈ ${cost:.2f}; {run.cache_read_tokens:,} tokens read from cache)")
                return 0

            print(f"Analysing with {model}", end="", flush=True)
            result = ai_mod.ai_analyse(args.pdf, profile=ai_mod.load_profile(args.profile), model=model,
                                       effort=args.effort or ai_mod.DEFAULT_EFFORT, on_progress=_progress())
            print()
        except Exception as e:  # noqa: BLE001 — report any API/SDK failure and fall back
            print(f"\n✗ AI analysis failed: {e}", file=sys.stderr)
            if "authentication" in str(e).lower() or "api_key" in str(e).lower():
                print("  Set your key first: export ANTHROPIC_API_KEY=... (see README, 'AI mode')", file=sys.stderr)
            if args.ask:
                return 1
            print("Falling back to the rule-based analysis.", file=sys.stderr)
        else:
            a = result.analysis
            out = args.output or args.pdf[0].with_name(f"{args.pdf[0].stem}_ai_analysis.xlsx")
            write_report(a, out, ai=result)
            _print_summary(a, out, a.source)
            b = result.insights
            print(f"  {'Recommendation':<22} {b.recommendation} — {b.recommendation_rationale}")
            if result.run and result.run.estimated_cost_usd is not None:
                print(f"  {'Estimated API cost':<22} ≈ ${result.run.estimated_cost_usd:.2f}")
            return 0

    if args.output and len(args.pdf) > 1:
        p.error("--output can only be used with a single PDF in rule-based mode")
    for pdf in args.pdf:
        a = analyse_pdf(pdf)
        out = args.output or pdf.with_name(f"{pdf.stem}_analysis.xlsx")
        write_report(a, out)
        _print_summary(a, out, pdf.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
