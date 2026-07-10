---
name: claim-batch
description: Use when claiming a batch from BUILD_QUEUE.md — eligibility, dependency, and parallelism checks, the CLAIMS.md entry, the `meta: claim` commit, push-race recovery, and handoff/reclaim flows. Invoke before starting any new batch.
---

# Claim a batch

Follow **`specflow/procedures/claim-batch.md`** in this repo — that file is the authoritative,
up-to-date procedure (it is kept in sync by `specflow upgrade`; this skill is a thin trigger so
the steps live in exactly one place).

In short: `git pull --ff-only` → pick an eligible, dependency-satisfied, non-overlapping batch →
add a `## In progress` entry to `CLAIMS.md` → commit `meta: claim batch-N (claude)` and push →
recover from any push race with fetch+reset (claim commit) **without force-pushing**. Then do the
work with `batch-N:` commits, and invoke `finish-batch` when done.
