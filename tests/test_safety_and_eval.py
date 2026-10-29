"""
Tests for the guardrails and the scoring logic. They run without an API key.
Run:  python -m pytest -q
"""
import sqlite3

import pytest

from app.safety import UnsafeSQLError, extract_sql, run_readonly, validate_sql
from eval.run_eval import results_match


def test_extract_sql_from_code_block():
    kind, sql = extract_sql("Here you go:\n```sql\nSELECT 1;\n```")
    assert kind == "sql" and sql == "SELECT 1"


def test_extract_refusal():
    kind, reason = extract_sql("CANNOT_ANSWER: no cost data")
    assert kind == "refuse" and "cost" in reason


@pytest.mark.parametrize("bad", [
    "DROP TABLE fact_sales",
    "DELETE FROM fact_sales",
    "SELECT 1; DROP TABLE fact_sales",
    "UPDATE fact_sales SET quantity = 0",
    "PRAGMA table_info(fact_sales)",
    "WITH x AS (SELECT 1) DELETE FROM fact_sales",
    "",
])
def test_blocks_unsafe_sql(bad):
    with pytest.raises(UnsafeSQLError):
        validate_sql(bad)


def test_allows_select_and_cte_and_keywords_in_strings():
    validate_sql("SELECT 'drop; table' AS note")
    validate_sql("WITH t AS (SELECT 1 AS a) SELECT a FROM t")


def test_readonly_connection_cannot_write(tmp_path):
    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    cols, rows, truncated = run_readonly(db, "SELECT a FROM t")
    assert rows == [(1,)] and not truncated


def test_row_cap(tmp_path):
    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(50)])
    conn.commit()
    conn.close()
    _, rows, truncated = run_readonly(db, "SELECT a FROM t", max_rows=10)
    assert len(rows) == 10 and truncated


def test_match_ignores_extra_columns_and_names():
    gold = [("A", 10.0), ("B", 5.0)]
    gen = [("A", "A-code", 10.004), ("B", "B-code", 5.0)]
    assert results_match(gold, gen, ordered=True)


def test_match_detects_wrong_numbers():
    assert not results_match([(10.0,)], [(11.0,)])


def test_match_order_matters_only_when_ordered():
    gold = [("A", 2.0), ("B", 1.0)]
    gen = [("B", 1.0), ("A", 2.0)]
    assert results_match(gold, gen, ordered=False)
    assert not results_match(gold, gen, ordered=True)


def test_percent_scale_accepted_only_when_allowed():
    assert results_match([(0.148,)], [(14.8,)], accept_percent_scale=True)
    assert not results_match([(0.148,)], [(14.8,)])


def test_row_count_must_match():
    assert not results_match([(1.0,), (2.0,)], [(1.0,)])


# ---------- harness catches the known traps (needs data/retail.db) ----------
import json
import os

from eval.run_eval import QUESTIONS_PATH, score_question

DB = os.environ.get("RETAIL_DB_PATH", "data/retail.db")
needs_db = pytest.mark.skipif(not os.path.exists(DB), reason="build data/retail.db first")


def _q(qid):
    return next(q for q in json.load(open(QUESTIONS_PATH)) if q["id"] == qid)


@needs_db
def test_harness_catches_postage_trap():
    naive = lambda _: ("```sql\nSELECT stock_code, ROUND(SUM(line_revenue),2) r FROM fact_sales "
                       "WHERE is_cancelled = 0 GROUP BY stock_code ORDER BY r DESC LIMIT 1\n```")
    assert score_question(_q("Q22"), naive, DB)["outcome"] == "fail_wrong_result"


@needs_db
def test_harness_catches_case_sensitive_code_trap():
    naive = lambda _: ("```sql\nSELECT SUM(quantity) FROM fact_sales "
                       "WHERE stock_code = '15056BL' AND is_valid_sale_line = 1\n```")
    assert score_question(_q("Q23"), naive, DB)["outcome"] == "fail_wrong_result"


@needs_db
def test_harness_scores_refusals_and_sql_errors():
    assert score_question(_q("Q25"), lambda _: "CANNOT_ANSWER: no costs", DB)["outcome"] == "pass"
    assert score_question(_q("Q25"), lambda _: "```sql\nSELECT 1\n```", DB)["outcome"] == "fail_should_have_refused"
    assert score_question(_q("Q01"), lambda _: "```sql\nSELECT nope FROM fact_sales\n```", DB)["outcome"] == "fail_sql_error"
    assert score_question(_q("Q01"), lambda _: "```sql\nDROP TABLE fact_sales\n```", DB)["outcome"] == "fail_blocked_by_guardrail"
