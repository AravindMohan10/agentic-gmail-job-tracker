# Testing and metrics

Use this as a checklist when validating the sync, running stress tests, and preparing metrics for your portfolio.

---

## Pre-run checks

- [ ] `GEMINI_API_KEY` set (env or `.env`)
- [ ] `credentials.json` in project root (or `GMAIL_CREDENTIALS_FILE` set)
- [ ] Gmail API enabled in Google Cloud project
- [ ] Test user added on OAuth consent screen
- [ ] First run only: browser OAuth completes and `token.json` is created

---

## Run and observe

1. **First-ever sync**
   ```bash
   python -m app.run_sync
   ```
   - Expect: browser opens once for OAuth (if no `token.json`).
   - Expect: run takes several minutes if many candidates (12s throttle per Gemini call).
   - Expect: `applications.xlsx` created; `applications.db` created.

2. **Second run (idempotent)**
   ```bash
   python -m app.run_sync
   ```
   - Expect: no browser; `skipped_already_seen` > 0; `records_extracted` small or 0; run faster.

3. **With run logging**
   - Set `SYNC_LOG_PATH=sync_run.log` in `.env` (or export), run sync twice.
   - Expect: `sync_run.log` has two lines (ts, duration_ms, messages_seen, skipped, records_extracted, status).

---

## Metrics to show

Capture these for demos or reports:

| Metric | How to get it |
|--------|----------------|
| **Runs per day** | Count lines in `sync_run.log` per day (if `SYNC_LOG_PATH` set). |
| **Success rate** | Fraction of log lines with `status=success`. |
| **Records extracted per run** | `records_extracted` from stdout or from log line. |
| **Latency per run** | `duration_ms` from stdout or log. |
| **Throughput** | Total `records_extracted` over N runs or over a week (from log). |
| **Idempotency** | After two runs, `skipped_already_seen` on second run ≈ messages already in DB. |

Example log line to parse:

```text
ts=2025-02-15T12:00:00+00:00 duration_ms=120000 messages_seen=50 skipped=45 records_extracted=3 status=success
```

---

## Optional: automated test script

You can add a small script (e.g. `scripts/test_sync_metrics.py`) that:

1. Runs `run_sync()` once (or twice).
2. Reads `sync_run.log` and parses the last line(s).
3. Asserts `status=success`, `records_extracted` >= 0, `duration_ms` > 0.
4. Prints a one-line summary (e.g. "PASS: 2 runs, 5 records, 45s total").

See **README → Testing and metrics** for manual checks and log format.

---

## Stress test scenarios

Run these and record results for portfolio or demo.

| Scenario | What to do | What to record |
|----------|------------|----------------|
| **Cold start (first sync)** | Empty DB, run once with `SYNC_LOG_PATH=sync_run.log` | `duration_ms`, `messages_seen`, `records_extracted`, success/fail |
| **Idempotent (second run)** | Run again immediately | `skipped_already_seen` ↑, `records_extracted` low/0, `duration_ms` (faster) |
| **High volume** | Set `SYNC_MAX_EXTRACTIONS_PER_RUN=80`, `SYNC_BATCH_SIZE=10`, run with many candidates | `records_extracted`, `duration_ms`, number of Gemini calls (e.g. 8 for 80) |
| **Status update** | Have at least one application in DB, then run after a new rejection/offer email arrives | Same company row in Excel shows updated status |

### How to run stress tests

1. Set in `.env`: `SYNC_LOG_PATH=sync_run.log`
2. Run `python -m app.run_sync` (or `./scripts/run_sync_cron.sh`) for each scenario
3. Copy stdout and the new line in `sync_run.log` for each run
4. Optionally clear DB (`rm applications.db`) and `processed_messages` for a clean cold start

---

## Metrics results (fill after stress test)

Add your numbers here or in a separate `METRICS.md` for your portfolio.

| Metric | Value | Notes |
|--------|-------|--------|
| Success rate | _e.g. 100% (N/N runs)_ | From `sync_run.log` |
| Cold start latency | _e.g. 45s_ | First run, empty DB |
| Idempotent run latency | _e.g. 8s_ | Second run, no new mail |
| Records per run (typical) | _e.g. 5–15_ | From stdout or log |
| Max batch size tested | _e.g. 10 emails/call_ | `SYNC_BATCH_SIZE` |
| Environment | _e.g. Python 3.10, macOS, Gemini free tier_ | For reproducibility |
