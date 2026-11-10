"""Claude-powered tender analysis (optional).

Sends the tender PDF(s) to the Claude API, which reads them natively (tables,
scanned pages, footnotes included) and returns a structured analysis validated
against a Pydantic schema. The result is mapped onto the same TenderAnalysis
used by the rule-based extractor, plus bid-decision insights.

The PDF content leaves your machine: check the tender's confidentiality clause
and your company policy before using this mode.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .extract import AwardCriterion, Deadline, Lot, Requirement, TenderAnalysis

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "high"
MAX_PDF_BYTES = 30 * 1024 * 1024  # API request limit is 32 MB, base64 adds ~33%

# ---------------------------------------------------------------------------
# Output schema (what Claude must return)
# ---------------------------------------------------------------------------

Category = Literal[
    "Exclusion", "Selection – financial", "Selection – technical", "Security & compliance",
    "Staffing / profiles", "Service levels / SLA", "Technical", "Pricing", "Award",
    "Administrative", "Contractual", "General",
]
Level = Literal["Critical", "Mandatory", "Desirable"]
DeadlineKind = Literal[
    "Submission of offers", "Opening of offers", "Questions deadline", "Site visit / information session",
    "Request to participate", "Contract start", "Award / notification", "Publication",
    "Reference period (selection)", "Other date",
]


class AIKeyInfo(BaseModel):
    title: str = Field(description="Subject of the contract, in the document's language")
    contracting_authority: str
    reference: str
    procedure: str
    contract_type: str = Field(description="Supplies / services / works, and pricing type if stated")
    estimated_value: str = Field(description="Amount with currency and VAT mention, or 'Not stated'")
    contract_duration: str
    offer_validity: str
    lots: str = Field(description="e.g. 'Not divided into lots' or '3 lots'")
    cpv_codes: list[str]
    submission_channel: str = Field(description="e.g. BOSA e-Procurement, with signature requirements")


class AIDeadline(BaseModel):
    kind: DeadlineKind
    date: str = Field(description="ISO date YYYY-MM-DD")
    time: str = Field(description="HH:MM in 24h, or empty string if not stated")
    page: int
    description: str = Field(description="What must happen by this date, in English")


class AILot(BaseModel):
    number: int
    title: str
    page: int


class AIAwardCriterion(BaseModel):
    criterion: str
    weight: str = Field(description="e.g. '70 %' or '30 points'")
    scoring_method: str = Field(description="How it is scored, in English (formula, sub-criteria)")
    page: int
    win_theme: str = Field(description="Concrete suggestion to maximise the score on this criterion")


class AIRequirement(BaseModel):
    text: str = Field(description="The requirement, close to the original wording and in the original language")
    summary_en: str = Field(description="One-line English summary")
    category: Category
    level: Level = Field(description="Critical = non-compliance leads to exclusion, nullity or irregular offer; "
                                     "Mandatory = must be met; Desirable = asset / preference")
    is_document: bool = Field(description="True if a document, certificate, form or proof must be submitted")
    page: int
    section: str = Field(description="Section number and title where it appears")


class AIFitItem(BaseModel):
    requirement: str = Field(description="Short name of a selection/qualification requirement")
    status: Literal["Met", "Gap", "Unknown"]
    rationale: str = Field(description="Why, based on the company profile; 'No information in profile' if unknown")


class AIBidAssessment(BaseModel):
    executive_summary: str = Field(description="5-8 sentences in English for a key account manager")
    scope_summary: list[str] = Field(description="What must be delivered, as bullet points")
    recommendation: Literal["Go", "Go with conditions", "No-go", "Insufficient information"]
    recommendation_rationale: str
    fit_assessment: list[AIFitItem] = Field(description="Empty list if no company profile was provided")
    key_risks: list[str] = Field(description="Commercial, contractual, technical and procedural risks")
    clarification_questions: list[str] = Field(description="Questions worth asking the buyer before the "
                                                           "questions deadline, in the tender's language")
    next_actions: list[str] = Field(description="Ordered, dated where possible")


class AITenderAnalysis(BaseModel):
    language: Literal["FR", "NL", "EN", "DE", "Other"]
    key_info: AIKeyInfo
    deadlines: list[AIDeadline]
    lots: list[AILot]
    award_criteria: list[AIAwardCriterion]
    requirements: list[AIRequirement]
    bid_assessment: AIBidAssessment


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior bid manager specialised in Belgian and European public procurement \
(law of 17 June 2016, royal decrees of 18 April 2017 / 18 June 2017 for special sectors, general \
execution rules of 14 January 2013). You analyse tender documents (cahier spécial des charges, bestek, \
documents de marché, tender specifications) for an IT services company that is deciding whether to bid.

How to analyse:
- Read every page, including annexes, footnotes and tables. Footnotes often hold binding thresholds.
- Requirements: list every obligation on the tenderer or the contractor that affects bid preparation, \
qualification or delivery. Keep the original wording and language in `text`; add an English summary. \
Do not list background information, legal boilerplate without a concrete obligation, or blank form fields.
- Level: Critical only when the document states (or the law implies, e.g. a substantial irregularity) that \
non-compliance leads to exclusion, rejection, nullity or a non-compliant offer. Mandatory for other \
obligations, Desirable for assets and preferences.
- Deadlines: every date relevant to the bidder, including registration for site visits and the reference \
period for selection. Ignore dates of laws and regulations.
- Page numbers are the physical page in the PDF (first page = 1).
- Bid assessment: be concrete and commercially minded. Base the fit assessment strictly on the company \
profile provided; when the profile does not cover a requirement, use status Unknown — never assume.
- If something is not stated in the documents, write "Not stated" rather than guessing."""


