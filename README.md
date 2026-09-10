# Uma-IT

A streamlined bot that loops **Independent Training** careers in Umamusume:
Pretty Derby (Global).

Independent Training is the mode where the game plays a career itself: you
configure the run, start it, and collect the result about fifty minutes later.
This bot does that on a loop — enter a career, load the race agenda, wait out
the run, collect the result, start the next one — and deliberately does nothing
else.

There is no game API. Everything is OpenCV template matching and PaddleOCR over
screenshots, with taps sent through uiautomator2 over ADB.

## Status

Runnable, unproven. Every screen on the path has a handler bar the two optional
features, and eleven check scripts cover the decisions. What has not happened
is a career: the career-start path has never faced the live game, and running
one needs TP the account does not currently have.

See [STATUS.md](STATUS.md) for the checklist and what is still open, and
[DESIGN.md](DESIGN.md) for how the thing is put together and which rules exist
because something once broke.

## Running it

Double-click `start.bat`, or:

```bash
py -3.10 main.py
```

It must be `py -3.10`, not `python`. The packages live in system Python 3.10's
site-packages, and a plain `python` picks up whatever is first on PATH - which
fails at `import cv2` with a message that says nothing about why. `start.bat`
handles that, and says so plainly if 3.10 is missing.

Pick the emulator when asked; the dashboard opens on http://127.0.0.1:8071.
It is a single HTML file with no build step - edit `public/index.html` and
reload.

**Starting the process starts the loop.** If a saved task restores and there is
no recorded scheduler state, the scheduler starts - which is what lets the loop
survive the soft restart it performs after every career. To restart without
running a career, stop it from the dashboard once it is up.

## Relationship to UAT-Global-Server

This is a fresh, much smaller project rather than a fork. The parent project
automates a turn-by-turn career — training choices, races, events, skills — and
Independent Training makes almost all of that unnecessary. An IT career touches
22 of its 56 screens and 28 of its 574 template images.

The parent project remains the place to look for anything this one does not do,
including normal-career play.

## Requirements

- Python 3.10 (`py -3.10`)
- An Android emulator at 720x1280 reachable over ADB
