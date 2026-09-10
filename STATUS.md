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

- [x] `uma_it/career.py` — the countdown handler and the training-log close.
      Fifty of a career's fifty-two minutes are the first of these, and its
      whole job is to do nothing correctly
      — `check_career.py`: 12 assertions. It clicks nothing on a readable
        frame, an unreadable one, an OCR that raises, a missing screen and a
        context with no run state; it sleeps between passes; it logs on the
        minute rather than every pass; and the training-log close clicks once
        and resets the countdown log

- [x] `uma_it/agenda.py` and `uma_it/parse.py` — the slot-1 picker, a state
      machine across three screens, plus the screen-reading helpers it needs
      — `check_agenda.py`: 25 assertions, most of them negative. An unreadable
        scrollbar loads nothing and scrolls to look again; row 2 or row 5 on
        top loads nothing; only a confirmed row 1 is clicked. An overwrite the
        flow did not ask for is cancelled. Both budgets end a stuck flow by
        closing rather than by loading something

- [x] `uma_it/start.py` — career start, the trainer-event failsafe and the
      pending-run rescue. With it the agenda picker is reachable end to end for
      the first time: Final Confirmation sets the phase it runs on
      — `check_start.py`: 18 assertions, all about when a handler refuses to
        act. The career-mode dialog switches to Normal and never confirms
        unverified, giving up by failing the task once its budget is spent; an
        unreadable frame counts as event mode, because guessing the other way
        confirms a one-way door. The start dialog checks the tab rather than
        assuming it. The pending-run dialog prefers the colour search, since
        Delete Data sits on the same screen
      — **still never run against the live game** (see DESIGN.md)

- [x] `uma_it/enter.py` and `uma_it/collect.py` — Home through to the start
      dialog, and the result screens after. **19 of 22 screens now have a
      handler**; the three left are the two optional features
      — `check_handlers.py`: 25 assertions. Home clears a stale agenda phase,
        Scenario Select fails the task rather than starting the wrong one, and
        the finish screen still finishes a career when asked for skill buying,
        which this app has not written

## Next
- [ ] `main.py` — device checks, scheduler, HTTP server
- [ ] Web UI — IT-only; the parent project's task modal is 5,330 lines for a
      career mode this app does not play
- [ ] Optional: skill buying (~450 lines), spark reroll (~180)

## Line budget

Target is ~2,050 lines for the core and ~2,700 with both optional features,
against the parent project's 9,415 lines of module Python. `uma_it/` is at **2,266**, with only the two optional features left.

| Piece | Estimate |
|---|---|
| Assets (done) | 200 |
| Enter and collect handlers (done) | 300 |

| Parse helpers (done) | 260 |
| Task + context (done) | 300 |
| Hooks | ~120 |
| Manifest and screens (done) | 240 |
| Router and fallback (done) | 330 |
| Countdown and results (done) | 90 |
| Agenda picker and parse helpers (done) | 320 |
| Career start (done) | 200 |

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

```bash
py -3.10 check_career.py
```

```bash
py -3.10 check_agenda.py
```

```bash
py -3.10 check_start.py
```

```bash
py -3.10 check_handlers.py
```

All ten exit non-zero on failure. Run them after touching anything under
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
