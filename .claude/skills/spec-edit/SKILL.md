---
name: spec-edit
description: Use before editing any file under `spec/**`, or when persisting a design decision the user just made. Covers concern-matching, cross-reference-don't-restate, the archive rule, size-watch, and propagation to BUILD_QUEUE.md.
---

# Edit the spec (or persist a design decision)

Follow **`specflow/procedures/spec-edit.md`** in this repo — that file is the authoritative,
up-to-date procedure (kept in sync by `specflow upgrade`; this skill is a thin trigger).

In short: open the relevant `spec/` index first and write to the **single** file whose concern
matches (flag cross-file changes instead of duplicating) → cross-reference by path, don't restate
→ move stale content to `archive.md`. When persisting a design decision, update `spec/` (`spec:`
commit) **and** `BUILD_QUEUE.md` (`meta:` commit) — never put claim state in the queue. If the
decision surfaced mid-execution, surface it to the user before persisting.
