"""Rule coverage/accuracy on the hand-written samples in tests/categorizer_samples.py (not real data).
Run from the project folder: python scripts/eval_categorizer.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
import categorizer as C
from categorizer_samples import SAMPLES
hit = [(t, n, w, C.rule_categorize(n, t)) for t, n, w in SAMPLES]
cov = [x for x in hit if x[3] is not None]; ok = [x for x in hit if x[3] == x[2]]
print(f"samples: {len(hit)} | rule matched: {len(cov)} | correct: {len(ok)} ({len(ok)/len(hit)*100:.1f}%)")
print(f"keywords: {sum(len(k) for _, k in C.EXPENSE_RULES)} expense in {len(C.EXPENSE_RULES)} categories, {sum(len(k) for _, k in C.INCOME_RULES)} income in {len(C.INCOME_RULES)} categories")
for x in hit:
    if x[3] != x[2]: print("MISS", x)
