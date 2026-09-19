"""Team trials, run in the gaps between careers.

Independent Training costs 30 TP, and TP comes back at 1 per 10 minutes, so a
loop that keeps up with itself spends most of the day waiting. Team trials
spend **RP** instead - one per race, one back every 90 minutes, capped at 5 -
which this app has no other use for and which stops accruing once it caps. So
the wait is where they belong: never ahead of a career, only while one cannot
start. `tp_pending` on the task says a session is owed; the scheduler starts
the task for it, and the TP wait resumes when the RP runs out.

The flow is the parent project's, ported: an ordered list of "if this crop is
on screen, click there". Every template and coordinate is moved verbatim from
its `hook.py`, because they are calibrated against the live game and
re-cropping them is how this project's worst bugs were made.

Three things end a session:

* **`cant_tt`** - the game saying there is no RP left. The expected end.
* **A quiet spell.** Races are long and need no clicks, so silence is normal;
  silence for longer than any race means the flow is stuck on a screen the
  rules do not name. It ends rather than clicking on, because a stuck flow
  that keeps clicking is what the repetitive-click guard restarts the game
  over.
* **The session cap**, as a backstop on the whole thing.

While a session is running this claims every frame, matched or not. The career
handlers must not see these screens: the bot is on the Race tab, where their
click points mean other things.
"""
import os
import time

import cv2

import bot.base.log as logger
from bot.base.task import TaskStatus
from bot.recog.image_matcher import image_match
from bot.recog.ocr import ocr_line, find_similar_text

from uma_it.asset.point import (
    HOME_TAB,
    IT_MENU,
    RESTORE_NO,
    TT_BACK,
    TT_DONE,
    TT_ITEMS_SELECTED_OK,
    TT_NEXT_AFTER,
    TT_NEXT_RESULT,
    TT_RACE_TAB,
    TT_SEE_ALL,
    TT_SEE_RESULTS,
    TT_SELECT_OPPONENT,
    TT_TEAM_RACE,
    TT_TEAM_TRIALS,
)
from uma_it.asset.template import (
    REF_NEXT,
    REF_TT_CANT,
    REF_TT_CANT_2,
    REF_TT_HOME,
    REF_TT_NEXT_RESULT,
    REF_TT_SEE_ALL,
    REF_TT_SEE_RESULTS,
    REF_TT_SELECT_OPPONENT,
    REF_TT_TEAM_RACE,
    REF_TT_TEAM_TRIALS,
    REF_TT_TO_HOME,
    UI_INFO,
)
from uma_it.task import EndTaskReason

log = logger.get_logger(__name__)

# A race runs for a couple of minutes with nothing to click, so quiet is
# normal. Quiet for longer than a race is the flow stuck on an unnamed screen.
QUIET_LIMIT_SECONDS = 240
# A session starts where the declined TP prompt left the bot - the career start
# screens, not Home - and every rule starts from Home. Back walks out of them.
# Bounded: Back on Home itself does nothing useful, and a handler that keeps
# clicking one point is what the repetitive-click guard restarts the game over.
BACK_OUT_AFTER_SECONDS = 12
MAX_BACK_CLICKS = 6
# Presses of the bottom nav's Home tab when walking back at the end.
MAX_RETURN_CLICKS = 8
# Five RP is the cap, and a race plus its result screens runs a few minutes.
SESSION_LIMIT_SECONDS = 1500


# RP comes back one point every 90 minutes and caps at 5, so there is no sense
# looking more often than that - and a session always runs RP to zero, so the
# clock starts when it does. A little under 90 so it does not drift past the
# point where a career could have used the time.
RP_RETRY_SECONDS = 85 * 60
# Not worth leaving a career that is nearly done: the results flow would wait
# on the bot, and the RP will still be there in a few minutes.
MIN_CAREER_MINUTES_LEFT = 8


def active(ctx) -> bool:
    """True while a team trials session is running or owed.

    Two ways in. `tt_pending` on the task is a session owed across a restart -
    a TP wait asked for one. `tt_active` on the run context is a session
    running inside a career, where the bot leaves the countdown, spends its RP
    and comes back; that one must not survive a restart, because the career it
    belongs to does not.
    """
    return bool(getattr(getattr(ctx, 'career', None), 'tt_active', False)
                or getattr(_detail(ctx), 'tt_pending', False))


