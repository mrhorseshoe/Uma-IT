# Uma-IT

A bot that loops Umamusume: Pretty Derby (Global) **Independent Training**
careers, and does nothing else.

## Why this project exists

The parent project (`UAT-Global-Server`) automates a career the way players
used to play one: turn by turn, choosing training, races, events and skills.
Cygames then shipped Independent Training, in which **the game plays the career
itself** — you configure a run, press start, and collect the result about fifty
minutes later. That makes almost all of the old bot dead weight for this use.

This is not a guess. A full career was traced over 81 log events, and 26
consecutive careers were then run on a slimmed module inside the parent repo.
What an Independent Training career actually touches:

| Surface | Parent project | This one |
|---|---|---|
| Screen definitions | 56 | **22** |
| Templates | 179 | **28** |
| Template PNGs on disk | 574 | **28** |
| Click points | 106 | **38** |
| Screen handlers | 54 functions / 2,676 lines | 17 / **851 lines** |
| Screen-parsing helpers | 49 functions / 1,710 lines | 13 / **516 lines** |
| Task fields read by decision code | 50 saved | **20** |
| Module Python | 9,415 lines | **~2,000 target** |

Fifty of a career's fifty-two minutes are spent in **one handler that clicks
nothing**. The active flow is about thirty steps. The turn-by-turn decision
engine of the parent project (`ai.py`, 427 lines) is unreachable here by
construction.

## What is reused, what is moved, what is written fresh

Three tiers, and the distinction is the whole design:

**Vendored — `bot/` (3,566 lines).** Screenshots, template matching, OCR,
taps, the click guard, the freeze watchdog, the scheduler, the HTTP server. It
was exercised for 21 hours straight by the loop this project replaces, so it is
copied here rather than rewritten. Do not rewrite it.

It is *called* game-agnostic in the parent project and very nearly is, but not
quite: seven places reach back into the parent's game module, and three of them
were top-level imports that broke on arrival here. They are repointed at this
project's asset layer:

| Engine file | Wanted | Resolution |
|---|---|---|
| `engine/ctrl.py` | `asset.point import *`, for `ESCAPE` alone | imports `ESCAPE` by name |
| `conn/u2_ctrl.py` | `REF_DONT_CLICK` | template moved here; it guards a real tap-blocking region |
| `conn/fetch.py` | `MOTIVATION_LIST` | five templates moved here |
| `server/handler.py` | `read_pal_defaults` | returns `{}`; "pal" is a turn-by-turn feature |

Three further references — parse-cache and skills/events database
invalidation in `base/purge.py` and `server/handler.py` — sit inside
`try: ... except Exception: pass` and are therefore silent no-ops here. They
are harmless, and they are also invisible, which is worse: if this project ever
grows a skills or events database, those hooks will not fire and nothing will
say so. `check_engine.py` pins the import surface.

**Moved verbatim, never retyped — the calibrated assets.** The 28 template
PNGs, the 22 screen definitions and the 38 click points are copied
byte-for-byte out of the parent project. Every one was calibrated against the
live game at 720x1280, and **re-cropping them is how the parent project's worst
bugs were made** — `MAIN_MENU` matching event-hub pages, race banners needing
to start at x >= 60. A blank-page rewrite of *code* is cheap and safe. A
blank-page rewrite of *calibration* is expensive and buys nothing.

**Written fresh — everything else.** The handlers, the dialog router, the task
and context, the dashboard. This is where the 75% cut comes from.

The dashboard is the sharpest example. The parent's is a Vue 3 + Vite app whose
task modal alone is 5,330 lines - 160 `data()` properties and 101 methods, most
of them configuring a career this app does not play - and it loads Bootstrap
and jQuery from a CDN, so it needs the internet to render a page about an
emulator on the same machine. This one is a single HTML file with no build step, no framework and no network
dependency. It shows seven fields by default - what a plain run needs - and
reveals the skill and spark sections only when those features are switched on.

## Layout

```
main.py               start-up order, and nothing else
device.py             ADB discovery, recovery and health checks
bot/                  vendored engine, unchanged
resource/uma_it/
  ui/                 22 screen templates
  ref/                4 reference crops
uma_it/
  asset/
    template.py       28 templates          [extracted, verified]
    ui.py             22 screens            [extracted, verified]
    point.py          38 click points       [extracted, verified]
    dialog_titles.py  59-title scoring set  [extracted, verified]
  manifest.py         app registration; screen -> handler table
  screens.py          the scan list
  dialogs.py          OCR-title dialog router
  career.py           the countdown handler (where the run spends its time)
  start.py            career start, career-mode failsafe, pending-run rescue
  agenda.py           the My Agendas slot-1 picker
  enter.py            Home through to the start dialog
  collect.py          the result screens
  parse.py            screen reading no template can do
  define.py           the scenario enum
  task.py             19 settings; everything that must survive a restart
  context.py          run state; everything that is expected not to
public/index.html     the dashboard - one file, no build step
check_assets.py       every template resolves and decodes
check_titles.py       every owned dialog title wins its own frame
check_engine.py       every engine module imports, and reaches back nowhere
```

## Settings and run state are separated, and only one of them persists

