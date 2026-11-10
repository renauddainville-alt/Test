"""Rule-based extraction of key information from public tender documents.

Supports French, Dutch and English documents as commonly found on the Belgian
e-Procurement platform (Cahier spécial des charges / Bestek / Tender
specifications). Everything runs locally: no document content leaves the
machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Deadline:
    kind: str
    when: datetime
    has_time: bool
    page: int
    context: str


@dataclass
class Lot:
    number: int
    title: str
    page: int


@dataclass
class AwardCriterion:
    criterion: str
    weight: str
    page: int
    section: str


@dataclass
class Requirement:
    id: str
    text: str
    category: str
    level: str  # Mandatory / Critical / Desirable
    is_document: bool
    page: int
    section: str


@dataclass
class TenderAnalysis:
    source: str
    pages: int
    language: str
    info: dict[str, str] = field(default_factory=dict)
    deadlines: list[Deadline] = field(default_factory=list)
    lots: list[Lot] = field(default_factory=list)
    lots_note: str = ""
    award_criteria: list[AwardCriterion] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)

    @property
    def documents(self) -> list[Requirement]:
        return [r for r in self.requirements if r.is_document]

    @property
    def submission_deadline(self) -> Deadline | None:
        subs = [d for d in self.deadlines if d.kind == "Submission of offers"]
        return min(subs, key=lambda d: d.when) if subs else None


# ---------------------------------------------------------------------------
# PDF text
# ---------------------------------------------------------------------------


def read_pdf_pages(path: str | Path) -> list[str]:
    """Return the text of each page. Uses pdfplumber, falls back to pypdf."""
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            return [(p.extract_text() or "") for p in pdf.pages]
    except Exception:
        from pypdf import PdfReader

        return [(p.extract_text() or "") for p in PdfReader(str(path)).pages]


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_LANG_MARKERS = {
    "FR": r"\b(le|la|les|des|du|et|est|pour|offre|soumissionnaire|marché)\b",
    "NL": r"\b(de|het|een|en|van|voor|is|inschrijver|opdracht|offerte)\b",
    "EN": r"\b(the|and|of|for|is|tenderer|contract|shall|offer)\b",
}


def detect_language(text: str) -> str:
    low = text.lower()
    scores = {k: len(re.findall(p, low)) for k, p in _LANG_MARKERS.items()}
    return max(scores, key=scores.get) if any(scores.values()) else "?"


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {
    # FR
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    # NL
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "oktober": 10,
    # EN
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_NUM = re.compile(r"(?<![\w.])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})(?![\w]|\.\d)")
_DATE_TXT = re.compile(
    rf"\b(\d{{1,2}})(?:er|e|st|nd|rd|th)?\s+({_MONTH_RE})\s+(\d{{4}})\b", re.I
)
_TIME = re.compile(
    r"^\s*(?:,|–|-|à|a|om|at|vers|tot|before|avant)?\s*(?:(?:à|om|at)\s*)?"
    r"(\d{1,2})\s*(?:h|:|u|\.)\s*(\d{2})?\s*(?:uur|hrs|h)?",
    re.I,
)
# Dates preceded by these words are legal references, not deadlines.
_LEGAL_REF = re.compile(
    r"\b(loi|wet|arrêté|arrete|besluit|directive|richtlijn|act|decree|"
    r"règlement|reglement|verordening|regulation|a\.?r\.?|k\.?b\.?)\b[^.;]{0,90}$",
    re.I,
)

_DEADLINE_KINDS = [
    ("Submission of offers", r"dépôt des offres|dépôt de l'offre|remise des offres|introduction des offres|"
     r"réception des offres|date limite de (?:dépôt|remise|réception)|"
     r"indienen van de offerte|indiening van de offerte|ontvangst van de offerte|"
     r"uiterste (?:datum|termijn) (?:voor|van) (?:het )?(?:indienen|indiening|ontvangst)|"
     r"submission of (?:offers|tenders|bids)|tender deadline|offers must be received"),
    ("Opening of offers", r"ouverture des offres|opening van de offertes|opening of (?:offers|tenders)"),
    ("Questions deadline", r"questions|vragen|clarification"),
    ("Site visit / information session", r"visite|plaatsbezoek|séance d'information|"
     r"informatiesessie|site visit|information session|bezoek ter plaatse"),
    ("Request to participate", r"demande de participation|aanvraag tot deelneming|"
     r"aanvragen tot deelneming|request to participate|candidature"),
    ("Contract start", r"début (?:du marché|des prestations|de l'exécution)|"
     r"aanvang (?:van de opdracht|der werken|van de diensten)|"
     r"start (?:date|of the contract|of services)|commencement"),
    ("Award / notification", r"attribution|notification|gunning|kennisgeving|award"),
    ("Publication", r"publication|publicatie|bekendmaking|published"),
    ("Reference period (selection)", r"références?|referenties?|marchés similaires|gelijkaardige opdrachten|"
     r"similar contracts|période comprise entre"),
]


def _parse_dates(line: str) -> list[tuple[datetime, bool, int]]:
    """Return (datetime, has_time, start_pos) for each date in the line."""
    found = []
    for m in _DATE_NUM.finditer(line):
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        found.append((m, d, mth, y))
    for m in _DATE_TXT.finditer(line):
        found.append((m, int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))))

    results = []
    for m, d, mth, y in found:
        if not (2000 <= y <= 2100):
            continue
        if _LEGAL_REF.search(line[: m.start()]):
            continue
        hour = minute = 0
        has_time = False
        t = _TIME.match(line[m.end(): m.end() + 25])
        if t:
            h = int(t.group(1))
            mi = int(t.group(2) or 0)
            if 0 <= h <= 23 and 0 <= mi <= 59:
                hour, minute, has_time = h, mi, True
        try:
            results.append((datetime(y, mth, d, hour, minute), has_time, m.start()))
        except ValueError:
            continue
    return results


def _classify_deadline(context: str) -> str:
    low = context.lower()
    for kind, pattern in _DEADLINE_KINDS:
        if re.search(pattern, low):
            return kind
    return "Other date"


# ---------------------------------------------------------------------------
# Sections, lots, sentences
# ---------------------------------------------------------------------------

_HEADING_NUM = re.compile(r"^\s*((?:\d+\.){0,3}\d+)\.?\s+([A-ZÀ-ÖØ-Ý][^\n]{2,90})$")
_HEADING_WORD = re.compile(
    r"^\s*(article|artikel|chapitre|hoofdstuk|chapter|section|afdeling|partie|"
    r"deel|part|titre|titel|title)\s+[\dIVXLC]+\b.{0,90}$",
    re.I,
)
_BULLET = re.compile(r"^\s*(?:[-•*▪●◦–]|\(?[a-z0-9]{1,2}[).])\s+", re.I)
_LOT = re.compile(
    r"^\s*(?:lot|perceel)\s*(?:n[°o]\.?\s*)?(\d{1,2})\s*[:\-–.)]\s*(.{3,150})$", re.I
)


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 100:
        return False
    if _HEADING_WORD.match(s):
        return True
    m = _HEADING_NUM.match(s)
    if m and not s.endswith((".", ";", ",")):
        # Avoid treating amounts or dates as headings
        return not re.match(r"^\d+[.,]\d{3}", s)
    return s.isupper() and 4 <= len(s) <= 80 and len(s.split()) <= 10


# ---------------------------------------------------------------------------
# Requirement detection
# ---------------------------------------------------------------------------

_CRITICAL = re.compile(
    r"à peine (?:de nullité|d'exclusion|d’exclusion|de rejet)|sous peine (?:de nullité|d'exclusion|d’exclusion)|"
    r"exigence substantielle|irrégularité substantielle|"
    r"op straffe van (?:nietigheid|uitsluiting|wering)|substantiële (?:eis|vereiste|onregelmatigheid)|"
    r"on pain of (?:exclusion|nullity)|will be (?:excluded|rejected)|knock[- ]out|"
    r"sera (?:écartée|exclue|rejetée)|wordt (?:geweerd|uitgesloten)|"
    r"nul(?:le)? et non avenue?|entraîner l'exclusion|peu(?:t|vent) être exclu(?:e|s|es)?|"
    r"(?:techniquement )?non conformes?|ne (?:seront|sera|sont|est) pas (?:acceptée?s?|autorisée?s?|admise?s?)|"
    r"condition essentielle|de plein droit la nullité|"
    r"als nietig beschouwd|kan (?:worden )?uitgesloten|niet (?:aanvaard|toegelaten|toegestaan)|"
    r"may be excluded|will not be accepted|not (?:be )?(?:accepted|allowed|permitted)|null and void",
    re.I,
)
_MANDATORY = re.compile(
    r"\b(doit|doivent|devra|devront|est tenu|sont tenus|obligatoire(?:ment)?|"
    r"impérativement|exigée?s?|requise?s?|au minimum|minimum|minimale?s?|au plus tard|s'engagent?|"
    r""
    r"moet|moeten|dient|dienen|verplicht|vereist|minimaal|minstens|ten minste|uiterlijk|verbindt zich|"
    r"must|shall|required|mandatory|at least|minimum|at the latest|undertakes?)\b",
    re.I,
)
_DESIRABLE = re.compile(
    r"\b(devrait|devraient|souhaitée?s?|de préférence|est un atout|"
    r"bij voorkeur|wenselijk|is een troef|zou moeten|"
    r"should|preferably|desirable|is an asset|nice to have)\b",
    re.I,
)
_DOC_VERB = re.compile(
    r"\b(joindre|joint|fournir|fournit|produire|annexer|remettre|transmettre|"
    r"renvoyer|soumettre|présenter|démontrer|apporter la preuve|"
    r"toevoegen|bijvoegen|voegt|voorleggen|bezorgen|overmaken|"
    r"provide|submit|attach|enclose|include)\b",
    re.I,
)
_DOC_NOUN = re.compile(
    r"\b(attestation|certificat|déclaration|cv|curriculum|référence|liste|bilan|"
    r"comptes annuels|rapports annuels|preuve|copie|formulaire|inventaire|métré|extrait|casier|"
    r"accord de confidentialité|procuration|modèle de soumission|"
    r"attest|verklaring|certificaat|referentie|lijst|jaarrekening|bewijs|kopie|"
    r"formulier|inventaris|meetstaat|uittreksel|geheimhoudingsovereenkomst|volmacht|"
    r"certificate|declaration|statement|reference|list|accounts|proof|copy|form|"
    r"non-disclosure|nda|power of attorney|iso|dume|uea|espd)",
    re.I,
)

_TENDERER = re.compile(r"\b(soumissionnaire|candidat|inschrijver|kandidaat|tenderer|bidder|candidate)\b", re.I)

_CATEGORIES = [
    ("Exclusion", r"motifs? d'exclusion|situations? d'exclusion|critères? d'exclusion|uitsluitingsgrond|"
     r"exclusion grounds|grounds for exclusion|casier judiciaire|strafregister|"
     r"dettes sociales|sociale schulden|cotisations|onss|rsz|faillite|faillissement"),
    ("Administrative", r"rédigée?s? en|opgesteld in|drafted in|written in|e-procurement|"
     r"signature électronique|elektronische handtekening|electronic signature"),
    ("Selection – financial", r"chiffre d'affaires|omzet|turnover|capacité économique|"
     r"financière|financiële|economische draagkracht|solvabilité|bilan|jaarrekening|assurance|verzekering|insurance"),
    ("Selection – technical", r"références?|referenties?|capacité technique|technische bekwaamheid|"
     r"technical capacity|experience|expérience|ervaring|similar contracts|marchés similaires"),
    ("Security & compliance", r"iso ?27001|iso ?9001|iso ?20000|nis ?2|rgpd|gdpr|avg|"
     r"habilitation de sécurité|veiligheidsmachtiging|security clearance|cyber|sécurité de l'information|"
     r"informatieveiligheid|information security|confidentialité|vertrouwelijk|"
     r"données|gegevens|\bdata\b|hébergé|gehost|hosted|union européenne|europese unie|european union"),
    ("Staffing / profiles", r"\bcv\b|curriculum|profil|profiel|consultant|chef de projet|projectleider|project manager|"
     r"certifi(?:é|ed|ering)|diplôme|diploma|années d'expérience|jaar ervaring|years of experience|"
     r"néerlandais|français|nederlands|frans|anglais|engels|bilingue|tweetalig"),
    ("Award", r"critères? d'attribution|gunningscriteri|award criteri|pondération|weging|weighting"),
    ("Service levels / SLA", r"\bsla\b|disponibilité|beschikbaarheid|availability|temps de réponse|"
     r"responstijd|response time|temps de résolution|oplostijd|resolution time|pénalité|boete|penalt"),
    ("Pricing", r"\bprix\b|\bprijs|\bprice|tarif|inventaire|inventaris|métré|meetstaat|révision des prix|prijsherziening|"
     r"facturation|facturatie|invoic"),
    ("Technical", r"technique|technisch|technical|infrastructure|logiciel|software|cloud|"
     r"réseau|netwerk|network|migration|migratie|intégration|integratie|integration|api"),
    ("Administrative", r"offre|offerte|offer|tender|signature|handtekening|sign|e-procurement|"
     r"délai|termijn|validité|geldigheid|validity|langue|taal|language"),
]

_CATEGORY_BY_SECTION = [
    ("Exclusion", r"exclusion|uitsluiting"),
    ("Selection – technical", r"sélection|selectie|selection|qualit|kwalitatieve"),
    ("Award", r"attribution|gunning|award"),
    ("Technical", r"technique|technisch|technical|prescriptions|spécifications|specificaties"),
]


def _categorise(sentence: str, section: str) -> str:
    low = _CRITICAL.sub("", sentence.lower())
    for cat, pat in _CATEGORIES:
        if re.search(pat, low):
            # A generic word in the sentence shouldn't override a clear section.
            if cat in ("Administrative", "Technical"):
                for scat, spat in _CATEGORY_BY_SECTION:
                    if re.search(spat, section.lower()):
                        return scat
            return cat
    for scat, spat in _CATEGORY_BY_SECTION:
        if re.search(spat, section.lower()):
            return scat
    return "General"


_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-ZÀ-ÖØ-Ý•\-(])")


def _paragraphs(lines: list[tuple[str, str]]):
    """Group (section, line) pairs into (section, paragraph) pairs."""
    buf: list[str] = []
    sec = ""
    for section, line in lines:
        s = line.strip()
        new_block = not s or _BULLET.match(line) or section != sec
        if new_block and buf:
            yield sec, " ".join(buf)
            buf = []
        sec = section
        if s:
            buf.append(_BULLET.sub("", s) if _BULLET.match(line) else s)
    if buf:
        yield sec, " ".join(buf)


# ---------------------------------------------------------------------------
# Key info
# ---------------------------------------------------------------------------

_INFO_PATTERNS = {
    "Contracting authority": r"(?:pouvoir adjudicateur|entité adjudicatrice|adjudicateur|"
                             r"aanbestedende (?:overheid|entiteit|dienst)|opdrachtgever|contracting (?:authority|entity))"
                             r"\s*(?:[:\-–]|est|is)\s+([^.\n]{3,120})",
    "Reference": r"(?:cahier (?:spécial )?des charges|csc|bestek|documents? (?:de|du) marché|opdrachtdocumenten|"
                 r"tender documents|référence|referentie|reference|dossier)\s*(?:n[°o]\.?|nr\.?|number|no\.?)"
                 r"\s*[:\-–]?\s*([A-Z0-9][\w./&\-]{2,40}(?:[ ][A-Z0-9][\w./&\-]*){0,2})",
    "Procedure": r"(procédure (?:ouverte|restreinte|négociée[^.\n]{0,60}|concurrentielle avec négociation)|"
                 r"openbare procedure|niet-openbare procedure|"
                 r"(?:mededingings)?procedure met onderhandeling[^.\n]{0,40}|onderhandelingsprocedure[^.\n]{0,40}|"
                 r"open procedure|restricted procedure|negotiated procedure[^.\n]{0,40}|competitive dialogue|"
                 r"dialogue compétitif|concurrentiedialoog)",
    "Estimated value": r"(?:montant estimé|valeur estimée|estimation|geraamde (?:waarde|kost)|raming|"
                       r"estimated (?:value|amount))[^€\d\n]{0,40}((?:€\s*)?\d[\d .,]*\d\s*(?:€|EUR|euros?)?(?:\s*(?:HTVA|hors TVA|excl\.? (?:btw|VAT)|exclusief btw))?)",
    "Contract duration": r"(?:période initiale de|initial period of|initiële periode van|durée du marché|durée|looptijd|duur van de opdracht|duration of the contract|contract duration)"
                         r"[ \t]*(?:du marché|van de opdracht|initiale)?[ \t]*(?:[:\-–]|est de|bedraagt|is|(?<=de)|(?<=of)|(?<=van))[ \t]*([^.\n]{3,100})",
    "Offer validity": r"(?:délai d'engagement|délai de validité|verbintenistermijn|geldigheidsduur van de offerte|"
                      r"offer validity|validity of the offer)[^\d\n]{0,40}(\d{2,3}\s*(?:jours|kalenderdagen|werkdagen|dagen|days)(?:\s*(?:calendrier|ouvrables|calendar|working))?)",
}


def _extract_title(pages: list[str]) -> str:
    lines = [l.strip() for l in "\n".join(pages[:3]).splitlines() if l.strip()]
    obj = re.compile(r"^(?:objet(?: du marché)?|voorwerp(?: van de opdracht)?|subject(?: of the contract)?|"
                     r"object of the contract|intitulé|titel van de opdracht|contract title)\s*[:\-–]\s*(.*)$", re.I)
    for i, l in enumerate(lines[:120]):
        m = obj.match(l)
        if not m:
            continue
        title = m.group(1).strip()
        nxt = i + 1
        # "Objet : Documents de marché n° X" → the real title is on the next line
        if len(title) < 6 or re.search(r"documents? (?:de|du) marché|cahier|bestek|n[°o]\s*\S+$", title, re.I):
            if nxt >= len(lines):
                continue
            title, nxt = lines[nxt], nxt + 1
        # Join a wrapped second line (shorter, no final punctuation on the first line)
        if (nxt < len(lines) and len(title) > 55 and not title.endswith((".", ":", ";"))
                and len(lines[nxt]) < len(title) and not obj.match(lines[nxt])):
            title += " " + lines[nxt]
        return title
    first = [l for l in (pages[0] if pages else "").splitlines() if l.strip()]
    candidates = [l.strip() for l in first[:12]
                  if 15 <= len(l) <= 160 and not re.search(r"cahier|bestek|page|blz|\d{2}/\d{2}/\d{4}", l, re.I)]
    return max(candidates, key=len) if candidates else ""


def _extract_info(pages: list[str], full: str) -> dict[str, str]:
    info: dict[str, str] = {"Title / object": _extract_title(pages)}
    flat = re.sub(r"\s+", " ", full)
    for key, pat in _INFO_PATTERNS.items():
        texts = (flat, full) if key == "Contract duration" else (full, flat)
        m = re.search(pat, texts[0], re.I) or re.search(pat, texts[1], re.I)
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip(" .:;,")
            info[key] = val.capitalize() if (key == "Procedure" and val.isupper()) else val
    cpv = sorted(set(re.findall(r"\b\d{8}-\d\b", full)))
    if cpv:
        info["CPV codes"] = ", ".join(cpv)
    return info


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    return (text.replace("’", "'").replace("‘", "'").replace("“", '"')
            .replace("”", '"').replace(" ", " ").replace(" ", " "))


_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*|blz\.?\s*|p\.\s*)?\d{1,3}(?:\s*(?:/|of|sur|van)\s*\d{1,3})?\s*$", re.I)
_FOOTNOTE = re.compile(r"^(\d{1,3}) (?=\S)")
_DOC_LIST_HEADER = re.compile(
    r"(?:documents?|pièces|attestations?|stukken|documenten).{0,40}(?:à joindre|à fournir|à remettre|à produire|"
    r"bij te voegen|toe te voegen|voor te leggen|to (?:be )?(?:submit|attach|enclos|provid))", re.I)
_NOT_IN_LOTS = re.compile(r"(?:n'est|ne sera) pas divisé en lots|niet (?:in percelen )?(?:op)?gedeeld in percelen|"
                          r"niet in percelen verdeeld|not divided into lots|pas de lots|geen percelen", re.I)


def _classify_lines(pages: list[str]) -> list[tuple[int, str, str]]:
    """Return (page, kind, line) with kind in body/heading/footnote; page numbers dropped."""
    out: list[tuple[int, str, str]] = []
    next_fn = 1
    for pno, text in enumerate(pages, start=1):
        lines = text.splitlines()
        while lines and (not lines[-1].strip() or _PAGE_NUMBER.match(lines[-1])):
            lines.pop()
        in_fn = False
        for i, line in enumerate(lines):
            m = _FOOTNOTE.match(line.strip())
            # Footnotes are numbered sequentially through the document and sit at the bottom of the page.
            if m and i >= len(lines) * 0.3 and next_fn <= int(m.group(1)) <= next_fn + 3:
                in_fn = True
                next_fn = int(m.group(1)) + 1
            if in_fn:
                out.append((pno, "footnote", line))
            elif _is_heading(line):
                out.append((pno, "heading", line))
            else:
                out.append((pno, "body", line))
    return out


def _nearest_kind(before: str, after: str) -> str:
    """Pick the deadline type whose keyword is closest to the date."""
    best, best_pos = "Other date", -1
    for kind, pattern in _DEADLINE_KINDS:
        for m in re.finditer(pattern, before, re.I):
            if m.end() > best_pos:
                best, best_pos = kind, m.end()
    if best_pos >= 0:
        return best
    best_pos = 10**6
    for kind, pattern in _DEADLINE_KINDS:
        m = re.search(pattern, after, re.I)
        if m and m.start() < best_pos:
            best, best_pos = kind, m.start()
    return best


def _find_deadlines(classified: list[tuple[int, str, str]]) -> list[Deadline]:
    by_page: dict[int, list[str]] = {}
    for pno, _kind, line in classified:
        by_page.setdefault(pno, []).append(line.strip())
    found: dict[tuple[str, date], Deadline] = {}
    for pno, lines in by_page.items():
        flat = re.sub(r"\s+", " ", " ".join(lines))  # dates split across lines become findable
        for when, has_time, pos in _parse_dates(flat):
            sent_start = flat.rfind(". ", 0, pos)
            before = flat[max(sent_start + 1, pos - 160):pos]
            after = flat[pos:pos + 160]
            after = after[: after.find(". ") + 1] if ". " in after else after
            kind = _nearest_kind(before, after)
            ctx_start = max(sent_start + 1, pos - 140)
            ctx = flat[ctx_start: pos + 80].strip()
            key = (kind, when.date())
            old = found.get(key)
            if old is None or (has_time and not old.has_time):
                found[key] = Deadline(kind, when, has_time, old.page if old else pno, ctx[:250])
    return sorted(found.values(), key=lambda d: d.when)


def analyse_pages(pages: list[str], source: str = "") -> TenderAnalysis:
    pages = [_normalise(p) for p in pages]
    full = "\n".join(pages)
    result = TenderAnalysis(source=source, pages=len(pages), language=detect_language(full))
    result.info = _extract_info(pages, full)
    if _NOT_IN_LOTS.search(full):
        result.lots_note = "Not divided into lots"

    classified = _classify_lines(pages)
    result.deadlines = _find_deadlines(classified)

    # Sections + lots
    section = ""
    sectioned: list[tuple[int, str, str, str]] = []  # (page, kind, section, line)
    lots: dict[int, Lot] = {}
    for pno, kind, line in classified:
        if kind == "heading":
            section = line.strip()
        sectioned.append((pno, kind, section, line))
        lm = _LOT.match(line)
        if lm and kind != "footnote":
            n = int(lm.group(1))
            title = lm.group(2).strip(" .")
            if n not in lots or len(title) > len(lots[n].title):
                lots[n] = Lot(n, title, lots[n].page if n in lots else pno)
    result.lots = [lots[k] for k in sorted(lots)]

    # Award criteria with weights
    weight_re = re.compile(r"^(.{3,120}?)\s*[:\-–(]?\s*(\d{1,3}(?:[.,]\d+)?)\s*(%|points?|punten|pts)\)?\s*\.?$", re.I)
    award_ctx = re.compile(r"attribution|gunning|award|critère|criteri|pondération|weging|weighting", re.I)
    seen_crit = set()
    for pno, kind, sec, line in sectioned:
        if kind == "footnote":
            continue
        m = weight_re.match(_BULLET.sub("", line.strip()))
        if m and (award_ctx.search(sec) or award_ctx.search(line)):
            crit = m.group(1).strip(" :-–.")
            crit = re.sub(r"^(?:critère|criterium|criterion)\s*\d*\s*[:\-–.]?\s*", "", crit, flags=re.I) or crit
            if (crit.lower() in seen_crit or re.match(r"^(?:total|totaal)\b", crit, re.I) or len(crit.split()) > 12
                    or re.search(r"attribuer|attribué|obtient|obtiendra|toegekend|krijgt|awarded|receives?", crit, re.I)):
                continue
            seen_crit.add(crit.lower())
            result.award_criteria.append(AwardCriterion(crit, f"{m.group(2)} {m.group(3)}", pno, sec))

    # Paragraphs across pages; footnotes kept apart so they don't cut sentences
    paras: list[tuple[int, str, str, bool]] = []  # (page, section, text, is_bullet)
    buf: list[str] = []
    meta: tuple[int, str, bool] | None = None
    prev_kind = ""

    def flush():
        nonlocal buf, meta
        if buf and meta:
            paras.append((meta[0], meta[1], " ".join(buf), meta[2]))
        buf, meta = [], None

    for pno, kind, sec, line in sectioned:
        st = line.strip()
        if kind == "heading":
            flush(); prev_kind = kind
            continue
        if kind == "footnote":
            if _FOOTNOTE.match(st) or prev_kind != "footnote":
                if prev_kind != "footnote":
                    body_buf, body_meta = buf, meta   # park the body paragraph (may continue on next page)
                    buf, meta = [], None
                else:
                    flush()
            if meta is None:
                meta = (pno, f"{sec} (footnote)", False)
            buf.append(_FOOTNOTE.sub("", st, count=1) if _FOOTNOTE.match(st) else st)
            prev_kind = kind
            continue
        if prev_kind == "footnote":
            flush()
            buf, meta = body_buf, body_meta
            if buf and st and (st[0].isupper() or _BULLET.match(line)) and buf[-1].endswith((".", ":", ";")):
                flush()
        prev_kind = kind
        bullet = bool(_BULLET.match(line))
        subheading = (len(buf) == 1 and len(buf[0]) < 70 and not buf[0].endswith((".", ";", ":", ","))
                      and st[:1].isupper())
        if not st or bullet or subheading or (meta and meta[1] != sec):
            flush()
        if st:
            if meta is None:
                meta = (pno, sec, bullet)
            buf.append(_BULLET.sub("", st) if bullet else st)
    flush()
    if prev_kind == "footnote":  # document ended on footnotes: release the parked body paragraph
        buf, meta = body_buf, body_meta
        flush()

    # Requirements
    n = 0
    seen_req = set()
    doc_list = False
    for pno, sec, para, is_bullet in paras:
        if para.rstrip().endswith(":") and _DOC_LIST_HEADER.search(para):
            doc_list = True
            continue
        if doc_list and not is_bullet:
            doc_list = False
        for sent in ([para] if doc_list else _SENT_SPLIT.split(para)):
            s = sent.strip()
            if len(s) < (12 if doc_list else 25) or "____" in s or "[----" in s:
                continue
            critical = bool(_CRITICAL.search(s))
            mandatory = bool(_MANDATORY.search(s))
            desirable = bool(_DESIRABLE.search(s))
            is_doc = doc_list or bool(_DOC_VERB.search(s) and _DOC_NOUN.search(s))
            # "Le soumissionnaire joint à son offre…" / "De inschrijver voegt … bij" is an obligation
            implicit = doc_list or (is_doc and bool(_TENDERER.search(s)))
            if not (critical or mandatory or desirable or implicit):
                continue
            norm = re.sub(r"\W+", " ", s.lower())
            if norm in seen_req:
                continue
            seen_req.add(norm)
            level = "Critical" if critical else ("Mandatory" if (mandatory or implicit) else "Desirable")
            n += 1
            result.requirements.append(Requirement(
                id=f"REQ-{n:03d}", text=s, category=_categorise(s, sec), level=level,
                is_document=is_doc, page=pno, section=sec,
            ))
    return result


def analyse_pdf(path: str | Path) -> TenderAnalysis:
    return analyse_pages(read_pdf_pages(path), source=Path(path).name)


def days_until(when: datetime, today: date | None = None) -> int:
    return (when.date() - (today or date.today())).days