def _detail(ctx):
    """The task's settings, or None. Read defensively: every caller here is on
    a screen handler's path, and a handler that raises fails the career."""
    return getattr(getattr(ctx, 'task', None), 'detail', None)


def wanted(ctx) -> bool:
    """True when the task asks for team trials at all."""
    return bool(getattr(_detail(ctx), 'team_trials_while_waiting', False))


def due(ctx) -> bool:
    """True when RP has had time to build up since the last session.

    The game is the authority on how much RP there is - a session ends when it
    says there is none - so this only decides when it is worth asking.
    """
    if not wanted(ctx):
        return False
    last = getattr(_detail(ctx), 'tt_last_empty_at', 0) or 0
    return time.time() - last >= RP_RETRY_SECONDS


def begin_in_career(ctx):
    """Leave the countdown to spend RP, and come back to it afterwards.

    An Independent Training career runs in real time for about fifty minutes
    and the game does not need the bot present for any of it, so this is the
    cheapest RP in the loop. Nothing is clicked here: setting the flag hands
    the next frame to `run_frame`, and this handler must not click.
    """
    career = ctx.career
    career.tt_active = True
    career.tt_from_career = True
    career.tt_started_at = 0.0
    career.tt_back_clicks = 0
    career.tt_raced = False
    log.info("🏁 Career is running itself - going to spend RP on team trials")


def _next_sequence(ctx):
    """The results "Next" button, then the confirm that follows it.

    Clicked where it was found rather than at a fixed point: this one moves
    with the result screen it belongs to.
    """
    img = ctx.ctrl.get_screen(to_gray=True)
    found = image_match(img, REF_NEXT)
    if found.find_match:
        ctx.ctrl.click(found.center_point[0], found.center_point[1], "Team trials - Next")
    else:
        ctx.ctrl.click_by_point(TT_NEXT_RESULT)
    time.sleep(0.7)
    ctx.ctrl.click_by_point(TT_NEXT_AFTER)


def _finish(ctx, why: str):
    """Start walking back to Home; `_hand_back` ends the session there.

    Never hand back where the session happens to end. The Race tab's screens
    have no templates in this app, so the ordinary handlers see nothing they
    know and fall through to the blind fallback, which clicks a corner. On
    19 Sep that ran for **five hours**: one click every second or so, the
    repetitive-click guard restarting the game every seventeen seconds, and the
    career finishing unattended. The daily reset dialog was what finally
    dislodged it. So the session is over only once Home is on screen.
    """
    career = ctx.career
    started = getattr(career, 'tt_started_at', 0) or time.time()
    # Whatever ended it, RP is either spent or unreachable; either way there is
    # no point asking again before it has had time to come back.
    ctx.task.detail.tt_last_empty_at = int(time.time())
    career.tt_returning = True
    career.tt_return_clicks = 0
    career.tt_finish_reason = f"{why} after {round((time.time() - started) / 60)} min"
    log.info(f"🏁 Team trials done ({why}) - heading back to Home")
    # A session that ends without the game saying no was looking at something
    # the rules do not name. Keep the frame: on 19 Sep one sat four minutes on
    # a screen nobody can now identify, because nothing captured it.
    if not why.startswith("out of RP"):
        _save_debug(ctx, "unrecognised")


def _hand_back(ctx, why: str):
    """Home is on screen: give the frames back to the ordinary handlers."""
    career = ctx.career
    detail = ctx.task.detail
    reason = getattr(career, 'tt_finish_reason', '') or 'done'
    career.tt_active = False
    career.tt_returning = False
    career.tt_from_career = False
    career.tt_started_at = 0.0
    career.tt_back_clicks = 0
    career.tt_return_clicks = 0
    career.tt_raced = False
    if detail.tt_pending:
        detail.tt_pending = False
        log.info(f"🏁 Team trials over ({reason}; {why})")
        ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.TEAM_TRIALS_DONE)
        return
    log.info(f"🏁 Team trials over ({reason}; {why}) - back to the career")


