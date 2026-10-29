# Product thinking: can a business trust AI generated SQL?

*Fill in after your first real evaluation run. The headings and prompts below are the structure; replace every bracketed prompt with your own findings and numbers from `eval/results/`.*

## 1. The question

A non technical user asks a question in plain English and gets a number. Who checks that the number is right? This write up looks at how often the assistant is right, how it fails, and what a product would need around it before people could rely on it.

## 2. What I built

[Two or three sentences: the flow from question to answer, the guardrails, the test set.]

Design decisions made before any testing:

- **Rules in the prompt.** The first project found that revenue must use valid sale lines only, postage is not a product, and product codes differ by letter case. These are written into `app/schema.py`.
- **A way to say no.** The model can reply `CANNOT_ANSWER` instead of guessing. [Why this matters for trust.]
- **Untrusted output.** The SQL must be one read only statement, runs with a time limit and row cap.
- **The SQL is shown.** Users and analysts can read what was run, not just the number.

## 3. Results

Overall: [x of 27 correct]

| Category | Correct | Total |
|---|---|---|
| Simple aggregates | | 5 |
| Joins and filters | | 6 |
| Time | | 5 |
| Business rules | | 5 |
| Data traps | | 3 |
| Unanswerable | | 3 |

[Two sentences on which categories were strongest and weakest, and whether that surprised you.]

## 4. Failure modes

For each failed question, record the question, what the model did, and why it matters. Group them:

| Failure type | Example question | What went wrong | Business risk |
|---|---|---|---|
| Missed a business rule | | | |
| Missed a data trap (postage, letter case) | Q22, Q23 | | |
| Confident wrong answer | | | |
| Should have refused but answered | Q25, Q26, Q27 | | |
| Refused a question it could answer | | | |
| SQL error | | | |

The most important category is the **confident wrong answer**: a plausible number with no sign that it is wrong. Count how many you found and explain why they are worse than errors.

## 5. What changed the results

Run the evaluation again after each change to the prompt in `app/schema.py`, and record the before and after score. [Which rule or example moved the score most? Did anything get worse?]

## 6. What a real product would need

[Pick three or four and justify them with your own findings.]

- Show the SQL and a plain English explanation next to every answer.
- A confidence or "check this" flag for query types that failed most often.
- A fixed library of approved metrics (revenue, orders, cancellation rate) so key numbers never depend on the model.
- A feedback loop: wrong answers logged and added to the test set.
- Re running the evaluation automatically whenever the model or prompt changes.
- Clear scope messages when the data cannot answer the question.

## 7. Recommendation

[One paragraph: for which uses is this safe today, for which is it not, and what would you want to see before expanding it.]
