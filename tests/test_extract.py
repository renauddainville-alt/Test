import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from tender_analyser import analyse_pages, analyse_pdf, write_report

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample_tender_fr.pdf"

NL_PAGES = ["""BESTEK
Bestek nr. TST/2027/031
Voorwerp van de opdracht: Applicatiebeheer en ontwikkeling van reizigersinformatiesystemen
Aanbestedende overheid: Fictieve Vervoermaatschappij, Voorbeeldstraat 2, 2000 Antwerpen
Openbare procedure
Geraamde waarde: 2.500.000 EUR excl. btw
1. ALGEMENE BEPALINGEN
Deze opdracht valt onder de wet van 17 juni 2016 inzake overheidsopdrachten.
Uiterste datum voor het indienen van de offertes: 3 maart 2027 om 10.00 uur
Vragen kunnen gesteld worden tot 15/02/2027.
Perceel 1: Applicatiebeheer
Perceel 2: Nieuwe ontwikkelingen
De verbintenistermijn bedraagt 120 kalenderdagen.
2. SELECTIECRITERIA
De inschrijver moet minstens drie referenties voorleggen voor gelijkaardige opdrachten.
De inschrijver voegt bij zijn offerte een kopie van het ISO 27001-certificaat.
De offerte moet ingediend worden via e-Procurement, op straffe van nietigheid.
Kennis van Azure is wenselijk.
3. GUNNINGSCRITERIA
Prijs: 50 punten
Kwaliteit van de aanpak: 35 punten
Duurzaamheid: 15 punten
"""]


class SampleFrenchTender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SAMPLE.exists():
            import runpy
            runpy.run_path(str(ROOT / "examples" / "make_sample_tender.py"), run_name="__main__")
        cls.a = analyse_pdf(SAMPLE)

    def test_key_info(self):
        info = self.a.info
        self.assertEqual(self.a.language, "FR")
        self.assertEqual(info["Reference"], "RFT-IT-2027-014")
        self.assertIn("Services managés", info["Title / object"])
        self.assertIn("Régie Fictive des Transports", info["Contracting authority"])
        self.assertEqual(info["CPV codes"], "72250000-2, 72611000-6")
        self.assertEqual(info["Offer validity"], "180 jours calendrier")
        self.assertTrue(info["Contract duration"].startswith("48 mois"))

    def test_deadlines(self):
        self.assertEqual(self.a.submission_deadline.when, datetime(2027, 1, 29, 11, 0))
        kinds = {d.kind: d.when for d in self.a.deadlines}
        self.assertEqual(kinds["Questions deadline"], datetime(2027, 1, 15, 12, 0))
        self.assertEqual(kinds["Opening of offers"], datetime(2027, 1, 29, 11, 30))
        # Legal references are not deadlines
        self.assertNotIn(date(2016, 6, 17), [d.when.date() for d in self.a.deadlines])

    def test_lots_and_award(self):
        self.assertEqual([l.number for l in self.a.lots], [1, 2, 3])
        self.assertEqual([c.weight for c in self.a.award_criteria], ["40 %", "30 %", "20 %", "10 %"])
        self.assertEqual(self.a.award_criteria[0].criterion, "Prix")

    def test_requirements(self):
        levels = [r.level for r in self.a.requirements]
        self.assertEqual(levels.count("Critical"), 3)
        texts = " ".join(r.text for r in self.a.documents)
        self.assertIn("ISO 27001", texts)
        self.assertIn("CV", texts)
        refs = next(r for r in self.a.requirements if "références" in r.text)
        self.assertEqual((refs.level, refs.category), ("Critical", "Selection – technical"))

    def test_excel_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = write_report(self.a, Path(d) / "out.xlsx", today=date(2026, 11, 10))
            wb = load_workbook(out)
            self.assertEqual(wb.sheetnames, ["Summary", "Deadlines", "Lots", "Award criteria",
                                             "Compliance matrix", "Documents to provide"])
            ws = wb["Compliance matrix"]
            self.assertEqual(ws.max_row, len(self.a.requirements) + 1)
            self.assertEqual(ws["H2"].value, "To review")


class DutchTender(unittest.TestCase):
    def setUp(self):
        self.a = analyse_pages(NL_PAGES, "nl.pdf")

    def test_dutch(self):
        a = self.a
        self.assertEqual(a.language, "NL")
        self.assertEqual(a.info["Reference"], "TST/2027/031")
        self.assertIn("Fictieve Vervoermaatschappij", a.info["Contracting authority"])
        self.assertEqual(a.info["Offer validity"], "120 kalenderdagen")
        self.assertEqual(a.submission_deadline.when, datetime(2027, 3, 3, 10, 0))
        self.assertEqual([l.title for l in a.lots], ["Applicatiebeheer", "Nieuwe ontwikkelingen"])
        self.assertEqual([c.weight for c in a.award_criteria], ["50 punten", "35 punten", "15 punten"])
        levels = {r.text[:20]: r.level for r in a.requirements}
        self.assertIn("Critical", levels.values())
        self.assertIn("Desirable", levels.values())
        self.assertTrue(any("ISO 27001" in r.text for r in a.documents))


if __name__ == "__main__":
    unittest.main()
