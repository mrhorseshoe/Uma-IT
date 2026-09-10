"""Every title this app acts on must win its own frame.

This is the invariant that keeps `'Confirmation'` from swallowing the career
start dialog. Run it after adding or renaming any title. See
uma_it/asset/dialog_titles.py for why the distractors are there.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from bot.recog.ocr import find_similar_text
from uma_it.asset.dialog_titles import OWNED_TITLES, DISTRACTOR_TITLES, ALL_TITLES
from uma_it.dialogs import DIALOGS

THRESHOLD = 0.8

print(f"owned {len(OWNED_TITLES)}  distractors {len(DISTRACTOR_TITLES)}  "
      f"scoring set {len(ALL_TITLES)}")

# The list and the table are separate so dialog_titles.py can stay
# import-free, which means they can drift. A title in the table but not the
# list can never win a frame - it is not scored against - so its handler would
# simply never run, silently.
drift_missing = sorted(set(DIALOGS) - set(OWNED_TITLES))
drift_extra = sorted(set(OWNED_TITLES) - set(DIALOGS))
print(f"titles with a handler in dialogs.py : {len(DIALOGS)}")
if drift_missing:
    print(f"    in DIALOGS but unscored: {drift_missing}")
if drift_extra:
    print(f"    listed as owned but no handler: {drift_extra}")

bad = bool(drift_missing or drift_extra)

# 1. a clean read of one of our titles must resolve to itself
losers = []
for t in OWNED_TITLES:
    got = find_similar_text(t, ALL_TITLES, THRESHOLD)
    if got != t:
        losers.append((t, got))

# 2. a clean read of a distractor must NOT resolve to one of ours
stolen = []
for t in DISTRACTOR_TITLES:
    got = find_similar_text(t, ALL_TITLES, THRESHOLD)
    if got in OWNED_TITLES:
        stolen.append((t, got))

print(f"owned titles losing their own frame : {len(losers)}")
for a, b in losers:
    print(f"    {a!r} -> {b!r}")
print(f"distractors wrongly taken by us     : {len(stolen)}")
for a, b in stolen:
    print(f"    {a!r} -> {b!r}")

# 3. the specific pair this project paid for
pair = find_similar_text('Final Confirmation', ALL_TITLES, THRESHOLD)
print(f"'Final Confirmation' resolves to     : {pair!r}"
      f"  {'OK' if pair == 'Final Confirmation' else 'BROKEN'}")

if bad:
    print("OWNED_TITLES and dialogs.DIALOGS have drifted apart")

sys.exit(1 if (losers or stolen or bad or pair != 'Final Confirmation') else 0)
