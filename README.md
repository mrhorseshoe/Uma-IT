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

Early. The engine, the calibrated screen assets and the dialog title table are
in place and verified; the handlers are being written. See
[STATUS.md](STATUS.md) for the checklist and [DESIGN.md](DESIGN.md) for how the
thing is put together and which rules exist because something once broke.

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
