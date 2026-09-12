# Status

Where the build has got to. See `DESIGN.md` for why the project is shaped this
way, and for the rules any new handler has to respect.

## Where it stands now

**Working against the live game.** On 11 September 2026 it completed five
consecutive careers across two loops with no errors — the first runs in which
skill buying and spark reroll both went end to end.

| | |
|---|---|
| screens scanned | 22, all with handlers |
| dialog titles | 29 with actions, 30 decoys that deliberately lose |
| template PNGs | 54 |
| task settings | 16 (14 user-facing) |
| `uma_it/` | 3,842 lines |
| dashboard | `public/index.html`, 874 lines, one file |
| checks | 18 scripts |

Verified live: skill buying spends a budget down to less than the cheapest
remaining skill (4108 points to 3 in one career); spark reroll rerolls on a
miss, keeps on a hit, and keeps the larger set when neither qualifies; TP
restore prefers an item, falls back to carats, and never spends a chocolate one.

The section below is the build log, kept in the order things were done. Figures
in it are from the time each entry was written.

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
      — since proven live: every career since 11 Sep 2026 has started through
        this path

- [x] `uma_it/enter.py` and `uma_it/collect.py` — Home through to the start
      dialog, and the result screens after. **19 of 22 screens now have a
      handler**; the three left are the two optional features
      — `check_handlers.py`: 25 assertions. Home clears a stale agenda phase,
        Scenario Select fails the task rather than starting the wrong one, and
        the finish screen still finishes a career when asked for skill buying
        (which was unwritten at the time; it is written now)

- [x] `main.py` and `device.py` — the app starts, registers, restores its task
      list and serves the dashboard. **It is runnable**
      — `check_main.py`: the ordering that fails silently. Registering the app
        after restoring tasks does not raise; it empties the task list on the
        first run, because the loader swallows the KeyError and the next save
        writes the shortened list back. Both halves are pinned: that tasks
        really are dropped when the app is unknown, and that `main()` does it
        in the right order

- [x] The dashboard — `public/index.html`, one file. No build step,
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

- [x] Spark reroll and skill priorities in the dashboard — both sections stay
      hidden until their feature is switched on, so the default view is still
      the handful of fields a plain run needs
      — sparks are chips that cycle off / 1 / 2 / 3 stars; skills are chip
        lists with autocomplete off `/api/skills`, which matters because a
        skill name is OCR'd and fuzzy-matched, so a typo is a skill that never
        gets bought and nothing says why
      — `check_ui.py` now also pins the spark names against `parse.py`

- [x] Restoring TP — `uma_it/tp.py`. `allow_recover_tp` above 0 now actually
      restores rather than just accepting the prompt: a TP item if one is held,
      carats otherwise, and never a chocolate item
      — `check_tp.py`: 17 assertions, one per screen of the flow plus both
        spending rules, and that an unrecognised screen gives up rather than
        being retried into the click guard

- [x] The CAREER colour search — it was never broken. The parent's note that it
      had "135 failures with no recorded success" was an artifact of logging
      only failures, with both paths clicking under the same name
      — settled from the DEBUG career's tap coordinates: one Home frame tapped
        (540, 1116), the search's own result; the next, two seconds later and
        mid-transition, warned and tapped the fixed point (548, 1083)
      — successes are logged now, the two clicks have different names, and a
        miss waits a few frames instead of immediately making a second,
        redundant tap on Home
      — `check_handlers.py` runs the real search against a real Home frame
        (`resource/uma_it/fixture/home_career_region.png`), so the region and
        the colour thresholds are pinned together

## Next

- [ ] **Reading the spark list past the fold has never run against the game.**
      `read_all_spark_rows` swipes and merges pages so a targeted white spark
      below the fold is not read as absent - 62% of captured frames hid at
      least one row, up to nine of eighteen. The merge, the termination and the
      refusal to guess after a failed scroll are all pinned with fakes, and the
      swipe path is drawn on a real frame to confirm it starts and ends inside
      the list. What is untested is the game's own response: this list flings
      rather than scrolling a fixed step, so the overshoot is the open
      question. The pages overlap by three or four rows to absorb it
- [ ] **The spark tiebreak when both lists fit one page** has no live coverage.
      `handle_spark_selection` counts rows when neither list overflows, which is
      exact, and falls back to total stars only on a genuine tie. That branch
      needs both sets under 9 rows — about 7% of tiebreaks — and has not come up
      in a real career. Covered by `check_spark.py` and by the 137 captured
      selection frames, not by the game
- [ ] **The agenda first-click retry.** The first Load List click of a run does
      not take; the flow reopens the list and clicks again, costing ~10s. It
      happens once per career, every career. Three hypotheses have each been
      disproved by measurement and the cause is still unknown. Harmless
- [ ] **The watchdog capture stall** inherited from the parent: `get_screen`
      occasionally returns byte-identical frames during the countdown, which
      trips the 30s watchdog and restarts the game. The in-game clock keeps
      perfect wall time across the event, so the game is fine and the bot's view
      of it is what stalls. Costs about 40 seconds and no careers. The open
      question is ADB / uiautomator2 / emulator screencap, not the threshold
- [ ] **A packaging pass.** `requirements.txt` is inherited from the parent and
      installs a good deal this bot never imports

## Line budget

Target is ~2,050 lines for the core and ~2,700 with both optional features,
against the parent project's 9,415 lines of module Python. `uma_it/` is at
**3,842** with both optional features in — over the 2,700 estimate, and the
overage is theirs: skill buying and spark reroll together are about 1,150 lines
of screen reading in the parent and are not much smaller when moved. The core
without them is ~2,300.

| Piece | Estimate |
|---|---|
| Assets (done) | 200 |
| Enter and collect handlers (done) | 300 |

| Parse helpers (done) | 260 |
| Task + context (done) | 300 |
| Hooks | ~120 |
| Manifest and screens (done) | 240 |
| Dashboard (done) | 874 |
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

```bash
py -3.10 check_tp.py
```

```bash
py -3.10 check_scope.py
```

```bash
py -3.10 check_presets.py
```

```bash
py -3.10 check_skills_db.py
```

All eighteen exit non-zero on failure. Run them after touching anything under
`uma_it/` or `bot/`.

## Running it

```bash
py -3.10 main.py
```

Pick the emulator when asked; the dashboard opens on http://127.0.0.1:8071.
The process soft-restarts itself after every career, relaunching `main.py` with
`UAT_AUTORESTART=1`, which takes the device from `config.yaml` and opens no
browser window.

`start.bat` does the same thing with the interpreter check in front of it. See
the README for installing and for configuring a run.

## Settled: the Skip presses do not matter

`before_hook` and `after_hook` are wired to `None`, and that is now measured
rather than assumed. `apply_rules` was provably inert (its rule table has one
key, TEAM_TRIALS, and this app runs in LOOP mode) and `before_hook`'s branches
return early for this path by explicit checks. The open one was `after_hook`,
which presses the game's Skip buttons.

Run on 10 Sep 2026: one full career on the parent project with file logging
raised to DEBUG, so `bot/conn/u2_ctrl.py` recorded every click by name. The
career completed - 16:12 to 17:04, `TASK_STATUS_SUCCESS`, including the entire
collect phase where those presses would have to happen.

**`click >> Skip` appears zero times.** The complete click inventory for the
career was 15 blind fallback clicks, 5 result confirms, 5 preparation Next
steps, 3 Next buttons, and single named clicks for each handler.

Two things the same run confirmed in passing: the blind fallback is
load-bearing (15 clicks), and the `Next` button probe kept in
`script_not_found_ui` earns its place (3).

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
