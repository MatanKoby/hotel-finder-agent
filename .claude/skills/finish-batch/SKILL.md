---
name: finish-batch
description: Use when wrapping up a claimed batch — final commit and SHA capture, move the CLAIMS.md entry to Completed, move the batch out of BUILD_QUEUE.md into specflow/history/BUILD_QUEUE_DONE.md, and the `meta: complete` commit.
---

# Finish a batch

Follow **`specflow/procedures/finish-batch.md`** in this repo — that file is the authoritative,
up-to-date procedure (kept in sync by `specflow upgrade`; this skill is a thin trigger).

In short: final work commit + capture its SHA → move the `CLAIMS.md` entry to `## Completed` with
Finished/Commit + a "What shipped" summary → delete the batch from `BUILD_QUEUE.md` and summarize
it in `specflow/history/BUILD_QUEUE_DONE.md` → commit `meta: complete batch-N` and push.
