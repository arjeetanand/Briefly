# Briefly Voice migration checklist

- [x] Inspect both folders and preserve the OneDrive files; all 81 source-index blob IDs match the verified project commit.
- [x] Preserve the 10-commit Git history and `arjeetanand/Briefly` origin from the intact local clone.
- [x] Copy private and ignored project data outside Git, including `.env`, `.DS_Store`, `.codex-finalizer/`, `.deck-build/`, and audit screenshots.
- [x] Rebuild the Python 3.12 environment at the local path; scan found no project databases or resumes.
- [x] Verify 81 committed file blobs and checksums for `.env`, the preserved `.DS_Store` snapshot, and all three audit screenshots.
- [x] Run backend (72 passed), Cloudflare (4 passed), motion (4 passed), and browser smoke tests; the full E2E passed once, while a final rerun was blocked by the local Chrome launcher exiting with `SIGABRT`.
- [x] Commit and push to `main` without force; GitHub `main` is `9f9c5faab339b03aafee48b8bf48f4ec84ec3f1e`.
- [x] Move the redundant staging copy to macOS Trash at `~/.Trash/briefly-voice-migration-stage-20261022`.
- [blocked] The OneDrive source remains at its original path. Its recoverable Trash request stalled for over two minutes; the helper was stopped and the source remains intact.
- [blocked] The saved Codex project still points to OneDrive; the available project API is read-only, so re-add `/Users/arjeetanand/projects/briefly-voice` in Codex manually.
