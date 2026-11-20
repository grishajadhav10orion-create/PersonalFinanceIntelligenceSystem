"""
Cash-flow forecast: next months' income, expenses and net, from the user's own monthly history.

Method (small-data time-series ML, all computed on the server from stored records):
  1. Build monthly income and expense series (complete months only; own-account "Transfers" are left out).
  2. Several candidate models forecast each series: last month, 3-month average, exponential smoothing, damped-trend
     (Holt) smoothing, Ridge regression on (last month + time trend) [machine learning], and "recurring commitments +
     smoothed variable part".
  3. Walk-forward backtesting picks the model with the lowest error on the user's own past months (each past month is
     predicted using only the months before it). No model is chosen by assumption.
  4. The likely range comes from that model's past errors; confidence depends on history length and backtest error.
Deep learning (LSTM etc.) is deliberately not used: a user has a few to a few dozen monthly points, far too few to train it.
Pure functions over record dicts (as returned by database.get_records); no network calls.
"""
import datetime
import math
from collections import defaultdict

import numpy as np
from sklearn.linear_model import Ridge

import analytics

HORIZON = 3
MIN_MONTHS_MODEL = 5        # below this: simple average only, no backtest
MAX_FOLDS = 4
EXCLUDED_EXPENSE_CATEGORIES = {"transfers"}       # own-account moves (e.g. credit-card bill payments)
RANGE_FACTOR = 1.6          # ~80% range from mean absolute backtest error (MAE ~ 0.8 sigma)


# ---------------- forecasting models: f(values, horizon, fixed) -> list of `horizon` predictions ----------------
def _m_last(v, h, fixed):
    return [v[-1]] * h


def _m_avg3(v, h, fixed):
    return [float(np.mean(v[-3:]))] * h


def _ses_level(v):
    best = None
    for a in (0.2, 0.35, 0.5, 0.65, 0.8):
        lvl, sse = v[0], 0.0
        for x in v[1:]:
            sse += (x - lvl) ** 2
            lvl = a * x + (1 - a) * lvl
        if best is None or sse < best[0]:
            best = (sse, lvl)
    return best[1]


def _m_ses(v, h, fixed):
    return [_ses_level(v)] * h


def _m_holt(v, h, fixed, phi=0.9):
    best = None
    for a in (0.3, 0.5, 0.7):
        for b in (0.1, 0.3):
            lvl, tr, sse = v[0], v[1] - v[0], 0.0
            for x in v[1:]:
                pred = lvl + phi * tr
                sse += (x - pred) ** 2
                new = a * x + (1 - a) * pred
                tr = b * (new - lvl) + (1 - b) * phi * tr
                lvl = new
            if best is None or sse < best[0]:
                best = (sse, lvl, tr)
    _, lvl, tr = best
    return [lvl + sum(phi ** i for i in range(1, k + 1)) * tr for k in range(1, h + 1)]


def _m_ridge(v, h, fixed):
    """ML: Ridge regression y[t] ~ y[t-1] + time index, on the series scaled by its mean; forecasts recursively."""
    sc = float(np.mean(v)) or 1.0
    y = np.array(v, float) / sc
    X = np.array([[y[i - 1], i / len(y)] for i in range(1, len(y))])
    model = Ridge(alpha=1.0).fit(X, y[1:])
    hist, out = list(y), []
    for k in range(h):
        t = (len(y) + k) / len(y)
        nxt = float(model.predict([[hist[-1], t]])[0])
        hist.append(nxt); out.append(nxt * sc)
    return out


def _m_fixed_var(v, h, fixed):
    """Known recurring commitments (constant) + exponentially smoothed variable remainder."""
    var = [max(x - fixed, 0.0) for x in v]
    return [fixed + _ses_level(var)] * h


MODELS = [("Last month", _m_last, 1, "baseline"), ("3-month average", _m_avg3, 1, "statistical"),
          ("Exponential smoothing", _m_ses, 2, "statistical"), ("Damped-trend smoothing (Holt)", _m_holt, 3, "statistical"),
          ("Ridge regression (lag + trend)", _m_ridge, 3, "ML"), ("Recurring commitments + variable", _m_fixed_var, 2, "rule + statistical")]


