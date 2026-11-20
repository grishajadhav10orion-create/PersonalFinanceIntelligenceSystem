"""AI persona fallback tests (the Gemini call is mocked; no network, no key needed). Run: python -m unittest tests.test_persona_ai"""
import json, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import persona as P, persona_ai as PA, llm_insights as L          # noqa: E402
from test_persona import months                                    # noqa: E402

UNCLASSIFIED = months(4, salary=60000, rent=33000, food=25000)      # no rule fully matches
GOOD = json.dumps({"label": "Stretched Salaried Earner", "is_new_label": True, "confidence": "medium",
                   "reasons": ["Savings rate is about 3%", "Salary share is 100%"], "closest_rule": "Balanced Salaried Earner"})

class PersonaAI(unittest.TestCase):
    def setUp(self):
        PA._cache.clear(); PA._last_call.clear()
        self.env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}); self.env.start()
    def tearDown(self): self.env.stop()

    def test_fixture_is_unclassified(self):
        self.assertEqual(P.compute_persona(UNCLASSIFIED)["persona"]["label"], "Mixed / Unclassified")

    def test_rule_matched_persona_never_calls_ai(self):
        p = P.compute_persona(months(4, salary=80000, rent=20000, food=4000))
        with mock.patch.object(L, "_call_api") as m:
            PA.attach("u1", p)
        m.assert_not_called(); self.assertNotIn("ai_classification", p)

    def test_unclassified_uses_gemini_and_keeps_rule_label(self):
        p = P.compute_persona(UNCLASSIFIED)
        with mock.patch.object(L, "_call_api", return_value=GOOD) as m:
            PA.attach("u2", p)
        self.assertEqual(m.call_args.kwargs["force_provider"], "gemini")
        self.assertEqual(p["persona"]["label"], "Mixed / Unclassified")       # rule label untouched
        ai = p["ai_classification"]
        self.assertEqual((ai["label"], ai["is_new_label"], ai["source"]), ("Stretched Salaried Earner", True, "ai"))

    def test_known_label_is_not_new_even_if_model_says_so(self):
        r = PA.parse_response(json.dumps({"label": "balanced salaried earner", "is_new_label": True, "confidence": "high", "reasons": []}))
        self.assertEqual((r["label"], r["is_new_label"]), ("Balanced Salaried Earner", False))

    def test_payload_has_no_names_or_narrations(self):
        recs = UNCLASSIFIED + [dict(UNCLASSIFIED[0], receiver_payer="SECRET PERSON NAME", raw_narration="UPI-SECRET PERSON NAME-ACC9988776655")]
        sent = json.dumps(PA.build_context(P.compute_persona(recs)))
        for bad in ("SECRET", "Acme", "Landlord", "Swiggy", "9988776655"): self.assertNotIn(bad, sent)

    def test_bad_reply_and_missing_key_are_reported_not_raised(self):
        p = P.compute_persona(UNCLASSIFIED)
        with mock.patch.object(L, "_call_api", return_value="not json"):
            PA.attach("u3", p)
        self.assertEqual(p["ai_classification"]["status"], "error")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            p2 = P.compute_persona(UNCLASSIFIED); PA.attach("u4", p2)
        self.assertEqual(p2["ai_classification"]["status"], "not_configured")

    def test_cached_second_call(self):
        with mock.patch.object(L, "_call_api", return_value=GOOD) as m:
            PA.classify("u5", P.compute_persona(UNCLASSIFIED)); r = PA.classify("u5", P.compute_persona(UNCLASSIFIED))
        self.assertEqual(m.call_count, 1); self.assertTrue(r["cached"])

if __name__ == "__main__":
    unittest.main()
