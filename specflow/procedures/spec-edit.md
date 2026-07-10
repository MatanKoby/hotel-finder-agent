<!-- specflow:start - managed by specflow; do not edit inside these markers (your edits block specflow upgrade). Add your own notes outside them. -->
# Procedure: edit the spec (or persist a design decision)

Run this before editing any file under `spec/**`, or when persisting a design decision the
user just made. `AGENTS.md` carries only the pointer to this file.

## Decide where to write — concern-matching

The spec lives in `spec/`, organized into concern-focused files (and sub-folders as it grows).
Open the relevant index **first** — don't read the whole spec:

- Start at `spec/README.md` for the file map.
- When a sub-folder has its own `README.md`, open that before reading individual files in it.

Pick the **single** file whose concern matches the change. If the change naturally crosses
multiple files, that's a signal the concern might be miscarved — **flag it to the user before
duplicating content.** Don't just write to both files.

## Cross-reference, don't restate

When file A needs a concept that lives in file B, link by **file path** — e.g.
`see schema.md → Tables` or `see signals/zone.md`. Don't restate the concept; restating creates
a second source of truth that will drift.

## Move stale content to `archive.md`

The spec describes the **current intended design**, not the history. When a section stops
reflecting live code — an abandoned approach, a removed table, a deprecated flow — move it to
`spec/archive.md` rather than leaving it inline. `archive.md` is the institutional memory;
everything else is current.

## Size watch

When a file heads past ~600 lines (~20k tokens), consider whether the next bite of content
wants its own file. A per-folder `README.md` is the index pattern — when a sub-concern grows
enough to warrant a file, add it and update the README in the same commit.

## Persisting a design decision the user just made

A decision lives in two places: the **spec** (durable design) and the **queue** (work that
flows from it). The transcript is not durable — if you don't write it down, a future agent will
re-litigate it or silently contradict it.

**Decision made *with* the user (working session):**

1. Update the relevant `spec/` file(s) to reflect the new design, with a `spec:` commit.
2. Update `BUILD_QUEUE.md`: revise the relevant in-flight batch, or add new batches that flow
   from the decision, with a `meta:` commit. **Never** put claim state (Owner / Started /
   Finished) into `BUILD_QUEUE.md` — that lives in `CLAIMS.md` only. The queue holds *design
   intent*; the claims file holds *execution state*.
3. Then proceed to implementation.

**Decision encountered mid-execution (no user input yet):**

Do **not** quietly make and persist the decision. Instead:

1. Surface it to the user — describe the choice and the tradeoffs.
2. Wait for their call.
3. Once decided, follow the working-session flow above.

Scope: this applies to **design/spec** — architecture, data model, public behavior, batch
scope. Day-to-day implementation forks (library choice, internal file naming, refactor shape)
stay agent discretion.

## Commit convention

| Prefix | When |
|---|---|
| `spec: <change>` | Edits to any `spec/**` file |
| `meta: <change>` | Edits to `BUILD_QUEUE.md`, `CLAIMS.md` structure, tooling |
| `batch-N: <change>` | Code/asset changes toward batch N |

A spec edit + a queue revision from the same decision are normally two commits (`spec:` then
`meta:`), but one combined commit is fine when small and unambiguous.
<!-- specflow:end -->
