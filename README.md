# Finance Intelligence System

A web app that reads bank statements (PDF / CSV / XLS / XLSX / TXT / JSON), combines them with manually entered transactions, and turns them
into analytics, risk flags, income-stream analysis and a financial persona. Optional AI analysis and chat use your own API key.

## Quick start

**Mac / Linux**
1. Unzip the folder. Open **Terminal** (Cmd + Space, type "Terminal").
2. Type `cd ` (with a space), drag the unzipped folder into the Terminal window, press Enter.
3. Run: `bash run.sh`
   (first run takes about a minute; if macOS offers to install "command line developer tools", click Install, then run it again).
4. Open **http://localhost:5001** in your browser and log in with **demo / demo1234**.
5. Stop the app with `Ctrl + C`.

**Windows:** double-click `run.bat`, then open http://localhost:5001.

Needs Python 3.9 or newer (`python3 --version`). If it is missing, install it from https://www.python.org/downloads/.
The demo data is made-up sample data. To start fresh, stop the app and delete `finance.db`.

<details><summary>Manual steps (if run.sh does not work)</summary>

```
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/load_demo.py        # creates the demo accounts (first time only)
python app.py                      # then open http://localhost:5001
```
</details>

## A 5-minute tour (logged in as `demo`)
| Where | What to look at |
|---|---|
| **Dashboard** | Income, expenses, savings rate, category chart, monthly trend and a short list of insights |
| **All Records** | Every transaction. The *Cat. Source* column shows how each category was chosen (ML %, keyword Rule, Manual, Edited); chips also show income stream and any risk flag |
| **Import Statement** | Upload `sample_data/statement_1_jul_aug_2026.csv` again: it reports 0 new rows and 76 duplicates skipped. Try `sample_data/sample_statement.pdf` for PDF import. Password-protected files (PDF or Excel) are rejected for safety: upload an unprotected copy |
| **AI Insights** | Rule-based insights, recurring payments, income streams (salary / business / investment / P2P), counterparties by type, category model status. The AI analysis and chat appear here too (see below) |
| **Persona** | The profile with the reasons behind it, every rule checked, and the full JSON (copy or download) |
| **Budget Manager** | Set a monthly budget per category; spending from imported and manual records counts |

Log in as **demo_risk / demo1234** to see an account with bounced-EMI, overdraft, penalty and late-fee events (persona: Cash-Flow Stressed).
You can also sign up with your own username and add or import your own data.

