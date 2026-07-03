# iffable

A quota-preservation guard for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

iffable arms **only** on sessions that started on a Claude Fable 5 model and stays
dormant otherwise. When armed it injects an orchestration policy at session start and
mechanically blocks three things: Haiku subagent spawns, large un-planned delegations
with no Requirements Ledger, and ending the turn while ledger items are still open.

> **Original implementation.** The hook-based enforcement *mechanism* (a SessionStart
> context injection plus PreToolUse/Stop ledger guards) was **inspired by**
> [Rylaa/fable5-orchestrator](https://github.com/Rylaa/fable5-orchestrator) by Yusuf
> Demirkoparan (MIT). iffable shares **no code** with it — this is a clean-room build
> written from a spec. See [NOTICE](NOTICE).

---

## Why

On the Max ($220) plan, the top-tier model (**Claude Fable 5**) is capped at roughly
**50% of weekly quota**, and it drains fast. The natural failure mode is to sit in
Fable and let it do everything — grepping trees, formatting files, writing
boilerplate — until the cap hits mid-week and you're locked out of your best model.

iffable makes the economical path the default: Fable orchestrates and does only
judgment-dense work; cheaper tiers do the rest. It doesn't nag — it injects the policy
once, then enforces the few rules that actually protect quota.

---

## The three guards

| Guard | Hook event | Fires when | Effect |
|-------|-----------|-----------|--------|
| **Haiku ban** | PreToolUse (`Agent`\|`Task`\|`Workflow`) | spawn `tool_input.model` contains `haiku` — **any profile** | deny; suggests `claude-sonnet-5` |
| **Ledger guard (spawn)** | PreToolUse | **fable profile**: heavy delegation only — spawn model contains `opus` or is unspecified (inherits Fable); explicit light models (e.g. sonnet) are exempt, `Workflow` is always guarded, `fork` exempt — **and** prompt/script > `IFFABLE_SPAWN_LIMIT` chars **and** no `.workflow/LEDGER.md` in the tree | deny; tells you to write the ledger first |
| **Ledger guard (stop)** | Stop | **fable profile**: ledger has any open `- [ ]` line | block turn end; lists the open items |

All hooks **fail open**: malformed input or any internal error exits 0 silently, so a
broken hook can never brick a session.

---

## Fable-only arming (and the startup-model caveat)

iffable resolves a **profile** at session start from the launch model:

- model contains `fable` (case-insensitive) → **`fable`** — guards armed.
- anything else → **`fallback`** — guards dormant (except the Haiku ban, which is
  enforced on every profile).

The profile is written to a per-session cache file and reused by the later hooks
(PreToolUse/Stop payloads carry no model field).

> ⚠️ **Arming is decided by the model the session *started* on.** Switching models
> mid-session with `/model` does **not** re-arm iffable — the SessionStart hook has
> already run. To get an armed session, **launch on Fable**:
>
> ```sh
> claude --model claude-fable-5
> ```

Override the auto behavior at any time with `IFFABLE_PROFILE` (`fable` / `fallback` /
`off`).

---

## The tier policy

When armed, iffable injects `instructions/orchestrator-fable.md`, which encodes:

| Tier | Model | Use for |
|------|-------|---------|
| Orchestrator | **Fable 5** | judgment, debugging loops, tradeoffs, synthesis |
| Hard worker | **`claude-opus-4-8`** (max effort) | heavy reasoning, complex implementation, security review |
| Simple worker | **`claude-sonnet-5`** | grep/scan, formatting, renaming, boilerplate |
| Banned | **Haiku** | never (also enforced by the guard) |

**External review — codex & GLM.** Before closing substantial work, optionally
cross-review via **Bash**: the `codex` CLI (`codex review` / `codex exec`) and **GLM**
(local, via Ollama). Their output is advisory; the orchestrator makes the final call.
These run through Bash and are never blocked by the guards.

**Delegation test:** *"Can I write complete requirements for this in
`.workflow/LEDGER.md` within 5 minutes?"* Yes → delegate per tiers. "Need to see it to
know" → do it yourself.

**Quota fallback:** at ~50% weekly Fable usage, switch the orchestrator to
`claude-opus-4-8` and notify in one line. A session that *starts* on Opus gets the
shorter `orchestrator-fallback.md` policy instead.

---

## Install

```sh
IFFABLE_HOME="$HOME/.claude/iffable" ./install.sh
```

This copies `iffable.py` and `instructions/` into `IFFABLE_HOME`
(default `~/.claude/iffable`). It **prints** — but does not apply — the settings merge
you need; wire the hooks yourself from [`settings.example.json`](settings.example.json).

Keep the hooks in **`settings.local.json`** to sidestep the Claude Code `/model`
migration bug ([#22659](https://github.com/anthropics/claude-code/issues/22659)), and
**merge** into your existing config rather than overwriting it.

---

## Configuration

| Env var | Default | Meaning |
|---------|---------|---------|
| `IFFABLE_PROFILE` | `auto` | `auto` = resolve from launch model; or force `fable` / `fallback` / `off`. Overrides the cache. |
| `IFFABLE_HOME` | `~/.claude/iffable` | where `iffable.py` and `instructions/` live. |
| `IFFABLE_SPAWN_LIMIT` | `1500` | spawn prompt/script char length above which the ledger guard applies. |

---

## Ledger format

The Requirements Ledger lives at `./.workflow/LEDGER.md`. Numbered checkbox lines:

```markdown
- [ ] 1. <requirement, concrete and verifiable>
- [ ] 2. <requirement>
- [x] 3. <done AND verified>
- [~] 4. deferred: <reason> — only with user approval
```

The spawn guard requires this file to exist before a large delegation; the stop guard
blocks ending the turn while any `- [ ]` line remains.

---

## Running tests

```sh
python3 -m unittest discover -s tests
```

Pure stdlib `unittest`, zero external dependencies. Covers profile resolution, ledger
walk-up (including the `.git` boundary), the spawn decision (Haiku ban, over-limit
without ledger, light-model exemption, Opus still-guarded, fork exemption, fallback
dormancy), and the stop decision.

---

## Credits

Enforcement-mechanism concept inspired by
[Rylaa/fable5-orchestrator](https://github.com/Rylaa/fable5-orchestrator) (MIT,
© Yusuf Demirkoparan). No code retained — iffable is an independent implementation.

## License

[Apache-2.0](LICENSE).
