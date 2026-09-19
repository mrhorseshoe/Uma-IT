"""Restoring TP, which is the only thing this app spends on purpose.

Independent Training costs 30 TP and regenerates far slower than a ~50 minute
career consumes it, so a loop left running eventually runs the account dry. The
game then offers to restore TP - from a TP item if one is held, otherwise from
carats.

`allow_recover_tp` is the single authority for whether that happens. At 0 a
career fails rather than being paid for; above 0 this flow runs, and it can
spend carats. It governs the spark reroll's TP prompt too - the parent has a
second flag for that, and one switch the user can find beats two that have to
agree.

The flow is a state machine across screens, one step per frame, because the
executor calls a handler once per frame: the prompt, then the selection screen,
then a confirm, then a result to close. Each step recognises its own screen, so
arriving part-way through - after a restart, say - still works.

One inherited rule kept deliberately: **never spend a chocolate TP item.**
Those are event items people keep, and carats are the cheaper thing to lose.
"""
import re
import time

import bot.base.log as logger
from bot.recog.image_matcher import image_match
from bot.recog.ocr import ocr_line

from uma_it.asset.point import (
    TO_RECOVER_TP,
    USE_TP_DRINK,
    USE_CARROT_RECOVER_TP,
    USE_TP_DRINK_CONFIRM,
    USE_CARROT_RECOVER_TP_ADD,
    USE_CARROT_RECOVER_CONFIRM,
    USE_TP_DRINK_RESULT_CLOSE,
)
from uma_it.asset.template import (
    REF_RECOVER_TP_1,
    REF_RECOVER_TP_2,
    REF_RECOVER_TP_2_CARROT,
    REF_RECOVER_TP_3,
    REF_RECOVER_TP_3_CARROT,
    REF_TP_RECOVER_DRINK,
)
from uma_it.parse import find_green_button

log = logger.get_logger(__name__)

# The row naming the offered TP item on the selection screen.
ITEM_ROW_REGION = (293, 352, 80, 545)     # y1, y2, x1, x2

# How many frames the whole flow may take. Without a bound, a screen it does
# not recognise would be retried until the click guard restarts the game.
MAX_STEPS = 10


def allowed(ctx) -> bool:
    """True when the task authorises restoring TP at all."""
    return bool(getattr(ctx.task.detail, 'allow_recover_tp', 0))


# TP comes back a point at a time, and a career needs 30. The wait is sized
# from what the game says is missing, then re-checked rather than trusted: too
# short costs one screen visit, too long costs careers. Hence the half-hour
# cap, and a floor so a retry cannot spin.
TP_REGEN_SECONDS = 600
MIN_WAIT_SECONDS = 300
MAX_WAIT_SECONDS = 1800


def shortfall(body_text: str) -> int:
    """The TP the prompt says is missing, or 0 when it does not say.

    The game writes "You need 2 more TP to start a Career Scenario", usually
    followed by a second, larger figure for Event Boost - which this app never
    uses, so only the first number counts.
    """
    m = re.search(r'need\s*(\d+)\s*more\s*tp', (body_text or '').lower())
    return int(m.group(1)) if m else 0


def wait_seconds(missing: int) -> int:
    """How long to hold the loop when `missing` TP are needed."""
    if missing <= 0:
        return MAX_WAIT_SECONDS
    return max(MIN_WAIT_SECONDS,
               min(MAX_WAIT_SECONDS, missing * TP_REGEN_SECONDS + 60))


def step(ctx, body_text: str = '', header_pos=None) -> bool:
    """Advance the TP restore by one screen. False when it gave up.

    Returns True whenever it acted, so the caller can leave the rest of the
    frame alone. A False means the caller should decline whatever it was doing
    - fail the career, or keep the original sparks.

    `body_text` is matched in lower case. Every test below was written against
    a caller that passed '', so the case never came up until one started
    passing the real OCR; the game writes "restore TP?", and both careers of
    the 11 Sep 01:16 run failed in fifteen seconds on the mismatch.
    """
    body_text = (body_text or '').lower()
    career = getattr(ctx, 'career', None)
    tries = getattr(career, 'tp_recover_tries', 0) + 1
    if career is not None:
        career.tp_recover_tries = tries
    if tries > MAX_STEPS:
        log.warning(f"TP restore has not completed in {MAX_STEPS} steps - giving up")
        return False

    screen = ctx.ctrl.get_screen(to_gray=True)

    # 1. the selection screen: a TP item if there is a suitable one, else carats
    if image_match(screen, REF_RECOVER_TP_1).find_match:
        y1, y2, x1, x2 = ITEM_ROW_REGION
        item_row = (ocr_line(screen[y1:y2, x1:x2]) or '').lower()
        chocolate = 'choc' in item_row or 'choc' in (body_text or '')
        if image_match(screen, REF_TP_RECOVER_DRINK).find_match and not chocolate:
            log.info(f"Restoring TP with a TP item ({item_row.strip()[:40]!r})")
            ctx.ctrl.click_by_point(USE_TP_DRINK)
        else:
            why = "chocolate item kept" if chocolate else "no TP item held"
            log.info(f"Restoring TP with carats ({why})")
            ctx.ctrl.click_by_point(USE_CARROT_RECOVER_TP)
        time.sleep(1)
        return True

    # 2. the confirms - the item and carat paths have different ones
    if image_match(screen, REF_RECOVER_TP_2).find_match:
        ctx.ctrl.click_by_point(USE_TP_DRINK_CONFIRM)
        time.sleep(1)
        return True
    if image_match(screen, REF_RECOVER_TP_2_CARROT).find_match:
        ctx.ctrl.click_by_point(USE_CARROT_RECOVER_TP_ADD)
        time.sleep(2)
        ctx.ctrl.click_by_point(USE_CARROT_RECOVER_CONFIRM)
        time.sleep(1)
        return True

    # 3. the result, either way
    if (image_match(screen, REF_RECOVER_TP_3).find_match
            or image_match(screen, REF_RECOVER_TP_3_CARROT).find_match):
        log.info("TP restored")
        if career is not None:
            career.tp_recover_tries = 0
        ctx.ctrl.click_by_point(USE_TP_DRINK_RESULT_CLOSE)
        time.sleep(1)
        return True

    # 4. otherwise this is the compact "You need N more TP. Restore TP?" prompt
    if not body_text or 'restore tp' in body_text or 'more tp' in body_text:
        spot = None
        if header_pos is not None:
            spot = find_green_button(ctx.current_screen, 70, header_pos[1][1], 660, 1270)
        if spot:
            log.info("Accepting the TP restore prompt")
            ctx.ctrl.click(spot[0], spot[1], "Restore TP")
        else:
            ctx.ctrl.click_by_point(TO_RECOVER_TP)
        time.sleep(1)
        return True

    return False