The parent project copied every setting from the task onto its run context, so
each one existed in both places. Adding a setting meant editing four files, and
the copy step was the easy one to forget.

Here nothing is copied:

- **`task.detail`** holds the 19 settings. It is serialized with the task,
  reloaded at boot, and survives the soft restart that happens after every
  career. `loops_done` is only correct because it lives here.
- **`ctx.career`** holds run state. It is built fresh per career and is
  *expected* to be lost. Nothing in it may be the only copy of something that
  has to outlive the run.

Handlers read settings from `ctx.task.detail` and run state from `ctx.career`.
The parent calls its equivalent `ctx.cultivate_detail`; code moved across will
raise `AttributeError` rather than silently read a stale value.

One wart: the engine's serializer still writes `ura_config: null` and
`aoharu_config: null` into every payload, because it special-cases the parent's
scenario config. `build_task` ignores unknown keys, so this round-trips
harmlessly. Left alone rather than patched, since the serializer is shared
engine code and the keys cost nothing.

## Rules this project inherits, each paid for in a live failure

None of these is obvious from reading the code. All are load-bearing.

1. **Home is the bottom-nav Home tab, not the CAREER button.** That button's
   art rotates with in-game events and no single crop matches two rotations;
   twice in one week the old bot could not find Home at all. CAREER is then
   located by colour search, not by template — and that search works, verified
   against a real Home frame and pinned by a fixture. The parent's claim that
   it had never once succeeded came from logging only its failures.
2. **The agenda is slot 1, and the scrollbar is read before clicking.** An
   unreadable scrollbar must *never* be treated as row 1 — that assumption ran
   a four-race agenda for fifteen careers without anyone noticing. Picking by
   name failed differently: a task saved with the field blank disabled the
   picker for eleven careers.
3. **A waiting handler must click nothing.** The generic not-found fallback
   blind-clicks a corner under a fixed name, and 11 identical consecutive
   clicks trip the repetitive-click guard into restarting the game. The
   countdown screen needs its own do-nothing handler.
4. **The 30 s freeze watchdog fires on a capture stall, not a frozen game.**
   Measured: the countdown screen scores ~55x above the threshold, then drops
   to *exactly* 0.000 in one sample, while the in-game clock keeps perfect
   wall-clock time across the stall. So the game is fine and `get_screen` is
   returning byte-identical frames. **Raising the threshold cannot help** — a
   score of 0.000 trips any positive threshold. The open question is ADB /
   uiautomator2 / emulator screencap.
5. **Confirm on the career-start dialog is a one-way door.** Select Normal
   Mode, verify the switch took, *then* confirm. Confirming the wrong option
   starts an event career that cannot be backed out of.
6. **`'Career Complete'` needs its own title entry and always clicks Cancel.**
   It used to ride a fuzzy match onto `'Training Complete'` by coincidence,
   which happened to click the same point — until a trainer event relabelled
   the green button "Event Home".
7. **State must survive the soft restart.** The process restarts after every
   career. Anything kept only in memory silently resets every run: loop counts,
   stop-after-run, scheduler flags, runtime thresholds.
8. **Dialog titles are scored against every title the path can show.** See
   `uma_it/asset/dialog_titles.py`. `'Confirmation'` scores 0.800 against
   `'Final Confirmation'`; against a table holding only titles we act on, ours
   wins the career-start dialog and **no career ever starts**. The 36
   distractor titles earn their place by losing. Pinned by `check_titles.py`.
9. **`'Confirm'` is two unrelated prompts, and only the body separates them.**
   The game titles both the TP restore offer and the skill screen's
   "Exit without learning skills?" prompt `Confirm`. Routing the title straight
   to the TP handler ended every career of the 11 Sep run the moment its skills
   were bought: the bot read a prompt raised by its own Back click as an
   out-of-TP offer and failed the run. Three loops burned in three minutes, each
   re-entering the skill screen the last had never left, and the logs said
   "TP restore offered" with TP in hand. Matching was never wrong — a title was
   simply not enough. `read_body` now reads the sentence under the header, and
   the decline logs what it read so a third `Confirm` prompt is visible the
   first time it appears rather than after a run.

## Not verified against the live game

The career-start path — `Final Confirmation`, the career-mode failsafe and the
pending-run rescue — is **simulation-verified only** in the parent project. It
was written after the loop had already been stopped, so no career has begun
through it on the real game. Treat it as the one place wanting live
confirmation.

The gate on getting that confirmation is TP: Independent Training costs 30 TP
and regenerates far slower than a ~50 minute career consumes it. With
`allow_recover_tp` at 0 the bot fails a career rather than spending carats to
avoid it, which is correct and also means **the first live run needs TP in
hand.**

## Working on it

**Python is `py -3.10`.** Packages live in system Python 3.10's site-packages.

**Scripts must run with the repo root as the working directory.** `Template`
resolves `resource/...` relative to the CWD, and templates that fail to load
silently make every screen look unrecognised — the most confusing failure mode
in this codebase. Both check scripts `os.chdir` to their own directory for this
reason.

**Verify handlers against captured frames, not against the game.** Capture a
real screen over ADB, then drive the handler with a fake controller exposing
`get_screen`, `click_by_point` and `click`, and assert on the clicks it
records. That catches a wrong click point without touching a live career.
