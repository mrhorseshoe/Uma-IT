# Status

Where the build has got to. See `DESIGN.md` for why the project is shaped this
way, and for the rules any new handler has to respect.

## Done

- [x] Repository, layout and design recorded
- [x] Engine vendored — `bot/`, 3,566 lines, 34 importable modules
      — seven references into the parent's game module found; the three
        top-level ones repointed at `uma_it/asset/`, `/api/pal-defaults`
        stubbed. `check_engine.py`: all 34 import, nothing from the parent
        project loads
- [x] Calibrated assets moved verbatim and verified
      — 34 template PNGs (28 for screens, 6 the engine requires), 22 screens,
        38 click points
      — `check_assets.py`: all resolve, all decode, no screen references a
        template outside the package
- [x] Dialog title scoring set extracted — 23 owned, 36 distractors, 59 total
      — `check_titles.py`: every owned title wins its own frame, no distractor
        is wrongly taken, and `'Final Confirmation'` resolves to itself

- [x] `uma_it/task.py`, `uma_it/context.py` and `uma_it/define.py` — 19
      settings against the parent's 50, and settings separated from run state
      so only what must persist does
      — `check_task.py`: 30 assertions. A task round-trips through the engine's
        real serializer with every setting intact; empty, null and
        parent-project payloads all build; a finished run increments
        `loops_done` and the increment survives the trip

- [x] `uma_it/manifest.py` and `uma_it/screens.py` — the app registers, the
      22-screen scan list is wired, and `build_task` / `build_context` are
      reachable through the executor's own lookup path
      — `check_manifest.py`: registration resolves under the name `build_task`
        stamps, the dispatch key matches the task type, no screen is scanned
        from outside this project, no two screens share a name, and an
        unhandled screen warns instead of raising

- [x] `uma_it/dialogs.py` — the title router and the blind fallback. 28 titles
      with actions, 31 kept only so they win their own frames
      — which titles get an action was decided by counting what actually
        appears across the preceding careers, not by reading the parent's
        table: `Recover TP` (332 frames), `Confirm` (112), `Items Selected`,
        `Race Details` and `Auto Select` all occur and none was owned
      — `check_dialogs.py`: 25 assertions driving the router with a fake
        controller. The TP decision ends the career when `allow_recover_tp` is
        0 and spends only when authorised; the two screens the parent
        deliberately leaves alone click nothing; unwritten handlers stay still;
        an unknown title still gets the load-bearing fallback click

## Next
- [ ] `uma_it/career.py` — the countdown handler; clicks nothing (rule 3)
- [ ] `uma_it/start.py` — career start, career-mode failsafe, pending-run
      rescue. **The one part never run against the live game** (see DESIGN.md)
- [ ] `uma_it/agenda.py` — the slot-1 picker; read the scrollbar (rule 2)
- [ ] Enter and collect handlers — ~300 lines
- [ ] `main.py` — device checks, scheduler, HTTP server
- [ ] Web UI — IT-only; the parent project's task modal is 5,330 lines for a
      career mode this app does not play
- [ ] Optional: skill buying (~450 lines), spark reroll (~180)

## Line budget

Target is ~2,050 lines for the core and ~2,700 with both optional features,
against the parent project's 9,415 lines of module Python.

| Piece | Estimate |
|---|---|
| Assets (done) | 200 |
| Enter/collect handlers | ~300 |
| Blind fallback, IT-only | ~60 |
| Parse helpers, core | ~180 |
| Task + context (done) | 300 |
| Hooks | ~120 |
| Manifest and screens (done) | 240 |
| Router and fallback (done) | 330 |
| Start, agenda, career | ~470 |

## Checks

```bash
py -3.10 check_assets.py
```

```bash
py -3.10 check_titles.py
```

```bash
py -3.10 check_engine.py
```

```bash
py -3.10 check_task.py
```

```bash
py -3.10 check_manifest.py
```

```bash
py -3.10 check_dialogs.py
```

All six exit non-zero on failure. Run them after touching anything under
`uma_it/` or `bot/`.

## Unresolved: do the Skip presses matter?

The parent runs `after_hook` on every frame, and part of it presses the game's
Skip buttons. They may be what dismisses the result animations at the end of a
career, or they may never fire on this path. `before_hook` and `apply_rules`
are settled — both are provably inert for an Independent Training task in LOOP
mode — but this one is not, and the hooks are wired to `None` until it is.

**The 26 careers' logs cannot answer it.** Clicks log at DEBUG
(`click >> <name>` in `bot/conn/u2_ctrl.py`) and those logs are INFO, so the
absence of "Skip" in them is not evidence of anything.

Settle it by running one career on the parent project at DEBUG and grepping for
`click >> Skip`. Do that before the first live run here.

## Known no-ops, deliberately left

Three engine hooks that invalidate the parent project's parse cache and its
skills and events databases are wrapped in `except Exception: pass`, so here
they do nothing and say nothing. Harmless today. If this project grows a skills
or events database, they must be revisited — `bot/base/purge.py:370`,
`bot/server/handler.py:176` and `:234`.

The dashboard's year / mood / energy readout is a turn-by-turn concept. Its
templates were carried over so nothing regresses, but nothing in an Independent
Training run branches on mood; decide what the readout should be when the UI is
rebuilt.