def _save_debug(ctx, tag: str):
    """Keep the frame a session gave up on, the way spark reroll does."""
    try:
        os.makedirs('screenshot/team_trials', exist_ok=True)
        cv2.imwrite(f'screenshot/team_trials/{time.strftime("%Y%m%d_%H%M%S")}_{tag}.png',
                    ctx.ctrl.get_screen())
    except Exception as e:
        log.debug(f"team trials capture failed: {e}")


def _to_home(ctx):
    """"To Home" on the countdown screen's menu, clicked where it was found.

    Never a fixed point: "Give Up" sits beside it on the same dialog and
    abandons the career. Matching the button is what keeps a stray coordinate
    from costing a run.
    """
    img = ctx.ctrl.get_screen(to_gray=True)
    found = image_match(img, REF_TT_TO_HOME)
    if not found.find_match:
        return
    log.info("Team trials: leaving the career to its countdown (To Home)")
    ctx.ctrl.click(found.center_point[0], found.center_point[1], "Team trials - To Home")


def _out_of_rp(ctx):
    """The game says there is no RP left: leave the screen and end the session."""
    ctx.ctrl.click_by_point(TT_DONE)
    time.sleep(1)
    ctx.ctrl.click_by_point(TT_DONE)
    _finish(ctx, "out of RP")


# The dialog body, below its header. Same geometry the dialog router reads.
BODY_REGION = (560, 700, 30, 690)       # y1, y2, x1, x2


def _decline_rp_restore(ctx):
    """"Not enough RP. Do you want to restore RP?" - No, and the session is over.

    This, not the parent's `cant_tt` crop, is how the game says RP has run out
    on this version: measured 19 Sep, the crop never matched and the session
    sat on this dialog until the quiet limit. Answering No costs nothing; RP is
    not worth carats, and the next session is an hour and a half away anyway.
    """
    log.info("Team trials: the game says RP has run out - declining the restore")
    ctx.ctrl.click_by_point(RESTORE_NO)
    time.sleep(1)
    _finish(ctx, "out of RP")


def is_rp_prompt(body: str) -> bool:
    """True for the RP restore prompt, false for the TP one.

    They are one dialog title apart - both are 'Confirm' - and the TP handler
    read this one as its own on 19 Sep: it declined, then held the loop for
    half an hour over RP, with a career still running.
    """
    text = (body or '').lower()
    return 'rp' in text and 'tp' not in text


# Ordered: the first crop found on the frame decides the click. Out-of-RP comes
# first so a session ends rather than starting another race it cannot pay for.
RULES = [
    ("no RP left", REF_TT_CANT, _out_of_rp),
    ("no RP left (2)", REF_TT_CANT_2, _out_of_rp),
    ("the training menu", REF_TT_TO_HOME, _to_home),
    ("Home", REF_TT_HOME, TT_RACE_TAB),
    ("the Race tab", REF_TT_TEAM_TRIALS, TT_TEAM_TRIALS),
    ("Team Trials", REF_TT_TEAM_RACE, TT_TEAM_RACE),
    ("the opponent list", REF_TT_SELECT_OPPONENT, TT_SELECT_OPPONENT),
    ("the race screen", REF_TT_SEE_ALL, TT_SEE_ALL),
    ("a Next button", REF_NEXT, _next_sequence),
    ("the results", REF_TT_SEE_RESULTS, TT_SEE_RESULTS),
    ("the team result", REF_TT_NEXT_RESULT, TT_NEXT_RESULT),
]

# Dialogs that can land on this path. The router in dialogs.py never sees them
# during a session - this claims the frame first - so the two that need a click
# are named here.
TITLE_RULES = [("Items Selected", TT_ITEMS_SELECTED_OK)]