## Optional: AI analysis and chat
The app works fully without this. The "Generate AI analysis" button and the finance assistant need an API key from Google (free tier available at
https://aistudio.google.com) or Anthropic. Only summarized figures are sent (totals, category spend, trends): never names, narrations or account numbers.

1. In the project folder create a file called `.env` containing (Mac: `nano .env`, paste, Ctrl+O, Enter, Ctrl+X):
   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your-key-here
   ```
   For Anthropic use `ANTHROPIC_API_KEY=your-key` instead (no `LLM_PROVIDER` line needed). Finder hides files starting with a dot: press Cmd + Shift + . to show them.
2. Restart the app (`bash run.sh`). On AI Insights the line next to the button should show the model name.
3. If it cannot connect, run `python scripts/llm_check.py` (inside the activated environment); it tells you whether the problem is the network, the key or the model name.
   If the default model is rejected, set `LLM_MODEL=` to a current model id from your provider.

## Newer additions
- **AI persona fallback (Gemini):** if no persona rule fully matches ("Mixed / Unclassified"), the Persona page also shows an *AI-suggested* persona from Gemini, with confidence and reasons. The rule-based label is never replaced. Needs `GEMINI_API_KEY`; only aggregated figures are sent. Without a key the page shows a short "unavailable" note.
- **Bigger categorisation rules:** about 440 expense keywords in 16 categories (new: Insurance, Transfers, Personal Care, Taxes) and more income keywords. Short keywords (4 letters or fewer) match whole words only. Run `python scripts/eval_categorizer.py` for rule coverage on the hand-written samples in `tests/categorizer_samples.py` (these are not real bank data and were written alongside the rules, so the score is a regression check, not an accuracy claim).
- **Statements with extra metadata (all formats):** CSV, TXT, XLS, XLSX, JSON and PDF statements no longer need manual clean-up. Bank name, account details, period, opening/closing summaries, totals and footers around the table are ignored and never stored. The transaction table is found by content (`bsi/table_finder.py`): the header row must match several column names and be followed by a row with a real date. Rows inside the table with a bad date are still reported as rejected. If no table is found, the upload fails with a clear message. Still required: a Date column, a narration/description column, withdrawal/debit and deposit/credit columns and a balance column; PDFs must contain a ruled (gridded) table.
- **Cash-flow forecast (AI Insights page):** forecasts income, expenses and net for the next 3 months from your own monthly history (complete months only; own-account "Transfers" excluded). Six candidate models are compared by walk-forward backtesting on your past months and the most accurate one is used: last month, 3-month average, exponential smoothing, damped-trend (Holt), **Ridge regression (ML)**, and recurring commitments + smoothed variable spend. The page shows the likely range (from the model's past errors), a confidence label, the chosen model and how much it beats "same as last month". An optional "Explain forecast with AI" button asks the configured LLM to explain the numbers (aggregated figures only; it does not create the forecast). Deep learning (LSTM) is not used because a user has far too few monthly points to train it. Needs at least 2 complete months (5+ for a backtested model; 9+ months for "high" confidence). Seasonality is not modelled. Code: `forecast.py`, `forecast_ai.py`; tests: `tests/test_forecast.py`.

## If something goes wrong
| Problem | Fix |
|---|---|
| `python3: command not found` or version below 3.9 | Install Python from python.org |
| "Address already in use" | Another program uses the port: `PORT=5055 bash run.sh` and open that port instead |
| Install fails on `scikit-learn` / `bcrypt` | Run `pip install --upgrade pip` inside the environment and try again |
| SSL / certificate errors when calling the AI | `pip install certifi` (already in requirements) or run "Install Certificates.command" from your Python folder |
| Blank page or odd data | Stop the app, delete `finance.db`, run `bash run.sh` again |

## How it works
* **Flask + SQLite** web app; login uses hashed passwords and tokens; every query is limited to the logged-in user.
* **Import** (`bsi/`, `importer.py`): reads CSV / XLS / XLSX / TXT / JSON / ruled-table PDFs, cleans narrations, extracts the counterparty, skips duplicates (date + amount + running balance).
* **Categories** (`categorizer.py`): ML (TF-IDF + Logistic Regression) trained on the categories you set yourself, with keyword rules as fallback. The ML model needs about 30 labelled transactions before it switches on.
* **Analytics** (`analytics.py`): totals, savings rate, trends, recurring payments, insights (plain calculations and rules, no ML).
* **Risk** (`risk.py`), **income streams** (`income.py`), **counterparty types** (`counterparty.py`), **persona** (`persona.py`): rule-based, with the reason shown for each decision. Persona thresholds are listed in the JSON and are assumptions.
* **AI analysis and chat** (`llm_insights.py`): calls the LLM provider you configure.

## Tests
```
python -m unittest tests.test_risk tests.test_income tests.test_counterparty tests.test_persona tests.test_intelligence tests.test_llm
DB_PATH=/tmp/t.db python -m unittest discover -s tests -p "test_whitebox.py"
python scripts/eval_risk.py
```
(`tests/test_pdf_password.py` also needs `pip install pypdf`, and `tests/test_formats.py` needs `pip install xlwt` to build the .xls fixture; `tests/test_*selenium*` need Chrome and are not part of the above.) The risk figure from `eval_risk.py` is a self-test on 30 narrations written for this project, not accuracy on real bank data.

## Known limits
* Tested on sample data only, not on real bank statements.
* PDF import needs tables with ruled lines; scanned (image-only) PDFs are not supported. Password-protected PDF/Excel files are rejected. TXT files must be delimited (tab, pipe, semicolon, comma) or space-aligned with no blank cells.
* Persona, income-stream and counterparty classification are rule-based heuristics, not validated models.
* Loan/purchase guidance is not built (shown as a placeholder on AI Insights). Cash-flow forecasting is built (see above).
