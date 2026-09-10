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

- [x] `main.py` and `device.py` — the app starts, registers, restores its task
      list and serves the dashboard. **It is runnable**
      — `check_main.py`: the ordering that fails silently. Registering the app
        after restoring tasks does not raise; it empties the task list on the
        first run, because the loader swallows the KeyError and the next save
        writes the shortened list back. Both halves are pinned: that tasks
        really are dropped when the app is unknown, and that `main()` does it
        in the right order

- [x] The dashboard — `public/index.html`, 456 lines, one file. No build step,
      no framework, no CDN, and same-origin API calls
      — `check_ui.py`: every path the page calls is a route the server serves,
        every setting it sends is one `build_task` reads, every scenario option
        maps to a real `ScenarioType`, and nothing is loaded from the network

- [x] Spark reroll — `uma_it/spark.py`, plus its screen reading in `parse.py`.
      **21 of 22 screens now have a handler**
      — `check_spark.py`: 25 assertions, most about when it decides *not* to
        spend. A satisfied or unreadable roll is kept; running out of TP
        mid-reroll aborts and keeps the original sparks instead of failing a
        career that is already over

- [x] Skill buying — `uma_it/skills.py`, its screen reading in `parse.py`, the
      default priority tiers in `const.py`, and the skill database shipped at
      `resource/uma_it/skills.json`. **Every scanned screen now has a handler**
      — `check_skills.py`: 17 assertions on what gets bought, and one on what
        must not get edited - the buying pass trims the priority list as it
        learns, and the task's own list is serialized, so the run works on a
        copy

## Next
- [ ] Expose spark reroll and the skill priority list in the dashboard. Both
      are more than a switch - a name -> stars map and a list of tiers - and
      both are usable over the API meanwhile. The seven settings the page does
      show are the ones a run actually needs
- [ ] A first live career. `start.py` has still never faced the game, and the
      `after_hook` Skip question is still open. Both need TP

## Line budget

Target is ~2,050 lines for the core and ~2,700 with both optional features,
against the parent project's 9,415 lines of module Python. `uma_it/` is at **3,598** with both optional features in - over the 2,700
estimate, and the overage is theirs: skill buying and spark reroll together are
about 1,150 lines of screen reading in the parent and are not much smaller when
moved. The core without them is ~2,300.

| Piece | Estimate |
|---|---|
| Assets (done) | 200 |
| Enter and collect handlers (done) | 300 |

| Parse helpers (done) | 260 |
| Task + context (done) | 300 |
| Hooks | ~120 |
| Manifest and screens (done) | 240 |
| Dashboard (done) | 456 |
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

```bash
py -3.10 check_main.py
```

```bash
py -3.10 check_ui.py
```

```bash
py -3.10 check_spark.py
```

```bash
py -3.10 check_skills.py
```

All fourteen exit non-zero on failure. Run them after touching anything under
`uma_it/` or `bot/`.

## Running it

```bash
py -3.10 main.py
```

Pick the emulator when asked; the dashboard opens on http://127.0.0.1:8071.
The process soft-restarts itself after every career, relaunching `main.py` with
`UAT_AUTORESTART=1`, which takes the device from `config.yaml` and opens no
browser window.

Two things stand between this and a first career, and neither is more code -
see below, and the note in DESIGN.md about `start.py` never having faced the
live game.

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
