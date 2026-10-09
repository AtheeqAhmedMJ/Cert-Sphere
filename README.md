# Bulk Certificate Generator

A small FastAPI service. You give it a list of recipients, either as JSON or as a CSV file, it generates a PDF certificate for each one in the background, and you poll the job to see how it's going and download the results.

I kept it deliberately small: FastAPI, SQLAlchemy, ReportLab, SQLite by default. Around 670 lines of app code, no queue broker, no extra infra to run it.

## Setup

Python 3.11+ (built and tested on 3.12, also installs fine on 3.14).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Run

```bash
uvicorn app.main:app
```

Tables are created on startup. Swagger UI is at http://127.0.0.1:8000/docs, and you can upload the CSV straight from there with a file picker.

Config is through env vars, all optional:

| Var | Default | What it does |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./certs.db` | Any SQLAlchemy URL. Postgres works as is (`postgresql+psycopg://...`, install the driver) |
| `STORAGE_DIR` | `./storage` | Where the PDFs are written |
| `MAX_RECIPIENTS` | `10000` | Cap per request / CSV |
| `MAX_CSV_MB` | `10` | Cap on the uploaded file size |
| `BATCH_SIZE` | `100` | Certificates processed per DB commit |

Run it as a single process (no `--workers N`), more on why below.

**Upgrading from an older copy:** the schema changed (certificate details now live on each certificate row so a CSV can have different values per row). There are no migrations, so delete `certs.db` and the `storage/` folder once and restart.

## Tests

```bash
pytest
```

36 tests, a couple of seconds. They use a throwaway SQLite file and temp storage, so nothing touches your real data. Covered: job creation, request and per-row validation, PDF content (I extract the text and check it), logo drawn only when given, progress, one certificate failing mid-job, CSV parsing and error cases, logo fetching and its safety checks, listing/pagination, downloads, zip, 404s, and resuming unfinished jobs.

## Using it

There are two ways in. Both create the same kind of job and share everything after that (status, failures, downloads).

### A. Upload a CSV

```bash
curl -X POST localhost:8000/jobs/csv -F "file=@samples/certificates.csv"
```

Columns:

| Column | Required | Notes |
|---|---|---|
| Name Of Person | yes | up to 80 chars |
| The Competition | yes | up to 100 chars |
| Category | yes | `Winner`, `Place` or `Participation` (any casing) |
| Final Issued Date | yes | `YYYY-MM-DD` or `DD/MM/YYYY` |
| Issuer | yes | up to 100 chars |
| Logo | no | an `https://` image URL or a `data:image/...;base64,...` value. Leave empty for no logo |

