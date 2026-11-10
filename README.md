# Tender analyser

Turns a public tender PDF (Cahier spécial des charges / Bestek / Tender
specifications) into an **Excel compliance matrix**, ready to start a bid/no-bid
review and a response plan.

Works with **French, Dutch and English** documents, such as those published on the
Belgian e-Procurement platform. Everything runs locally: the tender content is
never sent anywhere.

## What it extracts

| Sheet | Content |
|---|---|
| **Summary** | Title, contracting authority, reference, procedure, CPV codes, estimated value, duration, offer validity, submission deadline with days left, counts |
| **Deadlines** | Publication, information session / site visit, questions, submission, opening, contract start, with time and days left (legal references such as "loi du 17 juin 2016" are ignored) |
| **Lots** | Lot / perceel number and title, with a *Bid? (Y/N)* column |
| **Award criteria** | Criteria with weights (% / points / punten), plus a column for KEYES win themes |
| **Compliance matrix** | Every "must / doit / moet / shall…" sentence, categorised (exclusion, selection, security & compliance, SLA, staffing, pricing…) and levelled **Critical** (knock-out: "à peine de nullité", "op straffe van uitsluiting"…), **Mandatory** or **Desirable**, with Status drop-down, Owner, Response and Comments columns |
| **Documents to provide** | Certificates, references, CVs, declarations, forms requested, as a checklist |

## Usage

```bash
pip install -r requirements.txt
python -m tender_analyser path/to/tender.pdf
```

The report is written next to the PDF as `<name>_analysis.xlsx`. Options:

```bash
python -m tender_analyser tender.pdf -o reports/infrabel_tender.xlsx   # choose output
python -m tender_analyser lot1.pdf lot2.pdf annex.pdf                  # several files
```

## AI mode (optional, Claude API)

The rule-based mode is fast, free and offline, but it relies on keyword rules. AI mode
sends the PDF(s) to Claude, which reads the whole document (tables, scanned pages,
footnotes, annexes) and returns:

- the same sheets, built from Claude's reading of the document, with an English summary
  next to each requirement in the original language;
- a **Bid assessment** sheet: Go / Go with conditions / No-go recommendation, executive summary,
  scope, key risks, questions to ask the buyer before the questions deadline, next actions;
- a **fit check against your company profile** (Met / Gap / Unknown per selection requirement);
- for each award criterion, how it is scored and a suggested win theme.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # from console.anthropic.com
python -m tender_analyser tender.pdf --ai
python -m tender_analyser tender.pdf annex_I.pdf annex_IV.pdf --ai --profile company_profile.md
```

Several PDFs given with `--ai` are analysed together as **one** tender (main document + annexes).
Copy `examples/company_profile_template.md`, fill it in, and pass it with `--profile`.

Ask a quick question with page references:

```bash
python -m tender_analyser tender.pdf --ask "Quel est le chiffre d'affaires minimum exigé ?"
```

| Option | Default | |
|---|---|---|
| `--model` | `claude-opus-5-5` | e.g. `claude-sonnet-5-5` for a cheaper run |
| `--effort` | `high` (`--ai`), `medium` (`--ask`) | `low` … `max`: more effort = deeper reading, higher cost |
| `-y` / `--yes` | asks first | skip the confirmation before uploading |

**Confidentiality.** AI mode uploads the documents to the Anthropic API, and the tool asks
for confirmation before sending anything. Check the tender's confidentiality clause (some buyers,
for example, forbid sharing the documents with third parties) and your company's AI policy first.

**Cost.** A PDF page costs roughly 1,500–3,000 input tokens (text plus page image), so a 36-page tender is about 55–110k; the report shows the token usage and an
estimated cost. The documents are cached for one hour, so questions asked with `--ask` shortly after
an analysis read them from the cache at a fraction of the price.

**Reliability.** The AI output follows a strict schema, but it is still a reading by a model:
check every critical requirement, deadline and threshold against the document before you bid.
If the AI call fails (no key, network, quota), the tool falls back to the rule-based analysis.

## Try it

`examples/sample_tender_fr.pdf` is a **fictitious** tender (invented authority and
content). Its result is in `examples/sample_tender_fr_analysis.xlsx`.

```bash
python examples/make_sample_tender.py      # regenerate the sample PDF
python -m tender_analyser examples/sample_tender_fr.pdf
python -m unittest -v                      # run the tests (AI tests use a mock server, no key needed)
```

## Limits

- Extraction is rule-based. Always check the result against the source document;
  the matrix is a starting point, not a substitute for reading the tender.
- Scanned PDFs (images without a text layer) need OCR first.
- Requirements in complex tables may be split or missed.

Analyses of real tenders (`*_analysis.xlsx`) are git-ignored so client documents
don't end up in the repository by accident.
