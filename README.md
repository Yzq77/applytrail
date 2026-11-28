# Application Tracking

A local-first job application tracker that shows where your applications stall and why.
Your data stays on your computer: it lives in a git-ignored SQLite file, and the app only
listens on `127.0.0.1` and makes no external requests.

## Tracking

Log an application in one line (`link, company, job title, date`) and record each stage it
reaches: screen, webinar, online assessment, interviews, offer. Each stage has the date you
received it and the date you took it. Applications are **active**, **pending** (no movement
for 7+ days) or **scheduled**, and rejections take multi-select reasons, including your own.

## Analytics

Charts show where every application is right now, how long you've been waiting, the time
spent at each stage, how your online assessments go, why you were rejected, which skills
keep coming up as missing, and your pass rate at each stage.

## Privacy

Nothing leaves your machine. `.gitignore` and a pre-commit hook keep databases, exports,
backups, spreadsheets and `.env` files out of git.

## Import and export

Back up and restore as JSON, exchange data with spreadsheets as CSV, or import the
"Applied" sheet of an existing tracker workbook (`make import XLSX=path/to/file.xlsx`).

## Install and run

Requires Python 3.11+ and Node 18+.

```bash
git clone https://github.com/Yzq77/applytrail.git
cd applytrail
make setup   # install dependencies and the privacy pre-commit hook
make run     # open http://127.0.0.1:8000
```

| Command | What it does |
|---|---|
| `make demo` | Run with fictional demo data (your own data isn't touched) |
| `make dev` | Development mode with hot reload, at http://127.0.0.1:5173 |
| `make test` | Backend tests and frontend type-check |
| `make import XLSX=file.xlsx DRY=1` | Preview importing a workbook; drop `DRY=1` to import |

Without `make` (e.g. on Windows): create a virtualenv in `backend/` and
`pip install -r requirements-dev.txt`; then in `frontend/` run `npm install && npm run build`;
then from `backend/` run `uvicorn app.main:app --host 127.0.0.1 --port 8000`.

## License

MIT
