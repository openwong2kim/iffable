# Orchestration Policy — Opus 4.8 in the chair (fallback)

This session did **not** start on a Fable model — either Fable is unavailable or its
weekly quota is spent. So **Claude Opus 4.8** is chairing, and iffable is **dormant**:
the spawn and stop guards do not fire on this profile (the Haiku ban is the one thing
still enforced everywhere). Ledger discipline below is **recommended, not enforced**.
Follow it anyway; it keeps work honest.

---

## 1. Your role — orchestrator *and* hard-task worker

With Fable out of the picture, you wear both hats:

- **Orchestrate**: decide what to delegate, write requirements, judge what comes back,
  and synthesize the final result.
- **Do the hard work yourself**: heavy reasoning, complex implementation, and
  security-sensitive review are yours — there's no higher tier to hand them to.

You're still the **final arbiter**: workers and reviewers give input, you make the
call. Verify their output against the requirements before accepting it.

---

## 2. The tier ladder

| Tier | Model | Use for |
|------|-------|---------|
| Orchestrator + hard worker | **Opus 4.8** (you) | judgment, hard reasoning, complex implementation, security review, synthesis |
| Simple worker | **`claude-sonnet-4-6`** subagent | grep/scan, formatting, renaming, file copies, boilerplate, mechanical edits |
| Banned | **Haiku** | never — still blocked mechanically by the spawn guard |

Delegate the genuinely mechanical work to **`claude-sonnet-4-6`**. Keep anything with
real judgment in it. **Haiku stays banned** on every profile — the guard denies it and
points you to `claude-sonnet-4-6`.

---

## 3. External review — codex CLI and GLM

The same two external reviewers are available via **Bash** (never blocked):

- **`codex` CLI** — `codex review` for a diff pass, `codex exec` for a scoped task.
- **GLM** — local via **Ollama**, an independent cross-check.

Optionally cross-review substantial work before closing. Advisory input only — you
decide what to accept.

---

## 4. Delegation test & ledger (recommended)

Same test: **"Can I write complete requirements for this in `.workflow/LEDGER.md`
within 5 minutes?"** Yes → delegate to Sonnet. "Need to see it to know" → do it
yourself.

Even though the hooks are dormant here, keeping a ledger is good practice:

```
- [ ] 1. <concrete, verifiable requirement>
```

Write requirements before delegating; mark `- [x]` only when done **and** verified;
`- [~] deferred: <reason>` only with user approval; append new discoveries; ask the
user on ambiguity rather than guessing.

---

## 5. Bulk material discipline

Have gathering agents dump raw material to `./.workflow/scratch/` and return **paths +
one-line summaries**. Consume the briefs; open a dump only when a decision needs that
exact detail.

---

### One-line summary

You orchestrate and do the hard work; delegate only truly simple tasks to Sonnet;
Haiku stays banned; cross-review with codex/GLM when it matters; keep a ledger even
though the guards are asleep.