# ---------------- data preparation ----------------
def _month_add(m, k):
    y, mo = int(m[:4]), int(m[5:7])
    t = y * 12 + (mo - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _is_consecutive(a, b):
    return _month_add(a, 1) == b


def _usable_records(records):
    out = []
    for r in records:
        if not analytics._valid_month(r.get("date")) or not (r.get("amount") or 0) > 0:
            continue
        if r["type"] == "expense" and (r.get("category") or "").strip().lower() in EXCLUDED_EXPENSE_CATEGORIES:
            continue
        out.append(r)
    return out


def _series(records, today):
    """Returns (months, income[], expenses[], notes) for the latest contiguous run of complete months."""
    notes = []
    tot = defaultdict(lambda: [0.0, 0.0])
    for r in records:
        tot[r["date"][:7]][0 if r["type"] == "earning" else 1] += r["amount"]
    months = sorted(tot)
    if months and months[-1] == today.strftime("%Y-%m"):
        notes.append(f"{months[-1]} is still in progress, so it was left out of the history.")
        months = months[:-1]
    run = months[-1:] if months else []
    for m in reversed(months[:-1]):
        if _is_consecutive(m, run[0]):
            run.insert(0, m)
        else:
            notes.append(f"Months before a gap in your data ({m} and earlier) were not used.")
            break
    return run, [tot[m][0] for m in run], [tot[m][1] for m in run], notes


def _fixed_monthly(records, typ, upto_month, window_start, last_seen_from):
    """Monthly total of recurring items of this type, detected only from records before `upto_month`."""
    rs = [r for r in records if window_start <= r["date"][:7] < upto_month]
    sigs = [s for s in analytics.recurring_signals(rs) if s["type"] == typ and s["last_date"][:7] >= last_seen_from]
    return sum(analytics.monthly_equivalent(s) for s in sigs)


# ---------------- backtesting and selection ----------------
def _backtest(values, months, records, typ):
    n = len(values)
    folds = list(range(max(4, n - MAX_FOLDS), n))
    rows = []
    for name, fn, min_len, kind in MODELS:
        errs, ok = [], True
        for t in folds:
            if t < min_len + (1 if fn is _m_ridge else 0) or t < 3:
                ok = False; break
            fixed = _fixed_monthly(records, typ, months[t], months[0], months[t - 1]) if fn is _m_fixed_var else 0.0
            if fn is _m_fixed_var and fixed <= 0:
                ok = False; break
            try:
                pred = fn(values[:t], 1, fixed)[0]
            except Exception:
                ok = False; break
            errs.append(abs(values[t] - max(pred, 0.0)))
        rows.append({"model": name, "kind": kind, "mae": round(float(np.mean(errs)), 2) if ok and errs else None,
                     "folds": len(errs) if ok else 0})
    return folds, rows


def _confidence(n_months, mae, values):
    mean = float(np.mean(values[-6:])) or 1.0
    rel = mae / mean if mae is not None else None
    if rel is None:
        return "low", rel
    if n_months >= 9 and rel < 0.10:
        return "high", rel
    if n_months >= 6 and rel < 0.20:
        return "medium", rel
    return "low", rel


def _forecast_series(values, months, records, typ, h):
    n = len(values)
    if n < MIN_MONTHS_MODEL:
        pred = _m_avg3(values, h, 0.0)
        return {"chosen": "3-month average" if n >= 3 else "Average of available months", "kind": "baseline",
                "values": [float(np.mean(values[-3:]))] * h, "half_width": None, "backtest": [], "folds": 0,
                "mae": None, "baseline_mae": None, "improvement_pct": None, "confidence": "low", "relative_error_pct": None}
    folds, rows = _backtest(values, months, records, typ)
    valid = [r for r in rows if r["mae"] is not None]
    best = min(valid, key=lambda r: r["mae"])            # ties: first in MODELS order (simpler model)
    fn = next(f for nm, f, _, _ in MODELS if nm == best["model"])
    fixed = _fixed_monthly(records, typ, _month_add(months[-1], 1), months[0], months[-1]) if fn is _m_fixed_var else 0.0
    vals = [max(x, 0.0) for x in fn(values, h, fixed)]
    base = next((r["mae"] for r in rows if r["model"] == "Last month"), None)
    imp = round((base - best["mae"]) / base * 100, 1) if base and base > 0 else None
    conf, rel = _confidence(n, best["mae"], values)
    for r in rows:
        r["chosen"] = r["model"] == best["model"]
    return {"chosen": best["model"], "kind": best["kind"], "values": vals, "half_width": best["mae"] * RANGE_FACTOR,
            "backtest": rows, "folds": len(folds), "mae": best["mae"], "baseline_mae": base, "improvement_pct": imp,
            "confidence": conf, "relative_error_pct": round(rel * 100, 1) if rel is not None else None}


def _band(value, hw, step):
    if hw is None:
        return {"value": round(value, 2), "low": None, "high": None}
    w = hw * math.sqrt(step)
    return {"value": round(value, 2), "low": round(max(value - w, 0.0), 2), "high": round(value + w, 2)}


def compute_forecast(records, today=None, horizon=HORIZON):
    today = today or datetime.date.today()
    recs = _usable_records(records)
    months, inc, exp, notes = _series(recs, today)
    if len(months) < 2:
        return {"status": "insufficient_data", "months_used": len(months), "horizon": horizon,
                "message": "At least 2 complete months of transactions are needed. Import or add more history.", "notes": notes}
    window = [r for r in recs if months[0] <= r["date"][:7] <= months[-1]]
    fi = _forecast_series(inc, months, window, "earning", horizon)
    fe = _forecast_series(exp, months, window, "expense", horizon)
    out = []
    for k in range(horizon):
        i, e = _band(fi["values"][k], fi["half_width"], k + 1), _band(fe["values"][k], fe["half_width"], k + 1)
        net = round(i["value"] - e["value"], 2)
        hw = None if fi["half_width"] is None or fe["half_width"] is None else math.hypot(
            fi["half_width"], fe["half_width"]) * math.sqrt(k + 1)
        out.append({"month": _month_add(months[-1], k + 1), "income": i, "expenses": e,
                    "net": {"value": net, "low": None if hw is None else round(net - hw, 2),
                            "high": None if hw is None else round(net + hw, 2)}})
    sigs = [s for s in analytics.recurring_signals(window) if s["last_date"][:7] >= months[-1]]
    commit = round(sum(analytics.monthly_equivalent(s) for s in sigs if s["type"] == "expense"), 2)
    nxt = out[0]
    spend_over = round((nxt["expenses"]["value"] - nxt["income"]["value"]) / nxt["income"]["value"] * 100, 1) \
        if nxt["income"]["value"] > 0 and nxt["expenses"]["value"] > nxt["income"]["value"] else None
    if len(months) < 6:
        notes.append("Only a few months of history: the forecast is rough. It improves as you add more months.")
    notes.append("Seasonality (festivals, annual bills) cannot be learned from less than two years of data.")
    strip = lambda f: {k: v for k, v in f.items() if k not in ("values", "half_width")}
    return {"status": "ok", "months_used": len(months), "horizon": horizon, "last_month": months[-1],
            "history": [{"month": m, "income": round(a, 2), "expenses": round(b, 2), "net": round(a - b, 2)}
                        for m, a, b in zip(months, inc, exp)],
            "forecast": out, "next_month_spend_over_income_pct": spend_over,
            "income_model": strip(fi), "expense_model": strip(fe), "recurring_expense_commitments_monthly": commit,
            "notes": notes,
            "method": "Candidate models are tested on your own past months (walk-forward) and the most accurate one is used. "
                      "ML model: Ridge regression. Deep learning is not used: too little data per user."}
