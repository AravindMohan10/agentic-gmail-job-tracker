# Job Applications Sync (OpsCopilot)

**Gmail → one Excel with all your job applications, updated automatically.**


For job seekers and students: sync application emails from Gmail into a single spreadsheet. One-time OAuth, then it runs on a schedule (e.g. every 12 hours). Status updates (rejection, interview, offer) update the same row so you always see the latest. Uses Gemini for extraction; batched for up to ~80 applications/day on free tier.

---

## What it does

1. **Searches Gmail** for application-related messages (query: application, applied, interview, recruiter, etc.).
2. **Extracts** structured records (company, role, status: applied/interview/rejected/offer) using Gemini, with rule-based fallback.
3. **Stores** records in SQLite. One row per application (company + role). When a new email (e.g. rejection) matches an existing company+role, that row is **updated** to the new status—so the Excel shows "Company X → Rejected" instead of a duplicate row.
4. **Exports** all records to an Excel file (e.g. `applications.xlsx`).

**Sync window and API limits**
- **First sync** (empty DB): fetches mail from the **last 7 days**; processes up to `SYNC_MAX_EXTRACTIONS_PER_RUN` (default 80) candidates.
- **Later syncs**: only **today’s** mail. Existing applications are updated when you get a rejection/offer (same company+role → same row updated).
- **Batching:** Multiple emails per LLM call (`SYNC_BATCH_SIZE`, default 5). 80 emails = 16 Gemini calls (free-tier friendly). More capacity requires a paid API plan.

---

## Prerequisites

- **Python 3.10+**
- **Google Cloud project** with Gmail API enabled and OAuth consent screen configured
- **Gemini API key** (free tier is enough; sync throttles to stay under 5 req/min)

---

## Setup (for new users)

### 1. Clone and install

```bash
cd agentic-opscopilot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google Cloud (Gmail)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. **APIs & Services → Library** → search **Gmail API** → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User type: **External** (so you can add test users).
   - App name and support email (your email), then complete the wizard.
   - Under **Test users**, add the Gmail address you will use (e.g. your personal Gmail).
4. **APIs & Services → Credentials** → **Create Credentials** → **OAuth client ID**:
   - Application type: **Desktop app**.
   - Download the JSON and save it as **`credentials.json`** in the project root (`agentic-opscopilot/`).
   - Do **not** commit this file (it is in `.gitignore`).

### 3. Gemini API key

1. Go to [Google AI Studio](https://ai.google.dev/) or [Gemini API](https://ai.google.dev/gemini-api/docs).
2. Get an API key for Gemini.
3. Set it in your environment (see **Environment variables** below). Do **not** commit the key.

### 4. Environment variables

Copy the example env file and fill in **only** the required value:

```bash
cp .env.example .env
# Edit .env and set at least:
#   GEMINI_API_KEY=your_key_here
```

Optional: set paths and limits in `.env` (see `.env.example`). Use **absolute paths** for `GMAIL_CREDENTIALS_FILE` and `GMAIL_TOKEN_FILE` if you run from cron.

### 5. First run (OAuth + sync)

Run the sync once. The first time, a browser will open for you to sign in with Google and grant read-only Gmail access. After that, a `token.json` file is saved and future runs are unattended.

Load your env (e.g. from `.env`) then run:

```bash
# Linux/macOS (if you use .env):
set -a && source .env && set +a
python -m app.run_sync

# Or use the cron script (it loads .env):
./scripts/run_sync_cron.sh

# Windows (if you use .env):
# First, activate venv:
.venv\Scripts\activate
# Then set env vars from .env manually or run:
python -m app.run_sync
# The script will read .env automatically if present
```

Check that `applications.xlsx` is created/updated. Keep `credentials.json` and `token.json` in the project root (or paths you set in `.env`); both are in `.gitignore`.

---

## Security (no lapses)

- **Never commit**:
  - `credentials.json` (OAuth client secret)
  - `token.json` (refresh token)
  - `.env` (API keys and paths)
  - `applications.db` (your data)
- **`.gitignore`** already excludes these. **`.env.example`** has no real values—only variable names and placeholders.
- **Gmail scope** is read-only (`gmail.readonly`). The app cannot send or delete mail.
- Store **Gemini API key** only in environment or `.env`; never in code or in the repo.
- If you share the repo, others use their own Google Cloud project, their own `credentials.json` / `token.json`, and their own `.env` with their Gemini key.

---

## Running on a schedule (every 12 hours)

### Option A: Cron + script (Linux/macOS)

Make the script executable and add a cron job:

```bash
chmod +x scripts/run_sync_cron.sh
crontab -e
```

Add a line (adjust path to your clone):

```cron
0 */12 * * * /absolute/path/to/agentic-opscopilot/scripts/run_sync_cron.sh >> /tmp/opscopilot_sync.log 2>&1
```

This runs at 00:00 and 12:00. The script loads `.env` from the project root and runs `python -m app.run_sync`.

### Option B: Cron without script (Linux/macOS)

```cron
0 */12 * * * cd /absolute/path/to/agentic-opscopilot && .venv/bin/python -m app.run_sync >> /tmp/opscopilot_sync.log 2>&1
```

Set `GEMINI_API_KEY` and other vars in your shell profile or in the crontab (e.g. `GEMINI_API_KEY=...` lines before the command).

### Option C: Windows Task Scheduler

1. **Create a batch script** (`scripts/run_sync_cron.bat`):
   ```batch
   @echo off
   cd /d "C:\path\to\agentic-opscopilot"
   call .venv\Scripts\activate.bat
   python -m app.run_sync >> sync_run.log 2>&1
   ```
   Replace `C:\path\to\agentic-opscopilot` with your actual project path.

2. **Open Task Scheduler** (search "Task Scheduler" in Windows Start menu).

3. **Create Basic Task**:
   - Name: `OpsCopilot Job Sync`
   - Trigger: **Daily** → Start time: `00:00` → Recur every: `12 hours`
   - Action: **Start a program**
   - Program/script: `C:\path\to\agentic-opscopilot\scripts\run_sync_cron.bat`
   - Start in: `C:\path\to\agentic-opscopilot`

4. **Advanced settings** (optional):
   - Check **"Run whether user is logged on or not"** (if you want it to run when you're away)
   - Check **"Run with highest privileges"** (if needed for file access)

**Note:** Ensure your `.env` file is in the project root so the script can find it. The batch script will use the virtual environment's Python and run the sync.

### After pulling updates from GitHub

**Important:** If you pull updates that change the sync script or dependencies, you should:

1. **Update dependencies** (if `requirements.txt` changed):
   ```bash
   # Linux/macOS:
   source .venv/bin/activate
   pip install -r requirements.txt

   # Windows:
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Re-run the sync manually once** to verify it works:
   ```bash
   python -m app.run_sync
   ```

