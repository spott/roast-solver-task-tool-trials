# Curated run logs

This directory contains the selected public records for all six experiment runs. Its structure mirrors the trial branch names:

```text
logs/
├── baseline/{round-1,round-2}/
├── shadow/{round-1,round-2}/
└── full-projection/{round-1,round-2}/
```

Each run contains:

- `session.jsonl` — the complete persisted Pi session transcript, including model messages, tool calls, tool results, task markers, and usage records.
- `metrics.json` — metrics derived by the experiment harness.
- `completed.json` — final harness status and timestamps.
- `final-response.md` — the agent's final user-facing response.

`MANIFEST.sha256` records SHA-256 hashes for all copied source artifacts. Verify it from the repository root with:

```sh
sha256sum --check logs/MANIFEST.sha256
```

These are exact copies of the captured artifacts; they were not normalized or redacted. Before publication, all 24 files were scanned for common private-key, GitHub-token, OpenAI-key, AWS-key, bearer-token, and credential-assignment patterns, with no matches. The transcripts do contain non-secret local paths, commands, generated source excerpts, and build output.

Large protocol-level `events.jsonl`, patches, checkpoints, and SQLite/result-index files are intentionally excluded for now. The exact generated source is already available on the corresponding trial branches.
