import json
import subprocess
import sys
import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "notebooks" / "generate_report.py"
REPORT_PATH = ROOT / "data" / "report_zone_live_test.pdf"


class ReportGenerationTests(unittest.TestCase):
    def test_generate_report_accepts_live_zone_payload(self):
        if REPORT_PATH.exists():
            REPORT_PATH.unlink()

        zone_payload = {
            "id": "live_test",
            "lat": 19.4,
            "lon": 72.8,
            "area_sqm": 12000,
            "severity": "HIGH",
            "risk_score": 72,
            "action": "Schedule inspection",
            "violation_type": "AGRICULTURAL_LAND",
            "legal_violations": "AGRICULTURAL_LAND,WATER_BODY_ENCROACHMENT"
        }

        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "live_test", json.dumps(zone_payload)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(REPORT_PATH.exists(), completed.stdout + completed.stderr)

        reader = PdfReader(str(REPORT_PATH))
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages).lower()
        self.assertIn("agricultural", pdf_text)
        self.assertIn("water body", pdf_text)


if __name__ == "__main__":
    unittest.main()