Header names are matched loosely, so `Name Of Person`, `name`, `Category (Winner/Place/Participation)`, `Date`, `Issued By` and so on all work. Save as UTF-8 (Excel's "CSV UTF-8" is fine). Blank lines are skipped. A data URI contains a comma, so that cell has to be quoted, which every spreadsheet app does automatically on export. There's a working file in `samples/` (plus the `logo.png` it uses).

The certificate wording follows the category:

| Category | Title | Line above the competition |
|---|---|---|
| Winner | Certificate of Achievement | in recognition of outstanding performance as the winner of |
| Place | Certificate of Merit | in recognition of securing a place in |
| Participation | Certificate of Participation | in recognition of participating in |

These live in `TITLES` and `LEAD` at the top of `app/pdf.py` if you want different wording.

**Logo.** It sits top centre, scaled to fit a 160x50 pt box with its aspect ratio kept. No logo means the page is exactly the original template. PNG and JPG are the safe choices (transparent PNGs work). To turn a local file into a data URI:

```bash
python -c "import base64,sys; print('data:image/png;base64,'+base64.b64encode(open(sys.argv[1],'rb').read()).decode())" samples/logo.png
```

### B. Send JSON

```bash
curl -X POST localhost:8000/jobs -H "Content-Type: application/json" -d '{
  "title": "Certificate of Completion",
  "event_name": "Python Bootcamp 2026",
  "issuer": "Acme Academy",
  "issued_on": "2026-10-01",
  "recipients": [
    {"name": "Asha Rao", "email": "asha@acme.in"},
    {"name": "Ravi Kumar", "email": "ravi@acme.in"},
    {"name": "Broken Row"}
  ]
}'
```

`title` and `issued_on` are optional (defaults: "Certificate of Completion" and today). This is the original template and wording.

Either way you get `202 Accepted` with a `Location: /jobs/{id}` header.

### Check progress

```bash
curl localhost:8000/jobs/{job_id}
```

```json
{
  "id": "9f1c...",
  "status": "completed_with_errors",
  "total": 5, "succeeded": 4, "failed": 1, "pending": 0,
  "progress": 1.0,
  "created_at": "...", "finished_at": "..."
}
```

Status goes `pending` -> `processing` -> one of `completed`, `completed_with_errors` (some failed), or `failed` (nothing succeeded).

### See what failed (and why)

```bash
curl "localhost:8000/jobs/{job_id}/certificates?status=failed"
```

Each row has its `position` (0-based, counting data rows only, so the header and blank lines don't count) and an `error` such as `category: Input should be 'winner', 'place' or 'participation'`. Filters: `status=pending|success|failed`, plus `limit` (max 500) and `offset`.

### Get the certificates

```bash
curl -O -J localhost:8000/certificates/{certificate_id}/file
curl -O -J localhost:8000/jobs/{job_id}/archive
```

The first is one PDF (every successful row in the listing carries a `download_url`). The second is a zip of every successful certificate in the job, and returns `409` while the job is still running.

## Design decisions

**Background processing, not synchronous.** A request can carry thousands of recipients. Doing that inline means long-held HTTP connections, client and proxy timeouts, and a retry that can duplicate everything. So the submit endpoints validate, persist and return `202`; a FastAPI `BackgroundTask` does the work and the client polls. I measured about 5,000 certificates in 6-7 seconds on a laptop, so even the worst case is short, but the API shape shouldn't depend on that.

**Why not Celery/RQ.** For this scope it'd be a broker, a worker process and a deploy story, to solve a problem a thread handles fine. The seam is clean though: `process_job(job_id)` takes only an id and is idempotent, so swapping the `add_task` call for `queue.enqueue` is a one-line change.

**The database is the source of truth, so restarts are safe.** Every recipient is a row in `certificates` with its own status. The worker only picks up `pending` rows and commits in batches, so a crash loses at most one batch, and on startup the app re-runs any job still `pending` or `processing`. Finished rows are skipped, nothing is generated twice. This is also why you should run one process: two workers would both resume the same job. Going multi-worker means claiming rows with `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres), which is the first thing I'd add.

**One row = everything needed to render it.** Name, title, competition, category, issuer, date and logo are stored on the certificate row, not on the job. The JSON endpoint just copies its job-level values onto every row. That's what lets a single CSV mix competitions, issuers and dates, and it means the worker has exactly one code path.

**Bad rows don't fail the request.** Structural problems (empty list, missing column, wrong encoding, over the row cap, file too big) get a `4xx` because nothing useful can happen. A bad individual row (blank name, unknown category, unparseable date, bad logo reference, duplicate email in JSON mode) is stored as a `failed` row with a readable reason and everyone else carries on. That's what an organiser actually wants: 998 out of 1000 done, plus a list of the 2 to fix.

**Failure isolation at generation time.** Each certificate is rendered inside its own `try/except`. One failure marks that row `failed` with the error and the loop continues.

**Logos are fetched in the worker, once per unique reference per job.** A 1,000 row CSV with the same logo URL does one download, not 1,000. A failed fetch is cached too, so a dead URL costs one 5-second timeout, not 1,000. A logo that can't be loaded fails only the rows that asked for it. I chose that over silently issuing a certificate without the logo the sender wanted.

**Logo URLs are a server-side request, so they're locked down.** Only http(s) to public addresses (localhost, private ranges and cloud metadata addresses are refused), redirects are not followed, 5 second timeout, 2 MB cap. Practical consequence: a logo on `http://localhost:8000` will be refused by design, use a data URI for local testing. Known gap: DNS rebinding between the check and the fetch isn't covered; for production I'd pin the resolved IP or fetch through an egress proxy.

**Progress is computed, not stored.** Counts come from a `GROUP BY status` on an indexed `(job_id, status, position)`. I avoided counters on the job row because a counter updated separately from the thing it counts eventually drifts.

**Rendering.** ReportLab canvas, one landscape A4 template in `app/pdf.py`. Long names shrink to fit instead of overflowing. Each certificate prints its own ID at the bottom, which is the hook for a verification endpoint later.

**Storage.** PDFs go to `STORAGE_DIR/{job_id}/{certificate_id}.pdf`, the DB keeps the path. The zip uses `ZIP_STORED` because PDFs are already compressed, so deflate would just burn CPU.

**SQLite by default** so a reviewer can run it with zero setup, with WAL mode on so polling reads don't block the worker's writes. Nothing is SQLite-specific, point `DATABASE_URL` at Postgres and it works.

## Known limitations

- Fonts are the built-in Helvetica, so names outside Latin-1 (Devanagari, CJK, etc.) won't render properly. Fix is registering a Unicode TTF font in `pdf.py`.
- "Place" is wording only (no 1st/2nd/3rd). If you need ranks, add an optional column and use it in `LEAD`.
- A data URI logo is stored on every row that uses it. Fine for small logos, but for big jobs a URL keeps the DB smaller.
- The archive endpoint builds the zip in memory. Fine at the 10k cap (about 20 MB), but I'd stream it for bigger jobs.
- No auth, no idempotency key, and no duplicate detection for CSV rows. Uploading the same file twice creates two jobs.
- Files are on local disk. For more than one box this needs S3 or similar.
- Migrations: tables come from `create_all`. I'd bring in Alembic before the schema changes for real.

## Layout

```
app/
  main.py        routes, request handling, startup resume
  csv_import.py  CSV parsing, header matching, row validation
  worker.py      process_job: the generation loop and final status
  pdf.py         the certificate template and category wording
  logo.py        safe logo loading (URL or data URI)
  db.py          engine, models, status counts
  schemas.py     request/response models
  config.py      env config
samples/         example CSV and logo
tests/
```