3. **Cron/Task Scheduler**: No changes needed—your existing cron job or Windows Task Scheduler entry will continue to work. The scheduled task will automatically use the updated code.

**Note:** If the project structure changes significantly (e.g., script paths), you may need to update your cron entry or Task Scheduler action path.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Gemini API key |
| `APPLICATIONS_DB_PATH` | No | `applications.db` | SQLite database path |
| `SYNC_EXCEL_PATH` | No | `applications.xlsx` | Export path |
| `GMAIL_CREDENTIALS_FILE` | No | `credentials.json` | OAuth client JSON path |
| `GMAIL_TOKEN_FILE` | No | `token.json` | Saved OAuth token path |
| `SYNC_GMAIL_QUERY` | No | (built-in) | Gmail search query |
| `SYNC_GMAIL_AFTER` | No | **last 24 hours** | Only sync mails on/after this date (YYYY/MM/DD). Default = yesterday (to catch previous day evening emails). |
| `SYNC_MAX_MESSAGES` | No | `100` | Max messages to fetch from Gmail per run (1–500) |
| `SYNC_MAX_EXTRACTIONS_PER_RUN` | No | `80` | Max emails to process per run (assume up to 80 applications/day) |
| `SYNC_BATCH_SIZE` | No | `5` | Emails per LLM call (80 emails = 16 calls; 1–20) |
| `GEMINI_THROTTLE_S` | No | `12` | Seconds to wait after each Gemini call (free tier) |
| `SYNC_LOG_PATH` | No | — | If set, append one line per run for metrics |

---

## Testing and metrics

### Run once and check output

```bash
python -m app.run_sync
```

You should see a line like:

```text
Sync done: N records from M messages (skipped K already seen) in Dms → applications.xlsx
```

- **messages_seen**: number of messages returned by Gmail search.
- **skipped_already_seen**: already in DB (idempotent).
- **records_extracted**: new records extracted this run.
- **duration_ms**: total run time (includes Gemini throttle).

### Optional: log each run for metrics

Set in `.env`:

```bash
SYNC_LOG_PATH=sync_run.log
```

Each run appends one line:

```text
ts=2025-02-15T12:00:00+00:00 duration_ms=120000 messages_seen=50 skipped=45 records_extracted=3 status=success
```

On failure, a line with `status=failed` and `error=...` is appended. You can parse `sync_run.log` to compute:

- **Success rate**: fraction of runs with `status=success`
- **Throughput**: `records_extracted` per run (or per day)
- **Latency**: `duration_ms` (p50, p95)
- **Volume**: `messages_seen`, `skipped` over time

Keep `sync_run.log` out of version control (it’s in `.gitignore` as `sync_run.log`).

### Manual checks

- Open `applications.xlsx` and confirm columns: company, role, status, stage, event_date, etc.
- Re-run the sync; `skipped_already_seen` should increase and `records_extracted` drop for the same mailbox (idempotent).
- First run with many candidates may take 15–25 minutes (12s throttle per Gemini call); later runs are faster when most messages are already in DB.

---

## Project layout

```text
app/
  run_sync.py          # Entrypoint: run_sync(), main()
  repository/           # SQLite persistence
  tools/               # Gmail, Gemini, extraction, applications, export_excel
scripts/
  run_sync_cron.sh     # Cron wrapper (loads .env, runs app.run_sync)
.env.example           # Example env (no secrets)
requirements.txt
README.md
```

---


## License

MIT. See [LICENSE](LICENSE). Keep credentials and API keys out of the repo.