def run_frame(ctx) -> bool:
    """Drive one frame of a team trials session. True once it has claimed it.

    Always True while a session is live, even on a frame nothing matched: the
    career handlers must not act on these screens.
    """
    career = ctx.career
    now = time.time()
    if not getattr(career, 'tt_started_at', 0):
        career.tt_started_at = now
        career.tt_last_action_at = now
        where = "while the career runs itself" if getattr(career, 'tt_from_career', False) \
            else "while the loop waits for TP"
        log.info(f"🏁 Team trials: spending RP {where}")

    img = ctx.ctrl.get_screen(to_gray=True)

    # Walking back to Home after the session ended. Bounded: if the Home tab
    # does not get there, hand back anyway rather than click on forever.
    if getattr(career, 'tt_returning', False):
        try:
            if image_match(img, REF_TT_HOME).find_match:
                _hand_back(ctx, "Home reached")
                return True
        except Exception:
            pass
        clicks = getattr(career, 'tt_return_clicks', 0)
        if clicks >= MAX_RETURN_CLICKS:
            _hand_back(ctx, f"gave up after {clicks} Home presses")
            return True
        career.tt_return_clicks = clicks + 1
        career.tt_last_action_at = now
        ctx.ctrl.click_by_point(HOME_TAB)
        time.sleep(1.5)
        return True

    for name, template, action in RULES:
        try:
            if not image_match(img, template).find_match:
                continue
        except Exception as e:
            log.debug(f"team trials: {name} match failed: {e}")
            continue
        # One line per screen the session recognises. Without them a session
        # that does nothing looks identical to one that raced: on 19 Sep four
        # minutes of silence could have been any step of the flow.
        log.info(f"Team trials: on {name}")
        career.tt_last_action_at = now
        # Past Home, so Back is no longer the way out of anything: the rules
        # know these screens, and backing out of a race would lose it.
        career.tt_raced = True
        if callable(action):
            action(ctx)
        else:
            ctx.ctrl.click_by_point(action)
        return True

    title = _read_title(ctx, img) if TITLE_RULES else ''
    if title and find_similar_text(title, ['Confirm'], 0.8) == 'Confirm':
        y1, y2, x1, x2 = BODY_REGION
        body = ''
        try:
            body = (ocr_line(img[y1:y2, x1:x2]) or '').strip()
        except Exception:
            pass
        if is_rp_prompt(body):
            career.tt_last_action_at = now
            _decline_rp_restore(ctx)
            return True
        if 'tp' in body.lower():
            # The TP prompt, left over from a career that could not start. It
            # is modal, so nothing here can proceed until it is gone - and
            # spending on TP is never this session's business.
            career.tt_last_action_at = now
            log.info("Team trials: clearing the TP restore prompt")
            ctx.ctrl.click_by_point(RESTORE_NO)
            time.sleep(1)
            return True
    for name, point in TITLE_RULES:
        if title and find_similar_text(title, [name], 0.8) == name:
            career.tt_last_action_at = now
            log.info(f"Team trials: clearing {name!r}")
            ctx.ctrl.click_by_point(point)
            return True

    quiet = now - (getattr(career, 'tt_last_action_at', now) or now)
    if quiet > BACK_OUT_AFTER_SECONDS and not getattr(career, 'tt_raced', False):
        backs = getattr(career, 'tt_back_clicks', 0)
        if backs < MAX_BACK_CLICKS:
            career.tt_back_clicks = backs + 1
            career.tt_last_action_at = now
            # Two ways out, by where the session began. A career sits on the
            # countdown, which has no Back at all - only the menu, and then the
            # matched "To Home" above. A TP wait leaves the bot on the career
            # start screens, which do.
            if getattr(career, 'tt_from_career', False):
                log.info(f"Team trials: opening the training menu ({backs + 1})")
                ctx.ctrl.click_by_point(IT_MENU)
            else:
                log.info(f"Team trials: not on Home yet - backing out ({backs + 1})")
                ctx.ctrl.click_by_point(TT_BACK)
            return True
    if quiet > QUIET_LIMIT_SECONDS:
        _finish(ctx, f"nothing recognised for {round(quiet / 60)} min")
    elif now - career.tt_started_at > SESSION_LIMIT_SECONDS:
        _finish(ctx, "session ran long")
    return True


def _read_title(ctx, img) -> str:
    """The dialog title on this frame, or '' when there is no dialog."""
    try:
        found = image_match(img, UI_INFO)
        if not found.find_match:
            return ''
        pos = found.matched_area
        crop = img[pos[0][1] - 5:pos[1][1] + 5, pos[0][0] + 150:pos[1][0] + 405]
        return (ocr_line(crop) or '').strip()
    except Exception:
        return ''
