"""
streamlit_app.py
A small web app: type a question in plain English, see the SQL the model wrote,
the result table, and say whether the answer was right.

Run:  streamlit run app/streamlit_app.py
"""
import csv
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm import ask_model  # noqa: E402
from app.pipeline import DB_PATH, answer  # noqa: E402

FEEDBACK_PATH = "data/feedback.csv"  # local only, ignored by git

EXAMPLES = [
    "What is the total revenue from valid sales?",
    "Which 5 countries have the highest revenue?",
    "Show the top 10 products by revenue.",
    "What was the revenue in each month?",
    "What is the order cancellation rate?",
    "How many units of product 15056BL were sold?",
    "What is our profit margin?",
]

st.set_page_config(page_title="Retail data assistant", layout="wide")
st.title("Ask the retail database")
st.caption("UK online retailer, Dec 2010 to 9 Dec 2011. The AI writes SQL; you can read it, "
           "check it and tell me if it is wrong.")

if not os.path.exists(DB_PATH):
    st.error(f"Database not found at {DB_PATH}. See the README for how to build it.")
    st.stop()

with st.sidebar:
    st.subheader("Try an example")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state["question"] = ex

question = st.text_input("Your question", key="question",
                         placeholder="For example: Which country has the most customers?")

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Thinking..."):
        try:
            st.session_state["result"] = answer(question.strip(), ask_model)
            st.session_state["asked"] = question.strip()
        except Exception as exc:
            st.session_state["result"] = None
            st.error(f"The model call failed: {exc}")

res = st.session_state.get("result")
if res:
    if res["status"] == "refused":
        st.warning(f"The assistant could not answer this from the data: {res['message']}")
    else:
        st.subheader("SQL the model wrote")
        st.code(res["sql"] or "", language="sql")
        if res["status"] == "blocked":
            st.error(f"Blocked by the safety check: {res['message']}")
        elif res["status"] == "sql_error":
            st.error(f"The query failed: {res['message']}")
        else:
            df = pd.DataFrame(res["rows"], columns=res["columns"])
            st.subheader(f"Result ({len(df)} rows)")
            st.dataframe(df, use_container_width=True)
            if res["truncated"]:
                st.info("Showing the first 1,000 rows only.")

    st.write("Was this answer correct?")
    col1, col2, _ = st.columns([1, 1, 8])
    verdict = "correct" if col1.button("Yes") else "wrong" if col2.button("No") else None
    if verdict:
        os.makedirs(os.path.dirname(FEEDBACK_PATH), exist_ok=True)
        new = not os.path.exists(FEEDBACK_PATH)
        with open(FEEDBACK_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "question", "sql", "verdict"])
            w.writerow([datetime.now().isoformat(timespec="seconds"),
                        st.session_state.get("asked", ""), res["sql"] or "", verdict])
        st.success("Thanks, saved locally.")
