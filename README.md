# iffable

**A model-aware orchestration guard for [Claude Code](https://claude.com/claude-code) that arms _only_ on Fable-started sessions — and stays completely dormant on Opus/Sonnet.**

If your plan caps the top-tier model at a slice of your weekly quota (Fable 5 draws from ~50% of the limit and drains faster than Opus), the expensive mistake is letting the chair model quietly do bulk work itself. `iffable` makes that mechanically hard: on a Fable session it injects a delegation-first tier policy at startup and **blocks large, un-planned subagent spawns until you've written a Requirements Ledger**. Start the same session on Opus or Sonnet and none of it fires.

Zero custom logic to trust — the enforcement is four small hook scripts (redistributed unmodified from [`Rylaa/fable5-orchestrator`](https://github.com/Rylaa/fable5-orchestrator), MIT) wired together with a model-tier profile and one "fable-only" env switch.

---

## The problem

You are the orchestrator. Your model is the scarce, top-tier one. The failure mode isn't bad code — it's that under time pressure the chair model burns its own capped quota doing grep-and-format work a cheaper model should do, and loses requirement details in the un-written jump from "task" to "plan."

`iffable` attacks both:

- **Quota** — a startup-injected policy routes bulk work to `claude-opus-4-8` (heavy reasoning) and `claude-sonnet-4-6` (mechanical), Haiku banned.
- **Detail loss** — a hook refuses detailed delegations until a numbered Requirements Ledger exists on disk, and a second hook refuses to end the turn while any ledger item is still open.

Both are **off** unless the session started on Fable, so they never tax your cheaper day-to-day sessions.

---

## What it does — three hooks

| Lifecycle event | Script | Effect |
|---|---|---|
| **SessionStart** | `inject_instructions.py` | Detects the session's model, resolves a profile (`fable` / `opus`), and injects the matching instruction file as context. Caches the profile per-session. |
| **PreToolUse** (`Agent\|Task\|Workflow`) | `ledger_guard_spawn.py` | If a spawn prompt / Workflow script exceeds the profile threshold **and** no `.workflow/LEDGER.md` exists from cwd up to the repo root → **deny** with a message telling you to write the ledger first. Forks are exempt. |
| **Stop** | `ledger_guard_stop.py` | If a `.workflow/LEDGER.md` exists with any open `- [ ]` item → **block** turn end. No ledger → no-op. |
| **SessionEnd** | `cleanup_session_cache.py` | Removes the per-session profile cache. |

`Bash` is not matched — `codex`, `git`, and shell-driven tooling pass freely even on Fable. The guard only gates the `Agent` / `Task` / `Workflow` delegation tools.

---

## The "fable-only" switch

Profile resolution order (in `ledger_guard_spawn.py` / `inject_instructions.py`):

1. `FABLE_ORCH_PROFILE` env override (`fable` | `opus`)
2. `model` string in the hook payload
3. per-session cache (written at SessionStart)
4. default: `opus`

The trick is in `settings.example.json`:

```json
"env": {
  "FABLE_ORCH_PROFILE": "auto",
  "LEDGER_GUARD_THRESHOLD_FABLE": "1500",
  "LEDGER_GUARD_THRESHOLD_OPUS": "100000000"
}
```

`auto` lets the **startup model** decide the profile. Fable sessions get the strict `1500`-char gate. Non-Fable sessions get an effectively-infinite gate, so the guard can never fire. One session-scoped flag, no code change, full dormancy off Fable.

> **Caveat that matters:** enforcement keys off the **startup** model, cached at SessionStart. A mid-session `/model` switch does **not** re-fire SessionStart, so the guard stays locked to whatever model the session launched with. To get enforcement, launch on Fable:
>
> ```bash
> claude --model claude-fable-5
> ```

---

## The tier policy it encodes

The injected `instructions/dynamic-workflow-fable.md` tells the chair:

- **Fable 5 (you, the chair)** → judgment-density work only: debugging loops, architecture tradeoffs, final synthesis — anything you "need to see it to know."
- **`claude-opus-4-8` (`max` effort)** → heavy reasoning that can be fully specified upfront.
- **`claude-sonnet-4-6`** → zero-judgment mechanical work only (grep, fetch, format, rename, boilerplate).
- **Haiku → banned.**

One decision rule gates every delegation:

> **"Can I write the complete requirements for this task in `.workflow/LEDGER.md` within 5 minutes?"**
> Yes → delegate. "Need to see it to know" → do it yourself.

Plus a quota-fallback line: at ~50% of the Fable weekly limit, switch the chair to `claude-opus-4-8` and tell the user in one line. A leaner `dynamic-workflow-opus.md` profile carries the same tier policy for fallback sessions.

---

## Install

```bash
git clone https://github.com/openwong2kim/iffable.git
cd iffable
./install.sh          # copies scripts + instructions into ~/.claude/orchestrator/
```

Then **merge** `settings.example.json` into your `~/.claude/settings.json` (or `settings.local.json`) — the installer prints the path and does not edit your settings for you. Keeping the hooks/env in `settings.local.json` sidesteps the Claude Code auto-migration bug ([#22659](https://github.com/anthropics/claude-code/issues/22659)) that can strip `hooks` when you run `/model`.

Start a session on Fable and you're armed:

```bash
claude --model claude-fable-5
```

---

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `FABLE_ORCH_PROFILE` | `auto` | `auto` = decide by startup model. Force with `fable` / `opus`. |
| `LEDGER_GUARD_THRESHOLD_FABLE` | `1500` | Max spawn-prompt / script chars before a ledger is required, on Fable sessions. |
| `LEDGER_GUARD_THRESHOLD_OPUS` | `4000` | Same, for non-Fable sessions. Set very high (e.g. `100000000`) for full "fable-only" dormancy. |
| `LEDGER_GUARD_THRESHOLD` | — | Legacy hard override applied to every profile. |

### The Requirements Ledger

`.workflow/LEDGER.md`, checkbox format:

```markdown
- [ ] 1. <requirement>          # open
- [x] 2. <requirement>          # done AND verified
- [~] 3. deferred: <reason>     # deferred with user approval
```

The spawn guard searches from the working directory up to the first `.git` boundary, so a ledger at the project root covers sessions running in subdirectories.

---

## Interop note (e.g. gstack and other skill toolkits)

On non-Fable sessions the guard is dormant, so skill toolkits run untouched. On a **Fable** session the only friction point is a skill that fans out `Agent`/`Task`/`Workflow` spawns with large prompts and no ledger in the tree — write a short ledger, or run heavy skills on an Opus session. Bash-driven tooling is never affected. Housekeeping: close out ledger items (`[x]` / `[~]`) when done, or a leftover open ledger will keep the Stop guard active in that project tree.

---

## Credits

The enforcement mechanism — the four hook scripts in `scripts/` — is the work of **Yusuf Demirkoparan**, redistributed **unmodified** under MIT from [`Rylaa/fable5-orchestrator`](https://github.com/Rylaa/fable5-orchestrator). `iffable` contributes the model-tier instruction profiles, the fable-only activation wiring, and the docs. If you want the full upstream plugin (tests, plugin manifest, hooks packaging), go there.

## License

- `iffable`'s original files (instructions, wiring, installer, docs) — **Apache-2.0** (`LICENSE`).
- Bundled `scripts/` — **MIT**, © 2026 Yusuf Demirkoparan (`scripts/LICENSE`).

See `NOTICE` for the attribution split.
