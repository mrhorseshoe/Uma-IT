# Uma-IT

A streamlined bot that loops **Independent Training** careers in Umamusume:
Pretty Derby (Global).

Independent Training is the mode where the game plays a career itself: you
configure the run, start it, and collect the result about fifty minutes later.
This bot does that on a loop — enter a career, load the race agenda, wait out
the run, buy skills, handle the sparks, start the next one — and deliberately
does nothing else.

There is no game API. Everything is OpenCV template matching and PaddleOCR over
screenshots, with taps sent through uiautomator2 over ADB.

## What one loop does

1. From Home, open CAREER and pick the scenario and trainee
2. Borrow a support card by name, matched against the card on screen
3. Load your saved race agenda from slot 1 and confirm the run
4. Wait out the ~50 minute Independent Training countdown
5. Collect the result screens
6. Buy skills, sweeping repeatedly until nothing affordable is left
7. Read the end-of-career sparks and optionally reroll them
8. Restore TP if the task allows it, then start the next career

The process restarts itself after every career, so anything that has to
survive — loop counts, scheduler state, the task itself — is written to
`userdata/` and reloaded at boot.

## Status

Working. On 11 September 2026 it completed five consecutive careers across two
loops with no errors, including the first careers in which skill buying and
spark reroll both ran end to end.

Verified against the live game:

- **Skill buying** spends the budget down to whatever is cheaper than the
  cheapest remaining skill — 4108 points to 3 in one career, 4057 to 71 in
  another — across repeated passes, because learning a skill unlocks more.
- **Spark reroll** rerolls when the star criteria are not met, keeps the roll
  when they are, and when neither set qualifies keeps the set with the most
  sparks. All three branches were observed and each decision was recomputed
  independently from the logs.
- **TP restore** prefers a TP item and falls back to carats, and never spends a
  chocolate item.

See [STATUS.md](STATUS.md) for the checklist and [DESIGN.md](DESIGN.md) for how
it is put together and which rules exist because something once broke.

## Install

### 1. Python 3.10, specifically

