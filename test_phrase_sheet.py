"""Julius's 250-phrase test sheet (testing/test_phrases.csv) as a regression test.

Text mode only: each phrase goes straight to the detector. Every row must
PASS, except rows the sheet marks ambiguous (REVIEW) and delivery-condition
rows that need a real speaker (MANUAL).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).with_name("testing")))
from run_phrases import evaluate  # noqa: E402
from scripture_refs import KJV  # noqa: E402


class PhraseSheetTests(unittest.TestCase):
    def test_every_sheet_phrase(self):
        _, rows = evaluate(KJV())
        failures = [f"{r['ID']}: {r['Say this']!r} -> {r['Notes']}"
                    for r in rows if r["Result"] in ("FAIL", "PICKER")]
        self.assertEqual(failures, [], "\n" + "\n".join(failures))
        self.assertEqual(sum(r["Result"] == "PASS" for r in rows), 237)


if __name__ == "__main__":
    unittest.main()