def _profile_block(profile: str | None) -> str:
    if not profile:
        return "No company profile was provided: leave fit_assessment empty and base the recommendation " \
               "on the tender's attractiveness and difficulty only."
    return f"Company profile of the potential bidder:\n<company_profile>\n{profile}\n</company_profile>"


def _document_blocks(pdfs: list[Path]) -> list[dict]:
    blocks = []
    for i, pdf in enumerate(pdfs):
        data = pdf.read_bytes()
        if len(data) > MAX_PDF_BYTES:
            raise ValueError(f"{pdf.name} is {len(data) / 1e6:.0f} MB; the API accepts about 30 MB per request. "
                             "Split the file or analyse the annexes separately.")
        block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(data).decode("ascii")},
            "title": pdf.name,
        }
        if i == len(pdfs) - 1:
            # Cache the documents: follow-up runs and questions on the same tender reuse them.
            block["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
        blocks.append(block)
    return blocks


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------


@dataclass
class AIRunInfo:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    served_by: str = ""

    @property
    def estimated_cost_usd(self) -> float | None:
        # USD per million tokens: (input, cache read, output). 1-hour cache writes cost 2x input.
        prices = {"claude-opus-5-5": (4.0, 0.20, 20.0), "claude-sonnet-5-5": (2.0, 0.10, 10.0),
                  "claude-fable-5-2": (8.0, 0.20, 40.0)}
        p = prices.get(self.served_by or self.model)
        if not p:
            return None
        inp, read, out = p
        return (self.input_tokens * inp + self.cache_write_tokens * inp * 2.0
                + self.cache_read_tokens * read + self.output_tokens * out) / 1e6


@dataclass
class AIResult:
    analysis: TenderAnalysis
    insights: AIBidAssessment
    award_details: list[AIAwardCriterion] = field(default_factory=list)
    requirement_summaries: dict[str, str] = field(default_factory=dict)
    run: AIRunInfo | None = None


def _client(client=None):
    if client is not None:
        return client
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("AI mode needs the Anthropic SDK: pip install anthropic") from e
    return anthropic.Anthropic()


def _request_kwargs(model: str, effort: str, documents: list[dict], user_text: str) -> dict:
    kwargs = dict(
        model=model,
        max_tokens=64000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": [*documents, {"type": "text", "text": user_text}]}],
        output_config={"effort": effort},
    )
    if model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"):
        # If a safety classifier declines, the API retries on a fallback model in the same call.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    return kwargs


def _check_stop(message) -> None:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise RuntimeError(f"Claude declined the request ({getattr(details, 'category', None)}).")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("The analysis was cut off (output limit reached). "
                           "Try analysing the main document and the annexes separately.")


def _run_info(message, model: str) -> AIRunInfo:
    u = message.usage
    return AIRunInfo(
        model=model,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        served_by=getattr(message, "model", model),
    )


def ai_analyse(pdfs: list[str | Path], profile: str | None = None, model: str = DEFAULT_MODEL,
               effort: str = DEFAULT_EFFORT, client=None, on_progress=None) -> AIResult:
    """Analyse tender PDF(s) with Claude and return a structured result."""
    pdfs = [Path(p) for p in pdfs]
    documents = _document_blocks(pdfs)
    user_text = (
        f"{_profile_block(profile)}\n\n"
        f"Analyse the tender document(s) above ({', '.join(p.name for p in pdfs)}) and return the full "
        f"structured analysis. Today's date is {datetime.now():%Y-%m-%d}."
    )
    kwargs = _request_kwargs(model, effort, documents, user_text)

    api = _client(client)
    try:
        with api.beta.messages.stream(output_format=AITenderAnalysis, **kwargs) as stream:
            if on_progress:
                for event in stream:
                    if getattr(event, "type", "") == "content_block_delta":
                        on_progress()
            message = stream.get_final_message()
    except ValidationError as e:
        # The SDK validates the JSON when the text block closes, before the stop reason arrives.
        raise RuntimeError("The analysis was cut off or incomplete (often the output limit). "
                           "Try analysing the main document and the annexes separately.") from e

    _check_stop(message)
    parsed: AITenderAnalysis = message.parsed_output
    if parsed is None:
        raise RuntimeError("Claude's answer could not be parsed into the analysis schema.")
    result = to_tender_analysis(parsed, source=" + ".join(p.name for p in pdfs),
                                pages=_count_pages(pdfs))
    result.run = _run_info(message, model)
    return result


def ask(pdfs: list[str | Path], question: str, model: str = DEFAULT_MODEL, effort: str = "medium",
        client=None) -> tuple[str, list[tuple[str, int | None]], AIRunInfo]:
    """Answer a question about the tender, with citations (document title, page)."""
    pdfs = [Path(p) for p in pdfs]
    documents = _document_blocks(pdfs)
    for d in documents:
        d["citations"] = {"enabled": True}
    kwargs = _request_kwargs(model, effort, documents,
                             f"Question about the tender: {question}\n"
                             "Answer in the language of the question, precisely and briefly. "
                             "Quote the binding wording where useful.")
    api = _client(client)
    with api.beta.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()
    _check_stop(message)
    answer, cites = [], []
    for block in message.content:
        if block.type == "text":
            answer.append(block.text)
            for c in getattr(block, "citations", None) or []:
                cites.append((getattr(c, "document_title", "") or "", getattr(c, "start_page_number", None)))
    seen, unique = set(), []
    for c in cites:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return "".join(answer).strip(), unique, _run_info(message, model)


def _count_pages(pdfs: list[Path]) -> int:
    try:
        from pypdf import PdfReader
        return sum(len(PdfReader(str(p)).pages) for p in pdfs)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Mapping to the common data model
# ---------------------------------------------------------------------------


def _to_datetime(d: AIDeadline) -> tuple[datetime, bool] | None:
    try:
        day = datetime.strptime(d.date, "%Y-%m-%d")
    except ValueError:
        return None
    if d.time:
        try:
            t = datetime.strptime(d.time, "%H:%M")
            return day.replace(hour=t.hour, minute=t.minute), True
        except ValueError:
            pass
    return day, False


def to_tender_analysis(ai: AITenderAnalysis, source: str = "", pages: int = 0) -> AIResult:
    k = ai.key_info
    a = TenderAnalysis(source=source, pages=pages, language=ai.language)
    a.info = {
        "Title / object": k.title,
        "Contracting authority": k.contracting_authority,
        "Reference": k.reference,
        "Procedure": k.procedure,
        "Contract type": k.contract_type,
        "Estimated value": k.estimated_value,
        "Contract duration": k.contract_duration,
        "Offer validity": k.offer_validity,
        "Submission channel": k.submission_channel,
    }
    if k.cpv_codes:
        a.info["CPV codes"] = ", ".join(k.cpv_codes)
    a.lots = [Lot(l.number, l.title, l.page) for l in ai.lots]
    if not a.lots:
        a.lots_note = k.lots
    for d in ai.deadlines:
        parsed = _to_datetime(d)
        if parsed:
            a.deadlines.append(Deadline(d.kind, parsed[0], parsed[1], d.page, d.description))
    a.deadlines.sort(key=lambda d: d.when)
    a.award_criteria = [AwardCriterion(c.criterion, c.weight, c.page, c.scoring_method) for c in ai.award_criteria]
    summaries = {}
    for i, r in enumerate(ai.requirements, start=1):
        rid = f"REQ-{i:03d}"
        a.requirements.append(Requirement(rid, r.text, r.category, r.level, r.is_document, r.page, r.section))
        summaries[rid] = r.summary_en
    return AIResult(analysis=a, insights=ai.bid_assessment, award_details=list(ai.award_criteria),
                    requirement_summaries=summaries)


def load_profile(path: str | Path | None) -> str | None:
    if path:
        return Path(path).read_text(encoding="utf-8")
    env = os.environ.get("TENDER_COMPANY_PROFILE")
    return Path(env).read_text(encoding="utf-8") if env and Path(env).is_file() else None
