# Uma-IT

A bot that loops **Independent Training** careers in Umamusume: Pretty Derby
(Global) — enter a career, load the race agenda, wait out the run, buy skills,
handle the sparks, start the next one. It deliberately does nothing else.

There is no game API. Everything is OpenCV template matching and PaddleOCR over
screenshots, with taps sent through uiautomator2 over ADB.

Descended from [UAT-Global-Server](https://github.com/mrhorseshoe/UAT-Global-Server),
itself a fork of [TomerGamerTV/UAT-Global-Server](https://github.com/TomerGamerTV/UAT-Global-Server).
That project plays a full turn-by-turn career; this one only loops Independent
Training, and is a fresh, much smaller build rather than a fork. See
[What changed](#what-changed) below.

## Features

**Loops careers unattended.** Home → scenario → trainee → borrow a support card
by name → load your saved agenda → wait out the ~50 minute run → collect →
repeat. The process restarts itself after every career, so loop counts,
scheduler state and the task survive in `userdata/`.

**Buys skills, and does not leave points behind.** Spends in three stages:

1. **your priority skills**, in the order you list them;
2. **the ◎ upgrade of any priority skill it bought at ○** — a higher grade
   sparks more often. The game only offers a ◎ once its ○ is learned, so the
   bot holds points back for it and buys it on the next pass;
3. **everything else, cheapest first**, since every skill learned is another
   chance at a white spark.

It sweeps the skill screen repeatedly — learning one skill unlocks others, and
a row missed on one sweep is caught on the next — until nothing affordable is
left. Typical result: 3,700 points down to less than the cheapest skill still
on offer. Priorities are yours in three tiers, with a blacklist, saved as named
presets; **Only buy what I list** stops after stage 1.

**Rerolls sparks against a rule you write.** Targets can be:

- **blue** (the five stats) and **pink** (the ten aptitudes), each with a
  minimum star level;
- **white** — skills, races and *scenario* sparks like `URA Finale` — as
  requirement rows: every row must hold, any one entry satisfies its row. One
  entry per row is a pure AND, one row holding everything is a pure OR, so
  there is no operator precedence to guess at. A plain-English readback under
  the builder states the rule back to you.

Above all of that sits **Always keep 3★**: name any of the five blue sparks
and a roll holding one at 3★ is kept on sight, whatever the rest of the rule
wanted. Across 281 logged spark sets a blue spark read 3★ in 6.8% of them —
about 1.4% for a particular stat — which is rare enough that a roll carrying
one is worth more than the one you were farming for.

It reads the whole list, scrolling past the fold when a target could be hiding
below it, and when neither roll qualifies it keeps the set with more sparks.

**Restores TP** from a TP item when you hold one, carats otherwise, and never
spends a chocolate item. One switch governs all spending.

**Keeps its own data current.** One **Update data** button reads the game's
`master.mdb` and refreshes both the skill list and the spark vocabulary, and the
dashboard says which game version they are current to.

**A dashboard with no build step** — one HTML file, no framework, no CDN, works
offline.

## Install

**1. Python 3.10, specifically.** Install from
[python.org](https://www.python.org/downloads/) with the **py launcher** ticked:

```bash
py -3.10 --version
```

It must be `py -3.10`, not `python`. A bare `python` picks up whatever is first
on PATH and fails at `import cv2` with a message that says nothing about why;
`main.py` refuses to start under any other version rather than failing that way.

**2. Get the code.**

```bash
git clone https://github.com/mrhorseshoe/Uma-IT.git
```

**3. Install the packages.**

```bash
py -3.10 -m pip install -r requirements.txt
```

Two things about that file: it is inherited from the parent project and installs
more than this bot uses, and it pins `paddlepaddle-gpu`, which needs a CUDA
card. **Without one, install `paddlepaddle` instead** — the bot detects what is
available and logs which it used at startup. Packages must land in system Python
3.10's site-packages, not a virtualenv.

**4. An Android emulator** at **720x1280** with ADB debugging, running
Umamusume: Pretty Derby (Global). `deps/adb/adb.exe` ships with the repo.

**5. Two things to set up in-game**, which the bot will not do for you: put the
race agenda you want in **slot 1** of My Agendas, and have the support card you
want to borrow available to follow.

## Running it

Double-click `start.bat`, or:

```bash
py -3.10 main.py
```

Pick the emulator when asked; the dashboard opens on <http://127.0.0.1:8071>.

**Starting the process starts the loop** — that is what lets a run survive the
soft restart after each career. To come up without running one, stop it from the
dashboard once it is up. **Stop it from the dashboard, not by killing the
process**: run counts only reach disk when a run ends.

To reach it from a phone without exposing it to your LAN, put it behind
[Tailscale](https://tailscale.com) with `tailscale serve --bg 8071`. The
dashboard has **no authentication** — anything that can reach it can drive the
bot and authorise spending.

## Configuring a run

Everything is set from the dashboard. The task carries 15 user-facing settings:
the scenario, the card to borrow, whether to keep the last parents, the loop
count, whether to restore TP, four for skill buying and seven for spark
reroll.

A reroll costs **30 TP**, the same as a career, so the targets decide what a
loop costs. A single 3★ spark rerolls on roughly 99% of careers; a row of
several common sparks at 1★ keeps most of the time. Measured over 140 captured
rolls, two specific skills co-occur in about 2–4% of them while any-of-five
lands near 56%.

### Keeping the game data current

The bot matches an OCR'd name against a list, so a skill or spark it has never
heard of cannot be targeted and nothing says why. After a game update, press
**Update data** in the Game data panel. It reads the game's own `master.mdb` —
the authority on these names — and adds what is missing, never removing
anything. The first press looks in the usual place and only asks for the folder
if that fails, remembering it afterwards.

The repository ships a baseline of **521 skills and 389 sparks**, current to
game **1.35.0**; updates are written to `userdata/`, which is gitignored, so
keeping yours current is up to you. **Remove unknown skills** does the opposite,
dropping entries the game does not have — a scraped list carries names that can
still win a frame from the real one.

## What changed

An Independent Training career touches 22 of the parent's 56 screens, so almost
none of its turn-by-turn machinery is needed.

|  | UAT-Global-Server | Uma-IT |
| --- | --- | --- |
| task settings | 46 | 17 |
| UI templates | 574 | 54 |
| web UI | Vue 3 + Vite, build output committed; `TaskEditModal.vue` alone is 5,330 lines | one HTML file, no build step |
| external assets | Bootstrap and jQuery from a CDN | none — works offline |
| dialogs | one `TITLE` list; anything unmatched gets a blind corner click | 29 titles with handlers, scored against 30 decoys that deliberately lose |
| tests | none tracked | 19 check scripts |

**Every screen is named.** An unhandled dialog in the parent looks exactly like
a handled one, because the fallback silently clears it. Here the scoring set
also holds titles the bot does *not* act on, so they win their own frames rather
than a shorter title of ours stealing them — which took `Unknown option box`
warnings from four per career to zero.

**Settings exist once.** In the parent each lives on both the task and the run
context, so adding one meant editing four files. Here handlers read
`ctx.task.detail` directly.

**Skill buying does not stop early.** The parent breaks at the first
unaffordable skill, so a 300-point budget facing a 400-point skill bought
nothing at all.

**Sparks are matched against the game's own factor table**, not a skill list, so
race and scenario sparks can be targeted at all.

**Dropped deliberately**, with reasons recorded in `uma_it/task.py`: the support
card level filter (its OCR read 150 for a card that caps at 50), the mid-career
skill threshold (there are no turns here), manual purchase pauses, and a
separate carat flag for rerolls.

The parent remains the place to look for anything this one does not do,
including normal-career play.

## Development

No test framework: 19 `check_*.py` scripts at the repo root drive real functions
with fakes and assert on the clicks and decisions they produce.

```bash
py -3.10 check_skills.py
```

Several were added after a bug reached the live game, and each states the
failure it exists to catch. Run them all before committing.

Screen handlers are best checked against real captures — grab a frame and run
the handler against the PNG with a fake controller:

```bash
deps/adb/adb.exe -s emulator-5554 exec-out screencap -p > shot.png
```

Such scripts must `os.chdir` to the repo root: templates resolve relative to the
working directory, and templates that fail to load silently make every screen
look unrecognised.

See [DESIGN.md](DESIGN.md) for how it is put together and which rules exist
because something once broke, and [STATUS.md](STATUS.md) for what is proven and
what is still open.

## Known limits

- **Agenda selection is always slot 1.** Copy the agenda you want there.
- **Normal-career play is not supported.** Use the parent project.
- **The dashboard has no authentication.**
- **Windows in practice** — the bundled ADB is `adb.exe` and the launcher is a
  `.bat`, though nothing in the bot logic is platform-specific.

## License

[MIT](LICENSE), covering this project's own code — everything under `uma_it/`,
`public/`, the check scripts, `main.py` and `device.py`.

**The engine under `bot/` is vendored** from
[UAT-Global-Server](https://github.com/mrhorseshoe/UAT-Global-Server), which
descends from
[TomerGamerTV/UAT-Global-Server](https://github.com/TomerGamerTV/UAT-Global-Server)
and an upstream CN project before that. **Neither of those repositories
publishes a license**, so the terms on that code are their authors' default
copyright, not MIT. If you intend to reuse `bot/`, take that up with them rather
than relying on this file.
