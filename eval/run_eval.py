"""
run_eval.py
Scores the text-to-SQL assistant against eval/questions.json.

How a question is scored
  * The gold query is run, and the model's query is run, on the same database.
  * Results are compared by VALUES, not by SQL text, because many different queries
    are correct. Column names, extra columns and column order are ignored.
  * If the gold result has numeric columns, those columns must match (within a small
    tolerance) and the row count must be equal. If it has none, all columns must match.
  * "expect": "refuse" questions pass only if the model declines. "refuse_or_empty"
    passes if the model declines or returns nothing / NULL / zero.

Usage
  python -m eval.run_eval              # real model (needs .env)
  python -m eval.run_eval --mock       # harness self test: the gold SQL plays the model
  python -m eval.run_eval --limit 5    # first 5 questions only
"""
import argparse
import csv
import itertools
import json
import math
import os
import time
from collections import Counter, defaultdict
from datetime import datetime

from app.pipeline import DB_PATH, answer
from app.safety import run_readonly

QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "questions.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


# ---------- comparison ----------

def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _close(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-3, abs_tol=0.011)


def _col(rows, i):
    return [r[i] for r in rows]


def _cols_match(gcol, hcol, ordered, scale=1.0):
    if len(gcol) != len(hcol):
        return False
    if all(_is_num(v) or v is None for v in gcol + hcol):
        g = [0.0 if v is None else float(v) for v in gcol]
        h = [0.0 if v is None else float(v) * scale for v in hcol]
        if not ordered:
            g, h = sorted(g), sorted(h)
        return all(_close(a, b) for a, b in zip(g, h))
    g = [str(v).strip().lower() for v in gcol]
    h = [str(v).strip().lower() for v in hcol]
    return g == h if ordered else sorted(g) == sorted(h)


def results_match(gold_rows, gen_rows, ordered=False, accept_percent_scale=False):
    if len(gold_rows) != len(gen_rows):
        return False
    if not gold_rows:
        return True
    width_g = len(gold_rows[0])
    width_h = len(gen_rows[0]) if gen_rows else 0
    num_idx = [i for i in range(width_g) if all(_is_num(r[i]) for r in gold_rows)]
    target = num_idx if num_idx else list(range(width_g))
    scales = [1.0, 0.01] if accept_percent_scale else [1.0]
    for scale in scales:
        candidates = []
        for i in target:
            gcol = _col(gold_rows, i)
            candidates.append([j for j in range(width_h)
                               if _cols_match(gcol, _col(gen_rows, j), ordered, scale)])
        if all(candidates):
            return True
    return False


def is_empty(rows):
    return not rows or all(all(v in (None, 0, 0.0) for v in r) for r in rows)


# ---------- scoring ----------

def score_question(q, model_fn, db_path):
    out = {"id": q["id"], "category": q["category"], "question": q["question"],
           "outcome": "", "generated_sql": "", "message": ""}
    start = time.time()
    try:
        res = answer(q["question"], model_fn, db_path)
    except Exception as exc:  # model/API failure
        out.update(outcome="fail_model_error", message=str(exc))
        return out
    out["seconds"] = round(time.time() - start, 2)
    out["generated_sql"] = res["sql"] or ""
    out["message"] = res["message"]
    expect = q.get("expect")

    if expect == "refuse":
        out["outcome"] = "pass" if res["status"] == "refused" else "fail_should_have_refused"
        return out
    if expect == "refuse_or_empty":
        ok = res["status"] == "refused" or (res["status"] == "ok" and is_empty(res["rows"]))
        out["outcome"] = "pass" if ok else "fail_should_have_refused"
        return out

    if res["status"] == "refused":
        out["outcome"] = "fail_wrongly_refused"
    elif res["status"] == "blocked":
        out["outcome"] = "fail_blocked_by_guardrail"
    elif res["status"] == "sql_error":
        out["outcome"] = "fail_sql_error"
    else:
        _, gold_rows, _ = run_readonly(db_path, q["gold_sql"])
        ok = results_match(gold_rows, res["rows"], q.get("ordered", False),
                           q.get("accept_percent_scale", False))
        out["outcome"] = "pass" if ok else "fail_wrong_result"
    return out


def mock_model(questions):
    by_q = {q["question"]: q for q in questions}

    def fn(question):
        q = by_q[question]
        if q.get("gold_sql"):
            return f"```sql\n{q['gold_sql']}\n```"
        return "CANNOT_ANSWER: mock refusal"
    return fn


def write_reports(rows, label):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(RESULTS_DIR, f"{label}_{stamp}")
    with open(base + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "category", "question", "outcome",
                                          "generated_sql", "message", "seconds"])
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in w.fieldnames} for r in rows)

    total = len(rows)
    passed = sum(r["outcome"] == "pass" for r in rows)
    by_cat = defaultdict(lambda: [0, 0])
    for r in rows:
        by_cat[r["category"]][1] += 1
        by_cat[r["category"]][0] += r["outcome"] == "pass"
    fails = Counter(r["outcome"] for r in rows if r["outcome"] != "pass")

    lines = [f"# Evaluation results ({label}, {stamp})", "",
             f"Overall: {passed}/{total} correct ({passed / total:.0%})", "",
             "| Category | Correct | Total |", "|---|---|---|"]
    lines += [f"| {c} | {p} | {t} |" for c, (p, t) in by_cat.items()]
    lines += ["", "## Failure types", ""]
    lines += [f"- {k}: {v}" for k, v in fails.most_common()] or ["- none"]
    lines += ["", "## Failed questions", ""]
    for r in rows:
        if r["outcome"] != "pass":
            lines.append(f"- {r['id']} ({r['outcome']}): {r['question']}")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return base, passed, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="use gold SQL as the model (harness self test)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    questions = json.load(open(QUESTIONS_PATH, encoding="utf-8"))
    if args.limit:
        questions = questions[: args.limit]
    if args.mock:
        model_fn, label = mock_model(questions), "mock"
    else:
        from app.llm import ask_model
        model_fn, label = ask_model, "model"

    rows = []
    for q in questions:
        r = score_question(q, model_fn, args.db)
        print(f"{r['id']} {r['outcome']:<28} {q['question']}")
        rows.append(r)
    base, passed, total = write_reports(rows, label)
    print(f"\n{passed}/{total} correct. Saved {base}.csv and {base}.md")


if __name__ == "__main__":
    main()
