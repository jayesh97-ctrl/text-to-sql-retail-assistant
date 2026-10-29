# Text to SQL Retail Assistant

Ask questions about a UK online retailer's sales in plain English. An AI model writes the SQL, the app shows it, runs it safely on a read only database, and returns the result. The project also measures how often the model is right, and writes up where and why it fails.

This is the second half of a pair. The first project, [SQL and Power BI Retail Reporting Pipeline](https://github.com/jayesh97-ctrl/sql-powerbi-retail-pipeline), built the cleaned star schema this assistant queries.

## Why this project exists

Anyone can get a model to produce SQL. The harder product question is: **when can a business trust the answer?** This project treats that as the main deliverable.

- The model is given the schema and the business rules learned in the first project (what counts as a valid sale, why postage lines are not products, why product codes need case insensitive matching).
- It is allowed to say "I cannot answer this" when the data is not there.
- Its SQL is treated as untrusted: one read only statement, a time limit and a row cap.
- A 27 question test set with checked answers scores it, including questions built around known data traps.

## How it works

```
Question -> model (schema + rules in the prompt) -> SQL or CANNOT_ANSWER
         -> safety check (single SELECT only) -> read only SQLite -> result table
```

| File | Purpose |
|---|---|
| `app/schema.py` | The context given to the model: tables, joins, business rules, output format |
| `app/llm.py` | The only place that talks to the AI provider |
| `app/safety.py` | Parses the reply, blocks anything that is not one read only query, runs it with a timeout and row cap |
| `app/pipeline.py` | Question to answer flow shared by the app and the evaluation |
| `app/streamlit_app.py` | The web app, with a "was this right?" button that logs feedback locally |
| `eval/questions.json` | 27 questions, each with a checked gold query, in six groups |
| `eval/run_eval.py` | Scores the model by comparing result values, not SQL text |
| `tests/` | Tests for the guardrails and the scoring logic, no API key needed |
| `docs/product_thinking.md` | What the results mean for trusting AI generated SQL |

## Set up

1. Build the database. Run the pipeline from the [first project](https://github.com/jayesh97-ctrl/sql-powerbi-retail-pipeline) (load, then `sql/02_staging_clean.sql` and `sql/03_star_schema.sql`). Copy the resulting `data/retail.db` into this project's `data` folder. It is not committed because of its size.
2. Create a virtual environment and install packages:

   ```
   python -m venv .venv
   .venv\Scripts\activate          # on Mac or Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env`, add your Anthropic API key and a current model name from the Anthropic docs. `.env` is in `.gitignore` and must never be committed.
4. Check everything works without spending anything:

   ```
   python -m pytest -q
   python -m eval.run_eval --mock
   ```

   The mock run lets the gold queries play the model, so it should score 27 out of 27. If it does not, the database or scoring is wrong, not the AI.

## Run it

```
streamlit run app/streamlit_app.py
```

Run the evaluation with a real model:

```
python -m eval.run_eval
```

Results are written to `eval/results/` as a CSV (every question, the SQL, the outcome) and a Markdown summary.

## How answers are scored

Many different queries are correct, so the evaluation compares what the queries return rather than the SQL text. Column names, column order and extra columns are ignored. If the correct answer has numeric columns, those must match within a small tolerance and the row count must be equal. Questions with no answer in the data pass only if the model declines.

Known limitation: this checks numbers and row counts, so a query that returns the right numbers with the wrong labels could pass. Each failure is also reviewed by hand in the write up.

The 27 questions cover: simple aggregates, joins and filters, time questions, business rules, data traps, and unanswerable or out of range questions.

## Results

*To be filled in after the first real run. See `docs/product_thinking.md`.*

| Category | Correct | Total |
|---|---|---|
| Simple aggregates | | 5 |
| Joins and filters | | 6 |
| Time | | 5 |
| Business rules | | 5 |
| Data traps | | 3 |
| Unanswerable | | 3 |

## Limits and next steps

- One database, one SQL dialect (SQLite). Other schemas would need their own context file and test set.
- The model sees the whole schema in every request. A larger warehouse would need retrieval of relevant tables first.
- Feedback is logged locally only. A real product would feed it back into the test set.

## Data

UCI Online Retail dataset (Dec 2010 to Dec 2011), cleaned in the first project. MIT licence.
