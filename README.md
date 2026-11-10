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

## Try it

`examples/sample_tender_fr.pdf` is a **fictitious** tender (invented authority and
content). Its result is in `examples/sample_tender_fr_analysis.xlsx`.

```bash
python examples/make_sample_tender.py      # regenerate the sample PDF
python -m tender_analyser examples/sample_tender_fr.pdf
python -m unittest -v                      # run the tests
```

## Limits

- Extraction is rule-based. Always check the result against the source document;
  the matrix is a starting point, not a substitute for reading the tender.
- Scanned PDFs (images without a text layer) need OCR first.
- Requirements in complex tables may be split or missed.

Analyses of real tenders (`*_analysis.xlsx`) are git-ignored so client documents
don't end up in the repository by accident.
