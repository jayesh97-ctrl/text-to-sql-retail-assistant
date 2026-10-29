"""
safety.py
Guardrails between the model and the database. The model is treated as an
untrusted author: its SQL is checked before it runs, and it runs on a
read-only connection with a time limit and a row cap.
"""
import re
import sqlite3
import time

MAX_ROWS = 1000
TIMEOUT_SECONDS = 10

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "truncate",
}


class UnsafeSQLError(ValueError):
    """Raised when generated SQL is not a single read-only query."""


def extract_sql(model_output: str):
    """
    Parse the model reply. Returns ("sql", query) or ("refuse", reason).
    """
    text = model_output.strip()
    if text.upper().startswith("CANNOT_ANSWER"):
        reason = text.split(":", 1)[1].strip() if ":" in text else "No reason given."
        return "refuse", reason
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    query = match.group(1) if match else text
    return "sql", query.strip().rstrip(";").strip()


def validate_sql(query: str) -> str:
    """Return the query if it is a single read-only statement, else raise UnsafeSQLError."""
    if not query:
        raise UnsafeSQLError("Empty query.")
    # Remove comments and string literals before looking for keywords or ';'.
    no_comments = re.sub(r"--.*?$|/\*.*?\*/", " ", query, flags=re.DOTALL | re.MULTILINE)
    no_strings = re.sub(r"'(?:[^']|'')*'", "''", no_comments)
    if ";" in no_strings:
        raise UnsafeSQLError("Only one statement is allowed.")
    words = re.findall(r"[a-zA-Z_]+", no_strings.lower())
    if not words or words[0] not in {"select", "with"}:
        raise UnsafeSQLError("Only SELECT queries are allowed.")
    bad = FORBIDDEN.intersection(words)
    if bad:
        raise UnsafeSQLError(f"Forbidden keyword: {sorted(bad)[0]}")
    return query


def run_readonly(db_path: str, query: str, max_rows: int = MAX_ROWS):
    """
    Run a validated query on a read-only connection.
    Returns (columns, rows, truncated).
    """
    validate_sql(query)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    # Returning non-zero from the progress handler aborts the query.
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    try:
        cur = conn.execute(query)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        return columns, rows[:max_rows], truncated
    finally:
        conn.close()
