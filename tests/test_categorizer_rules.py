"""Keyword-rule regression tests. Run: python -m unittest tests.test_categorizer_rules"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import categorizer as C                       # noqa: E402
from categorizer_samples import SAMPLES       # noqa: E402

class Rules(unittest.TestCase):
    def test_samples(self):
        bad = [(t, n, want, C.rule_categorize(n, t)) for t, n, want in SAMPLES if C.rule_categorize(n, t) != want]
        self.assertEqual(bad, [])
    def test_whole_word_for_short_keywords(self):
        self.assertIsNone(C.rule_categorize("SATMAN", "expense")); self.assertEqual(C.rule_categorize("ATM WDL", "expense"), "Cash")
    def test_no_duplicate_keyword_across_categories_in_conflict(self):
        seen = {}
        for cat, kws in C.EXPENSE_RULES:
            for k in kws: seen.setdefault(k, set()).add(cat)
        self.assertEqual({k: v for k, v in seen.items() if len(v) > 1}, {})
if __name__ == "__main__":
    unittest.main()
