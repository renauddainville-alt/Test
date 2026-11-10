# Claude Project instructions for tender analysis

Paste one of these files into **Project instructions** of a Claude Project
(claude.ai → Projects → New project). The language of the file sets the language
of Claude's answers; quotes stay in the tender's original language.

| File | Answers in |
|---|---|
| `instructions_en.md` | English |
| `instructions_fr.md` | French |
| `instructions_nl.md` | Dutch |

Add a filled-in copy of `../examples/company_profile_template.md` to
**Project knowledge** so the fit assessment can use KEYES data.
Check KEYES's AI policy and the tender's confidentiality clause before uploading documents.

## Bid library

- `KEYES_Bid_Fact_Sheet_Template.docx` — the bid fact sheet to fill in once and add to every tender project.
- `create_bid_library_onedrive.ps1` — creates the "KEYES - Bid library" folder structure in your synced
  OneDrive for Business and copies the template into folder 01. Run on Windows from this folder:
  `powershell -ExecutionPolicy Bypass -File .\create_bid_library_onedrive.ps1`
  (add `-Root "C:\Users\<you>\OneDrive - NRB"` if the OneDrive folder isn't detected).
