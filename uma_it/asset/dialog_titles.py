"""Dialog titles, and why the ones this app never handles are still here.

Dialogs are dispatched by their OCR'd title, fuzzy-matched. The matching is
only safe when a title is scored against *every* title the game can show on
this path - not only the ones with actions.

The failure it prevents is not subtle. `'Confirmation'` scores 0.800 against
`'Final Confirmation'` and 0.828 against `'Skip Confirmation'`. Scored against
a table holding only titles we act on, our `'Confirmation'` entry wins the
career-start dialog and taps a skill-confirm point at it - and no career ever
starts. Scored against the full list, `'Final Confirmation'` matches itself at
1.0 and wins its own frame.

So DISTRACTOR_TITLES earns its place by losing. Every entry is a real dialog
title from the original project that this app has no reason to act on; they are
kept so that a frame showing one of them cannot be mistaken for a frame we do
act on. Deleting an entry here is not a cleanup - it re-opens that collision.

Generated from the original project's TITLE table; do not hand-edit to trim.
"""

# Titles this app dispatches on. Kept as data for the collision check below;
# the actions live in uma_it/dialogs.py.
OWNED_TITLES = [
    'Perks',
    'Borrow Card',
    'Follow Trainer',
    'Notices',
    'Career Complete',
    'Complete Career',
    'Training Complete',
    'Umamusume Details',
    'Confirmation',
    'Rewards Collected',
    'Event Story Unlocked',
    'Final Confirmation',
    'Independent Training',
    'Choose Career Mode',
    'Start Event',
    'Agenda',
    'My Agendas',
    'Overwrite',
    'Network Error',
    'Connection Error',
    'Data Update',
    'Data Download',
    'Date Changed',
]

"""Titles carried purely so they win their own frames. See the module
docstring - these are load-bearing precisely because nothing acts on them."""
DISTRACTOR_TITLES = [
    'Race Details',
    'Rest & Outing Confirmation',
    'Rest & Recreation',
    'Try Again',
    'Earned Title',
    'Quick Mode Settings',
    'Recreation',
    'Skills Learned',
    'Fan Count Below Target Race Requirement',
    'Outing',
    'Skip Confirmation',
    'Rest',
    'Race Recommendations',
    'Tactics',
    'Strategy',
    'Goal Not Reached',
    'Insufficient Fans',
    'Warning',
    'Infirmary',
    'Gift Box',
    'Collection Successful',
    'Character Story Unlocked',
    'Skill Acquisition Confirmation',
    'Successfully Acquired Skill',
    'Target Achievement Count Insufficient',
    'Confirm',
    'Recover TP',
    'Factor Confirmation',
    'New Difficulty Unlocked',
    'Auto Formation',
    'Battle Confirmation',
    'Unmet Requirements',
    'Items Selected',
    'Auto Select',
    'Session Error',
    'areer Playthrough Difficulty Se',
]

# The set every OCR'd title is scored against. Build it from both lists,
# always - see the module docstring for what happens otherwise.
ALL_TITLES = OWNED_TITLES + DISTRACTOR_TITLES
