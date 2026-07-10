<!-- specflow:start - managed by specflow; do not edit inside these markers (your edits block specflow upgrade). Add your own notes outside them. -->
# AGENTS.md — Shared Agent Protocol (specflow)

> **Managed by [specflow](https://github.com/MatanKoby/specflow).** Everything between the
> `specflow:start` / `specflow:end` markers is generated — `specflow upgrade` refreshes that
> region and **only** that region; text outside the markers is preserved. Add repo-specific
> notes *outside* the markers (project identity is better in `README.md` / `CLAUDE.md` / your
> agent's own config). Don't edit *inside* the markers — `upgrade` flags an edited region and
> leaves it untouched rather than clobbering it, so your change blocks future refreshes.

This is the single source of truth for how one or more AI coding agents collaborate on this
repo. **Every agent must read this before starting work.** It applies to *all* agents equally
(Claude Code, Cursor, Copilot, and any other) — agent-specific quirks live in that agent's own
config file, not here.

## The model in one paragraph

Work is **specced** before it is built (`spec/`), broken into **batches** (`BUILD_QUEUE.md`),
and each batch is **claimed** in git before code is written (`CLAIMS.md`) so the record of
"who is doing what / what is done" survives a crashed laptop and lets multiple agents (or
people) work the same branch without colliding. Three procedures — **claim a batch**, **edit
the spec**, **finish a batch** — carry the discipline; their full steps live in
`specflow/procedures/`.

## Repo & branches

- There is one **shared working branch** (default `main` — substitute your team's if different).
  Agents commit directly to it, subject to the **commit/push levers** below. Always
  `git pull --ff-only` before you start work.
- No feature branches in the normal flow. (Teams that prefer PR-per-batch can layer that on;
  the default is direct-commit.)
- **Never** force-push the shared branch. Recover from a rejected push with `git pull --rebase`
  (never force), then re-push. The one exception is a rejected
  **claim** commit, which is resolved with `git fetch` + `reset` — see `claim-batch.md`.

## Commit & push authority

Two independent levers in `specflow/config.json` (`config.commit` / `config.push`) govern what an
agent may do with code it has written. **Read them before any commit or push step** in the
procedures:

- **`commit: agent`** — the agent creates commits itself. **`commit: user`** — the agent does
  **not** commit; on reaching a sensible commit point it **alerts the user and supplies a short
  suggested commit message** (in the convention below), and the user makes the commit.
- **`push: agent`** — the agent pushes after committing. **`push: user`** — the agent commits but
  **never pushes**; the user pushes on their own terms. (Only meaningful when `commit: agent`.)

Where the procedures say "commit … and push," honor these levers: substitute an alert + suggested
message when `commit: user`, and stop before pushing when `push: user`. The default is
`agent` / `agent` — the agent commits and pushes.

## File ownership

| File / path | Owner | Notes |
|---|---|---|
| `spec/**` | user | The design. Agents propose `spec:` edits via the `spec-edit` procedure; don't freelance. |
| `BUILD_QUEUE.md` | user | Declares the work (un-done batches, in full). Agents **never** write claim state here. |
| `specflow/history/BUILD_QUEUE_DONE.md` | shared archive | One-paragraph summaries of completed batches. Append on finish. |
| `CLAIMS.md` | agents | Active claims + recent completions. The execution-state ledger. |
| `specflow/history/CLAIMS_DONE.md` | agents | Older completed entries archived from `CLAIMS.md`. Reference-only. |
| `AGENTS.md`, `specflow/**` | specflow | Generated mechanism. Overwritten on `specflow upgrade`; don't hand-edit. |
| source code, assets | shared | Commit with the grammar below. |

The golden rule: **the queue declares work; the claims file records execution state.** They
never mix. The user can overwrite `BUILD_QUEUE.md` at any time without breaking agent state,
because no Owner / Started / Finished / Status ever lives in it.

## The work queue — `BUILD_QUEUE.md`

Lists only **un-done** batches, in full (completed ones collapse to summaries in
`specflow/history/BUILD_QUEUE_DONE.md`). Eligibility is read from the tag in each batch heading:

- **No tag** — claimable, subject to the dependency check below.
- `[MANUAL]` — the user executes this (e.g. infra provisioning). Agents skip entirely.
- `[NOT READY]` — blocked on external work or undecided design. Don't claim.
- Any tag you don't recognize — treat as exclusionary and ask the user.

A batch may list `Depends on: Batch X[, Batch Y]`. It's only eligible once **every** listed
dependency appears in `CLAIMS.md` `## Completed` (or `specflow/history/CLAIMS_DONE.md`).

Multiple batches run in parallel only when their declared "Files this batch creates/edits"
don't overlap. When they touch the same files, run them sequentially.

## The claims file — `CLAIMS.md`

Two sections: `## In progress` (one entry per active claim) and `## Completed` (recent
finishes, newest first; older history archived to `specflow/history/CLAIMS_DONE.md`). Entry format:

```
### Batch N — <short title>
- Owner: <agent>
- Started: YYYY-MM-DD HH:MM        (UTC)
- Finished: YYYY-MM-DD HH:MM       (only in Completed)
- Commit: <short SHA of the work commit>   (only in Completed)
- Handoff note: ...                 (only when a mid-batch handoff occurred)
```

## The procedures

Detailed steps live in `specflow/procedures/`. **Read the relevant file before acting** —
don't reconstruct it from memory.

- **`specflow/procedures/spec-edit.md`** — before editing any `spec/**` file or persisting a
  design decision: concern-matching, cross-reference-don't-restate, archive rule,
  propagation to `BUILD_QUEUE.md`. **Run before any spec change.**
- **`specflow/procedures/claim-batch.md`** — pull, eligibility + dependency + parallelism
  checks, write the `CLAIMS.md` entry, `meta: claim` commit, push-race recovery, handoff,
  stale-claim reclaim. **Run before starting any new batch.**
- **`specflow/procedures/finish-batch.md`** — final commit + SHA, move the entry to
  `## Completed`, summarize, move the batch out of `BUILD_QUEUE.md` into `specflow/history/BUILD_QUEUE_DONE.md`,
  `meta: complete` commit. **Run when wrapping up.**

> Claude Code users: these procedures are also installed as auto-triggering skills.

## Commit message convention

| Prefix | When to use |
|---|---|
| `batch-N: <imperative>` | Code/asset change toward batch N |
| `meta: claim batch-N (<agent>)` | Claiming a batch |
| `meta: complete batch-N` | Marking a batch done |
| `meta: handoff batch-N` | Mid-batch hand-off (Owner cleared) |
| `meta: reclaim batch-N from <prior owner>` | Stale-claim recovery |
| `spec: <change>` | Edits to any `spec/**` file |
| `meta: <other>` | Tooling / structural changes |

`git log --oneline` is the change log — there is no separate changelog file.

## Editing rules

- Treat `spec/**` as the design — propose edits through the `spec-edit` procedure; don't freelance.
- Treat `BUILD_QUEUE.md` and `spec/**` as user-owned for *execution state* (claim/Owner/
  timestamps live in `CLAIMS.md` only). Design intent may be written to both via `spec-edit`.
- Anyone may add new `CLAIMS.md` entries, but only the current Owner mutates a batch's entry
  (except stale-claim recovery — see `claim-batch.md`).
- Always `git pull --ff-only` before claiming so you don't race another agent.
<!-- specflow:end -->
