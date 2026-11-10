"""AI mode tests: the real Anthropic SDK talks to a mock HTTP transport (no network, no API key)."""

import base64
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

try:
    import anthropic
    import httpx2
except ImportError:  # pragma: no cover
    anthropic = None

from openpyxl import load_workbook

from tender_analyser.report import write_report

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample_tender_fr.pdf"

CANNED = {
    "language": "FR",
    "key_info": {
        "title": "Services managés d'infrastructure IT", "contracting_authority": "Régie Fictive des Transports",
        "reference": "RFT-IT-2027-014", "procedure": "Procédure ouverte", "contract_type": "Services",
        "estimated_value": "4.800.000 € HTVA", "contract_duration": "48 mois", "offer_validity": "180 jours",
        "lots": "3 lots", "cpv_codes": ["72250000-2"], "submission_channel": "e-Procurement",
    },
    "deadlines": [
        {"kind": "Submission of offers", "date": "2027-01-29", "time": "11:00", "page": 1,
         "description": "Upload the signed offer"},
        {"kind": "Questions deadline", "date": "2027-01-15", "time": "", "page": 1, "description": "Questions"},
        {"kind": "Other date", "date": "not a date", "time": "", "page": 1, "description": "ignored"},
    ],
    "lots": [{"number": 1, "title": "Datacenter", "page": 1}],
    "award_criteria": [{"criterion": "Prix", "weight": "40 %", "scoring_method": "Lowest price gets 40",
                        "page": 2, "win_theme": "Sharp pricing"}],
    "requirements": [
        {"text": "L'offre doit être introduite via e-Procurement, à peine de nullité.",
         "summary_en": "Submit via e-Procurement only", "category": "Administrative", "level": "Critical",
         "is_document": False, "page": 1, "section": "1.4 Dépôt des offres"},
        {"text": "Copie du certificat ISO 27001.", "summary_en": "ISO 27001 certificate copy",
         "category": "Security & compliance", "level": "Mandatory", "is_document": True, "page": 2,
         "section": "2.3"},
    ],
    "bid_assessment": {
        "executive_summary": "Managed services tender.", "scope_summary": ["Datacenter", "Service desk"],
        "recommendation": "Go with conditions", "recommendation_rationale": "Turnover to confirm",
        "fit_assessment": [{"requirement": "ISO 27001", "status": "Met", "rationale": "In profile"},
                           {"requirement": "Turnover ≥ 10 M€", "status": "Unknown", "rationale": "No information"}],
        "key_risks": ["SLA penalties"], "clarification_questions": ["Quel est le volume de tickets ?"],
        "next_actions": ["Confirm turnover"],
    },
}


def _sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _stream_body(text: str, stop_reason="end_turn", citations=None):
    events = [
        {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 1200, "output_tokens": 1, "cache_creation_input_tokens": 30000,
                      "cache_read_input_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ]
    for i in range(0, len(text), 400):
        events.append({"type": "content_block_delta", "index": 0,
                       "delta": {"type": "text_delta", "text": text[i:i + 400]}})
    for c in citations or []:
        events.append({"type": "content_block_delta", "index": 0, "delta": {"type": "citations_delta", "citation": c}})
    events += [
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
         "usage": {"output_tokens": 2500}},
        {"type": "message_stop"},
    ]
    return _sse(events)


@unittest.skipIf(anthropic is None, "anthropic SDK not installed")
class AIModeTests(unittest.TestCase):
    def _client(self, body: bytes):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

        return anthropic.Anthropic(api_key="test-key", max_retries=0,
                                   http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))

    def test_request_and_mapping(self):
        from tender_analyser.ai import ai_analyse

        client = self._client(_stream_body(json.dumps(CANNED)))
        result = ai_analyse([SAMPLE], profile="We are ISO 27001 certified.", client=client)

        # --- request sent to the API
        req = self.requests[0]
        body = json.loads(req.content)
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["output_config"]["effort"], "high")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertIn("requirements", body["output_config"]["format"]["schema"]["properties"])
        self.assertEqual(body["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", req.headers.get("anthropic-beta", ""))
        doc, text = body["messages"][0]["content"]
        self.assertEqual(doc["type"], "document")
        self.assertEqual(base64.b64decode(doc["source"]["data"]), SAMPLE.read_bytes())
        self.assertEqual(doc["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        self.assertIn("ISO 27001 certified", text["text"])
        self.assertTrue(body.get("stream"))

        # --- mapping to the common model
        a = result.analysis
        self.assertEqual(a.info["Reference"], "RFT-IT-2027-014")
        self.assertEqual(a.submission_deadline.when, datetime(2027, 1, 29, 11, 0))
        self.assertEqual(len(a.deadlines), 2)  # invalid date dropped
        self.assertEqual([r.level for r in a.requirements], ["Critical", "Mandatory"])
        self.assertEqual(len(a.documents), 1)
        self.assertEqual(result.requirement_summaries["REQ-002"], "ISO 27001 certificate copy")
        self.assertEqual(result.insights.recommendation, "Go with conditions")
        self.assertEqual(result.run.cache_write_tokens, 30000)
        self.assertAlmostEqual(result.run.estimated_cost_usd,
                               (1200 * 4 + 30000 * 8 + 2500 * 20) / 1e6)

        # --- Excel report with AI sheets
        with tempfile.TemporaryDirectory() as d:
            out = write_report(a, Path(d) / "ai.xlsx", today=date(2026, 11, 10), ai=result)
            wb = load_workbook(out)
            self.assertEqual(wb.sheetnames[:2], ["Summary", "Bid assessment"])
            ws = wb["Bid assessment"]
            self.assertEqual(ws["B3"].value, "Go with conditions")
            cm = wb["Compliance matrix"]
            self.assertEqual(cm["C1"].value, "Summary (EN)")
            self.assertEqual(cm["I1"].value, "Status")
            self.assertEqual(cm["I2"].value, "To review")
            self.assertEqual(wb["Award criteria"]["E2"].value, "Sharp pricing")

    def test_truncated_output_is_reported(self):
        from tender_analyser.ai import ai_analyse

        client = self._client(_stream_body('{"language": "FR", "key_', stop_reason="max_tokens"))
        with self.assertRaisesRegex(RuntimeError, "cut off"):
            ai_analyse([SAMPLE], client=client)

    def test_ask_with_citations(self):
        from tender_analyser.ai import ask

        cite = {"type": "page_location", "cited_text": "40 %", "document_index": 0,
                "document_title": "sample_tender_fr.pdf", "start_page_number": 2, "end_page_number": 3}
        client = self._client(_stream_body("Le prix compte pour 40 %.", citations=[cite]))
        answer, cites, run = ask([SAMPLE], "Quel est le poids du prix ?", client=client)
        body = json.loads(self.requests[0].content)
        self.assertEqual(body["messages"][0]["content"][0]["citations"], {"enabled": True})
        self.assertNotIn("format", body.get("output_config", {}))  # citations and JSON format don't mix
        self.assertEqual(body["output_config"]["effort"], "medium")
        self.assertEqual(answer, "Le prix compte pour 40 %.")
        self.assertEqual(cites, [("sample_tender_fr.pdf", 2)])

    def test_cli_requires_confirmation(self):
        from tender_analyser.__main__ import main
        import builtins
        orig = builtins.input
        builtins.input = lambda _prompt="": "n"
        try:
            self.assertEqual(main([str(SAMPLE), "--ai"]), 1)
        finally:
            builtins.input = orig


if __name__ == "__main__":
    unittest.main()
