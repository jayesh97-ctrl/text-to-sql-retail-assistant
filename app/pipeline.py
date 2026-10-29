"""
pipeline.py
The full question-to-answer flow used by both the web app and the evaluation:
ask the model, parse the reply, validate the SQL, run it read-only.
"""
import os

from app.safety import UnsafeSQLError, extract_sql, run_readonly

DB_PATH = os.environ.get("RETAIL_DB_PATH", "data/retail.db")


def answer(question: str, model_fn, db_path: str = DB_PATH) -> dict:
    """
    Returns a dict with: status ("ok", "refused", "blocked", "sql_error"),
    sql, columns, rows, truncated, message.
    """
    result = {"status": "ok", "sql": None, "columns": [], "rows": [],
              "truncated": False, "message": "", "raw": ""}
    raw = model_fn(question)
    result["raw"] = raw
    kind, payload = extract_sql(raw)
    if kind == "refuse":
        result.update(status="refused", message=payload)
        return result
    result["sql"] = payload
    try:
        cols, rows, truncated = run_readonly(db_path, payload)
    except UnsafeSQLError as exc:
        result.update(status="blocked", message=str(exc))
        return result
    except Exception as exc:  # sqlite3.Error, timeouts
        result.update(status="sql_error", message=str(exc))
        return result
    result.update(columns=cols, rows=rows, truncated=truncated)
    return result
