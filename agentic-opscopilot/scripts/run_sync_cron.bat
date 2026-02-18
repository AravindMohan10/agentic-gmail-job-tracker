@echo off
REM Run the sync from Windows Task Scheduler.
REM Update the path below to your actual project directory.

set PROJECT_ROOT=C:\path\to\agentic-opscopilot
cd /d "%PROJECT_ROOT%"

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Load .env if present (Windows batch doesn't have set -a, so we'll read it manually)
REM Note: For simplicity, ensure GEMINI_API_KEY is set in system environment or Task Scheduler
REM Alternatively, you can manually set vars here:
REM set GEMINI_API_KEY=your_key_here

REM Run sync and append to log
python -m app.run_sync >> sync_run.log 2>&1
