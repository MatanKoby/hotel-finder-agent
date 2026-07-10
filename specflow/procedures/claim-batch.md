<!-- specflow:start - managed by specflow; do not edit inside these markers (your edits block specflow upgrade). Add your own notes outside them. -->
# Procedure: claim a batch from `BUILD_QUEUE.md`

Run this before starting any new batch. `AGENTS.md` carries only the pointer to this file.

> **Commit & push follow the configured levers** (`config.commit` / `config.push` in
> `specflow/config.json`; see `AGENTS.md` → *Commit & push authority*). Wherever a step below says
> "commit" or "push": if `commit: user`, don't commit — alert the user and hand them the suggested
> message; if `push: user`, commit but don't push. Default is `agent` / `agent`.

## Pre-flight

1. `git pull --ff-only` on the shared working branch — if it fails, resolve before claiming.

## Eligibility

2. Pick a candidate batch in `BUILD_QUEUE.md` (under "Un-done batches"):
   - **Skip** if it has an exclusionary tag: `[MANUAL]`, `[NOT READY]`, or any tag you don't recognize.
   - **Skip** if it's already listed in `CLAIMS.md` `## In progress` or `## Completed`.

3. **Dependency check.** If the batch lists `Depends on: Batch X[, Batch Y]`, verify each
   listed batch appears in `CLAIMS.md` `## Completed` (or `specflow/history/CLAIMS_DONE.md`). If any are
   missing, pick a different candidate.

4. **Parallelism check.** If any batch is currently `## In progress`, compare your candidate's
   "Files this batch creates/edits" against that batch's same field. If they overlap, pick a
   different candidate or wait.

## Claim

5. Edit `CLAIMS.md`. Add an entry to the **top** of `## In progress`:

   ```
   ### Batch N — <title>
   - Owner: <your agent name>
   - Started: YYYY-MM-DD HH:MM
   ```

   Use UTC for the timestamp (the convention every entry uses).

6. Commit `meta: claim batch-N (<agent>)` and push to the shared branch.

## Push-race recovery (rejected push on the claim commit)

If `git push` is rejected as non-fast-forward, another agent committed first. Recover
**without force-pushing**:

1. `git fetch` the shared branch.
2. `git reset --hard <remote>/<branch>` — drops your local claim commit. Safe because the only
   change was `CLAIMS.md`.
3. Re-read `CLAIMS.md`:
   - If your target batch is now `## In progress`, someone else has it — pick a different
     claimable batch and start over.
   - If your target is still unclaimed (they raced for a *different* batch), re-run this whole
     procedure from step 1 with the same target.

For a rejected push on a *work* commit (`batch-N: ...`), **don't reset** — `git pull --rebase`,
resolve conflicts, push again. **Never** `git push --force` on the shared branch.

## Mid-batch handoff (rare)

If you must stop before finishing:

1. Edit the batch's `## In progress` entry: change `Owner:` to `none`, add a `Handoff note:`
   line (what's done, what's left, files touched, gotchas).
2. Commit `meta: handoff batch-N` and push.

The next agent runs this same claim procedure but only updates `Owner:` (the original
`Started:` timestamp stays).

## Stale-claim recovery

If a batch has been `## In progress` with no new commits for >24h and you want to take over:

1. Update `Owner:` in the existing entry; add a `Reclaim note:` explaining why.
2. Commit `meta: reclaim batch-N from <prior owner>` and push.

Use sparingly — prefer to wait or ask the user.

## Doing the work

After step 6 you're the owner. Commit incrementally with `batch-N: <imperative>` messages and
push at sensible checkpoints. On any rejected push during work commits, `git pull --rebase`,
never force. When finishing, follow `finish-batch.md`.
<!-- specflow:end -->
