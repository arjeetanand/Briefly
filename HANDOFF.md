# Migration handoff

## Retained project

- Local project: `/Users/arjeetanand/projects/briefly-voice`
- GitHub origin: `https://github.com/arjeetanand/Briefly.git`
- Migration branch: `codex/migrate-briefly-voice`
- Base commit: `43a7f626e96e90c152c37b880394a3b5a3129373`
- Migration commit: `9f9c5faab339b03aafee48b8bf48f4ec84ec3f1e`
- Published branch: `main` (verified against GitHub with `git ls-remote`)

The OneDrive copy's Git metadata had no commit. Its 81 staged file entries all
matched the base commit's Git blob IDs. The intact local clone at
`/Users/arjeetanand/projects/pitchDeck` supplied the reachable history; it is
outside the requested cleanup scope and remains untouched.

## Changes and preserved data

- Added executable `run.sh`, which starts or safely restarts only this project.
- Set the local launcher and README examples to port 4002; `run-dev.sh` retains
  port 8501. Port 4001 belongs to another project and was left running.
- Added `.briefly-voice/` to `.gitignore` for launcher PID and log files.
- Increased the E2E test's browser startup and synthetic interruption waits.
- Rebuilt `.venv` with Python 3.12.13 and the existing Kokoro requirements.
- Preserved `.env`, the pre-Finder `.DS_Store` snapshot, `.codex-finalizer/`,
  `.deck-build/`, and three `docs/audit/` screenshots outside Git. Checksums
  matched at copy time; `.DS_Store` matches its staging snapshot because Finder
  later updated the OneDrive copy while it was being inspected. The migrated
  presentation deck also matches its committed Git blob. No project database
  or resume files were found.
- Searched project files for old OneDrive and `pitchDeck` absolute paths; none
  remain in the migrated project.

## Verification

- 81 committed blobs and modes match the migration base commit.
- Backend: 72 passed. Cloudflare worker: 4 passed. Motion: 4 passed.
- The automated browser E2E passed 1/1 after increasing its startup wait. A
  final repeat could not launch the local Chrome process (`SIGABRT`); Launch
  Services also returned `kLSNoExecutableErr`. The embedded-browser smoke test
  loaded the app at `http://127.0.0.1:4002/`, answered “What is blocking the
  launch?” from `weekly-project-update.pptx · Slide 4`, showed its excerpt, and
  reported no console warnings or errors.
- `run.sh` start, restart, health response, and refusal to stop the unrelated
  port-4001 listener were verified. `bash -n`, JavaScript syntax checks, and
  `git diff --check` passed.

## Launch

Run `./run.sh`; the app stays at `http://127.0.0.1:4002/`. The paired test
ports are 5002 and 6002. The running server uses the local project directory.

## Finalization status

- The migration commit was pushed to `main` with a normal fast-forward, and the
  remote hash was verified. The checkout is clean and tracks `origin/main`.
- The staging copy is confirmed in
  `/Users/arjeetanand/.Trash/briefly-voice-migration-stage-20261022`.
- The OneDrive source remains at
  `/Users/arjeetanand/Library/CloudStorage/OneDrive-OracleCorporation/projects/pitchDeck`.
  macOS `trash -v -s` waited more than two minutes without moving it; the helper
  was stopped after confirming the original folder still existed. No permanent
  deletion was attempted. Retry **Move to Trash** in Finder once OneDrive's
  File Provider responds.
- Codex's saved project entry `briefly` still points to the OneDrive folder.
  The available project-list API cannot edit its path. In Codex, remove or
  repoint that saved entry and add `/Users/arjeetanand/projects/briefly-voice`
  as the local project.
- The separate local clone at `/Users/arjeetanand/projects/pitchDeck` remains
  untouched because it is outside the authorized source path.