The bot needs **Python 3.10**. Install it from
[python.org](https://www.python.org/downloads/) with the **py launcher** option
ticked, then check:

```bash
py -3.10 --version
```

It must be `py -3.10`, not `python`. A bare `python` picks up whatever is first
on PATH and fails at `import cv2` with a message that says nothing about why.
`main.py` refuses to start under any other version rather than failing that way.

### 2. Get the code

```bash
git clone https://github.com/mrhorseshoe/Uma-IT.git
```

### 3. Install the packages

```bash
py -3.10 -m pip install -r requirements.txt
```

Two things to know about that file:

- It is inherited from the parent project and installs more than this bot uses.
  What is actually imported is `opencv-python`, `numpy`, `paddleocr`,
  `uiautomator2`, `fastapi`, `uvicorn`, `pydantic`, `PyYAML`, `psutil`,
  `colorlog`, `croniter`, `plyer` and `requests`.
- It pins `paddlepaddle-gpu`, which needs a CUDA-capable GPU. **Without one,
  install `paddlepaddle` instead** — the bot detects what is available and logs
  which it is using at startup.

Packages must land in system Python 3.10's site-packages, not a virtualenv,
because that is where `py -3.10` looks.

### 4. An Android emulator

- Resolution **720x1280**, with ADB debugging enabled
- Umamusume: Pretty Derby (Global), package `com.cygames.umamusume`
- Reachable over ADB — `deps/adb/adb.exe` ships with the repo, so there is
  nothing to install separately

### 5. Set the game up once

The bot does not configure these for you:

- Put the race agenda you want in **slot 1** of My Agendas. Selection is always
  slot 1; there is no task setting for it, and two earlier designs that tried to
  pick by name or by position both silently ran the wrong schedule.
- Have the support card you want to borrow available to follow.

## Running it

Double-click `start.bat`, or:

```bash
py -3.10 main.py
```

Pick the emulator when asked. The dashboard opens on <http://127.0.0.1:8071> —
a single HTML file with no build step, so you can edit `public/index.html` and
reload.

**Starting the process starts the loop.** If a saved task restores and there is
no recorded scheduler state, the scheduler starts — which is what lets the loop
survive the soft restart it performs after every career. To restart without
running a career, stop it from the dashboard once it is up.

**Stop it from the dashboard, not by killing the process.** Run counts and
scheduler flags only reach disk when a run ends.

### Reaching the dashboard from another device

It binds to `127.0.0.1` deliberately. To reach it from a phone without exposing
it to your LAN, put it behind [Tailscale](https://tailscale.com):

```bash
tailscale serve --bg 8071
```

The dashboard has **no authentication** and can start and stop the bot, edit the
task and authorise spending, so anything that can reach it can drive it.

## Configuring a run

Everything is set from the dashboard. The task carries 14 user-facing settings:

| setting | what it does |
| --- | --- |
| `scenario` | which career scenario to start |
| `follow_support_card_name` | the card to borrow, matched by OCR against the name |
| `use_last_parents` | keep the previous parents rather than letting the game pick |
| `loop_count` | careers to run, `0` for until stopped |
| `allow_recover_tp` | `0` fails a career rather than paying; above `0` restores TP, carats included |
| `skip_learn_skill` | turn skill buying off |
| `learn_skill_list` | three priority tiers, bought in order |
| `learn_skill_blacklist` | never buy these |
| `learn_skill_only_user_provided` | buy only what is listed, ignoring leftovers |
| `spark_reroll_enabled` | turn spark reroll on |
| `spark_reroll_targets` | spark name to minimum stars |
| `spark_reroll_mode` | `or` needs a hit in either group, `and` in both |
| `spark_reroll_min_stars` | default minimum for targets that do not set their own |
| `stop_at_spark_reroll` | stop on the sparks screen so you can reroll by hand |

Skill configurations can be saved as named presets, stored per-file under
`userdata/skill_presets/`.

Note that a reroll costs **30 TP**, the same as a career. Targeting a 3★ spark
rerolls on roughly 99% of careers, which doubles the TP a loop consumes.

### Keeping the skill list current

The bot OCRs a skill name off the screen and fuzzy-matches it against a list of
known names, so a skill it has never heard of cannot be bought and nothing says
why. After a game update adds skills — a new umamusume, a new support card —
press **Update from game files** in the skill section.

It reads the game's own `master.mdb`, which is the authority on these names, and
adds anything the list is missing. It never removes anything. The first press
looks in the usual place; if your install is somewhere else it asks for the
folder, and remembers it afterwards. You can give it the game folder, the folder
holding `master.mdb`, or the file itself.

**Remove unknown** does the opposite: it drops entries for skills the game's
database does not have. A scraped list carries names the game never shows, and
they are not free — the matcher scores an OCR'd name against every candidate, so
a name that cannot appear on screen can still win a frame. It keeps un-suffixed
aliases of graded skills, since `Corner Acceleration` is what OCR produces for
the game's `Corner Acceleration ○`, and refuses outright if the database reads
back implausibly small rather than emptying your list.

**Your list is yours.** The repository ships a baseline at
`resource/uma_it/skills.json` and never receives updates; a sync writes to
`userdata/skills.json`, which is gitignored and shadows the shipped one. Keeping
it current after a game update is up to you. Delete that file to fall back to
the baseline.

## What changed from UAT-Global-Server

This is a fresh, much smaller project rather than a fork of
[UAT-Global-Server](https://github.com/mrhorseshoe/UAT-Global-Server). The
parent automates a turn-by-turn career — training choices, races, events, moods,
support-card bonds — and Independent Training makes almost all of that
unnecessary. An IT career touches 22 of the parent's 56 screens.

|  | UAT-Global-Server | Uma-IT |
| --- | --- | --- |
| task settings | 46 | 16 (14 user-facing) |
| UI templates | 574 | 54 |
| web UI | Vue 3 + Vite with the build output committed; `TaskEditModal.vue` alone is 5,330 lines | one 874-line HTML file, no build step |
| external assets | Bootstrap and jQuery from a CDN | none — works offline |
| dialog handling | one `TITLE` list; an unmatched dialog falls to a blind corner click | 29 titles with explicit handlers, scored against 30 decoys that deliberately lose |
| tests | none tracked | 17 check scripts |

The substantive differences:

**Every screen is named.** The parent dispatches dialogs by OCR'd title against
a list of the titles it acts on, so a screen it does not know gets cleared by a
blind corner click — which works, but means an unhandled screen looks exactly
like a handled one. Here the scoring set also holds 30 titles the bot does *not*
act on, precisely so they win their own frames instead of a shorter title of ours
stealing them. Across 26 careers that took `Unknown option box` warnings from
four per career to zero.

**Settings exist once.** In the parent every setting lives on both the task and
the run context, so adding one meant editing four files with the copy step the
easy one to forget. Here handlers read `ctx.task.detail` directly.

**Skill buying does not stop early.** The parent breaks out of its loop at the
first unaffordable skill, so a 300-point budget facing a 400-point skill bought
nothing at all. This one skips it and carries on, and reports what it could not
spend.

**One switch for spending.** The parent has separate flags for TP recovery and
for the reroll's TP prompt, which have to agree. Here `allow_recover_tp` governs
both.

**Dropped deliberately**, with the reasons recorded in `uma_it/task.py`: the
support card level filter (its OCR read 150 for a card that caps at 50, so it
passed everything), the mid-career skill threshold (there are no turns here),
manual purchase pauses, and a separate carat flag for rerolls.

The parent remains the place to look for anything this one does not do,
including normal-career play.

## Development

There is no test framework. Instead there are 18 `check_*.py` scripts at the
repo root, each driving real functions with fakes and asserting on the clicks and
decisions they produce:

```bash
py -3.10 check_skills.py
```

They are written to fail if the behaviour they describe regresses — several were
added after a bug reached the live game, and each states the failure it exists to
catch. Run them all before committing.

Screen handlers are best checked against real captures. Grab a frame over ADB and
run the handler against the saved PNG with a fake controller:

```bash
deps/adb/adb.exe -s emulator-5554 exec-out screencap -p > shot.png
```

Such scripts must `os.chdir` to the repo root — templates resolve relative to the
working directory, and templates that fail to load silently make every screen
look unrecognised.

## Known limits

- **Agenda selection is always slot 1.** Copy the agenda you want there.
- **Normal-career play is not supported.** Use the parent project.
- **The dashboard has no authentication.**
- **Windows in practice** — the bundled ADB is `adb.exe` and the launcher is a
  `.bat`, though nothing in the bot logic is platform-specific.

## Requirements

- Python 3.10, reachable as `py -3.10`
- An Android emulator at 720x1280 with ADB debugging
- Umamusume: Pretty Derby (Global)
- A CUDA GPU is optional; PaddleOCR runs on CPU

## License

[MIT](LICENSE), covering this project's own code — everything under `uma_it/`,
`public/`, the check scripts, `main.py` and `device.py`.

**The engine under `bot/` is vendored** from
[UAT-Global-Server](https://github.com/mrhorseshoe/UAT-Global-Server), which
descends in turn from
[TomerGamerTV/UAT-Global-Server](https://github.com/TomerGamerTV/UAT-Global-Server)
and an upstream CN project before that — parts of it still carry Chinese
comments from that lineage. **Neither of those repositories publishes a
license**, so the terms on that code are whatever their authors' default
copyright is, not MIT. If you intend to reuse `bot/`, take that up with them
rather than relying on this file.
