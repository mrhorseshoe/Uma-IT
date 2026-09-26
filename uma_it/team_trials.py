"""Team trials, run between careers.

Independent Training costs 30 TP, and TP comes back at 1 per 10 minutes, so a
loop that keeps up with itself spends most of the day waiting. Team trials
spend **RP** instead - one per race, one back every 90 minutes, capped at 5 -
which this app has no other use for and which stops accruing once it caps.

A session runs **between careers, never inside one**: the loop spends whatever
RP has built up, and only then starts the next career. There used to be a
second path that left a running career on its countdown to spend RP mid-run.
It worked, but at 90 minutes a point RP simply does not build up fast enough
for a career-length gap to be worth interrupting anything for, and it was the
half of this module with all the sharp edges - a way out of the countdown
screen, a way back in, and career state that had to survive both.

`tt_pending` on the task says a session is owed. It is set before a career
starts and by a TP wait, both of which are the loop standing still; the
scheduler starts the task for it, and whatever was holding the loop back is
still holding it when the RP runs out.

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
    UI_GAME_LOADING,
    UI_GAME_TITLE,
    UI_INDEPENDENT_TRAINING_WAIT,
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
# point where a career could have used the time. A career is about 50 minutes,
# so in practice this is a session every second loop, which is the rate RP
# accrues at anyway.
RP_RETRY_SECONDS = 85 * 60


def active(ctx) -> bool:
    """True while a team trials session is owed or running.

    One way in: `tt_pending` on the task, which is durable, because the
    process soft-restarts between runs and a session that lost its flag would
    hand the frames straight back to the career handlers.
    """
    return bool(getattr(_detail(ctx), 'tt_pending', False))


def _detail(ctx):
    """The task's settings, or None. Read defensively: every caller here is on
    a screen handler's path, and a handler that raises fails the career."""
    return getattr(getattr(ctx, 'task', None), 'detail', None)


def wanted(ctx) -> bool:
    """True when the task asks for team trials at all."""
    return bool(getattr(_detail(ctx), 'team_trials_while_waiting', False))


def due(ctx) -> bool:
    """True when RP has had time to build up since the last session."""
    return due_for(_detail(ctx))


def due_for(detail) -> bool:
    """Same, from the task's settings alone.

    Taken apart from `due` so `UmaItTask.start_task` can ask before a career
    without building a context to ask with.

    The game is the authority on how much RP there is - a session ends when it
    says there is none - so this only decides when it is worth walking to the
    Race tab to find out. Without it the loop would make that trip before
    every career, and most of them would be told there is no RP.
    """
    if not bool(getattr(detail, 'team_trials_while_waiting', False)):
        return False
    last = getattr(detail, 'tt_last_empty_at', 0) or 0
    return time.time() - last >= RP_RETRY_SECONDS


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


def _stand_down(ctx, why: str):
    """Drop the session without ending the run, and let the frame fall through.

    The one case this exists for: a run begins with a career already pending
    in-game - after a watchdog restart, say - so the first screen the session
    sees is the countdown. A session must never interrupt a running career, and
    it cannot walk out of that screen either (the countdown has no Back and no
    bottom nav), so the only right answer is to stop being a session. The
    career handlers take the frame, the career finishes, and the RP is still
    there for the next loop.
    """
    career = ctx.career
    career.tt_started_at = 0.0
    career.tt_last_action_at = 0.0
    career.tt_back_clicks = 0
    career.tt_return_clicks = 0
    career.tt_returning = False
    career.tt_raced = False
    career.tt_in_flow = False
    ctx.task.detail.tt_pending = False
    log.info(f"🏁 Team trials stood down ({why}) - the RP keeps until next time")


def _hand_back(ctx, why: str):
    """Home is on screen: the session is over, and so is this run.

    Ending the run rather than carrying on from Home is what makes the session
    a thing that happens *between* careers. The scheduler starts the task again
    immediately; `tt_pending` is clear by then, so that start is the career -
    unless a TP wait is still outstanding, which `start_task` leaves standing.
    """
    career = ctx.career
    detail = ctx.task.detail
    reason = getattr(career, 'tt_finish_reason', '') or 'done'
    career.tt_returning = False
    career.tt_started_at = 0.0
    career.tt_back_clicks = 0
    career.tt_return_clicks = 0
    career.tt_raced = False
    career.tt_in_flow = False
    detail.tt_pending = False
    log.info(f"🏁 Team trials over ({reason}; {why})")
    ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.TEAM_TRIALS_DONE)


def _save_debug(ctx, tag: str) -> str:
    """Keep the frame a session gave up on, the way spark reroll does.

    Returns the path written, or '' when the capture failed.
    """
    try:
        os.makedirs('screenshot/team_trials', exist_ok=True)
        path = f'screenshot/team_trials/{time.strftime("%Y%m%d_%H%M%S")}_{tag}.png'
        cv2.imwrite(path, ctx.ctrl.get_screen())
        return path
    except Exception as e:
        log.debug(f"team trials capture failed: {e}")
        return ''


# A session that has recognised nothing for this long is photographed once,
# while the screen is still the one it is stuck on. It has to come before the
# watchdog, which restarts the game after 90 seconds of a still screen - on
# 26 Sep at 02:41 a session stalled after a race, the watchdog restarted the
# game, and the only capture the session makes, at its four-minute quiet
# limit, never happened. So nobody knows what that screen was.
STUCK_CAPTURE_SECONDS = 45
# Per process, which restarts after every run: enough to identify a screen.
MAX_STUCK_CAPTURES = 3
_stuck_captures = 0


def _capture_stuck(ctx, quiet: float):
    """Photograph the screen a session is stuck on, once per quiet spell."""
    global _stuck_captures
    career = ctx.career
    if _stuck_captures >= MAX_STUCK_CAPTURES:
        return
    # Once per spell: an action since the last capture starts a new one.
    if getattr(career, 'tt_stuck_captured_at', 0.0) >= getattr(career, 'tt_last_action_at', 0.0):
        return
    career.tt_stuck_captured_at = time.time()
    _stuck_captures += 1
    path = _save_debug(ctx, "stuck")
    if path:
        log.info(f"Team trials: nothing recognised for {round(quiet)}s - kept the screen at {path}")


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
    ("Home", REF_TT_HOME, TT_RACE_TAB),
    ("the Race tab", REF_TT_TEAM_TRIALS, TT_TEAM_TRIALS),
    ("Team Trials", REF_TT_TEAM_RACE, TT_TEAM_RACE),
    ("the opponent list", REF_TT_SELECT_OPPONENT, TT_SELECT_OPPONENT),
    ("the race screen", REF_TT_SEE_ALL, TT_SEE_ALL),
    ("a Next button", REF_NEXT, _next_sequence),
    ("the results", REF_TT_SEE_RESULTS, TT_SEE_RESULTS),
    ("the team result", REF_TT_NEXT_RESULT, TT_NEXT_RESULT),
]

# Screens that exist only inside team trials. Seeing one means the session is
# in its own flow.
ENTERS_FLOW = {"the Race tab", "Team Trials", "the opponent list",
               "the race screen", "the results", "the team result"}
# Rules that are only safe once it is. REF_NEXT is a crop of a generic green
# Next button, and the career setup screens have one too: on 25 Sep a session
# that began on Support Formation matched it at 16:48:10, pressed Next into the
# career setup, and - because any match also stopped the Back budget - had no
# way out. The screen went still and the watchdog restarted the game. Inside
# the flow the same rule is what gets through the race results.
FLOW_ONLY = {"a Next button"}

def _carat_pack(ctx):
    """Decline the Daily Carat Pack through the router's own handler."""
    from uma_it.dialogs import decline_carat_pack
    decline_carat_pack(ctx)


def _daily_sale(ctx):
    """Decline the shop offer, through the router's own handler.

    Imported here rather than at module scope because dialogs.py imports this
    module; the call is what keeps one implementation of "Cancel" instead of a
    second copy that drifts.
    """
    from uma_it.dialogs import decline_daily_sale
    decline_daily_sale(ctx)


# Dialogs that can land on this path. The router in dialogs.py never sees them
# during a session - this claims the frame first - so the ones that need a
# click are named here. An entry is a fixed point or an action, like RULES.
#
# 'Daily Sale' is here because of 20 Sep: it appeared mid-session, no rule
# matched it, and a session that recognises nothing clicks nothing. The quiet
# limit would have ended the session after four minutes, but the 30s watchdog
# reached three strikes at ninety seconds and restarted the game first.
TITLE_RULES = [("Items Selected", TT_ITEMS_SELECTED_OK),
               ("Daily Sale", _daily_sale),
               ("Daily Carat Pack", _carat_pack)]


def run_frame(ctx) -> bool:
    """Drive one frame of a team trials session. True once it has claimed it.

    True on every frame while a session is live, even one nothing matched: the
    career handlers must not act on these screens. The single exception is a
    session that stands down - see `_stand_down` - which hands the frame back
    by returning False.
    """
    career = ctx.career
    now = time.time()
    img = ctx.ctrl.get_screen(to_gray=True)

    # Never interrupt a career. A session has no way off the countdown screen
    # anyway - no Back, no bottom nav - so one that started in front of one
    # would click at it until the quiet limit and hand back having done
    # nothing. Checked only before the session has raced: afterwards this
    # screen cannot be what is on show.
    if not getattr(career, 'tt_raced', False) and not getattr(career, 'tt_returning', False):
        try:
            if image_match(img, UI_INDEPENDENT_TRAINING_WAIT).find_match:
                _stand_down(ctx, "a career is already running")
                return False
        except Exception as e:
            log.debug(f"team trials: countdown check failed: {e}")

    # The title screen under a session means the game restarted - the
    # watchdog did it at 11:02 on 25 Sep, during the daily reset. Whatever the
    # session was doing is gone, and the title needs a tap a session never
    # gives it, so the session stands down and keeps the RP for the next loop.
    #
    # The loading screen does *not* mean that. The game shows "Now Loading" on
    # its own scene changes, including Race tab -> Team Trials: at 17:54:38 on
    # 25 Sep a session stood down 1.7 seconds after reaching the Race tab,
    # left the ordinary handlers on the Team Trials page they do not know, and
    # the click guard reopened the game three times. So a loading screen is
    # waited out - nothing clicked, and not counted as the session going quiet.
    try:
        if image_match(img, UI_GAME_TITLE).find_match:
            _stand_down(ctx, "the game restarted under the session")
            return False
        if image_match(img, UI_GAME_LOADING).find_match:
            career.tt_last_action_at = now
            time.sleep(1)
            return True
    except Exception as e:
        log.debug(f"team trials: launch-screen check failed: {e}")

    if not getattr(career, 'tt_started_at', 0):
        career.tt_started_at = now
        career.tt_last_action_at = now
        log.info("🏁 Team trials: spending RP before the next career")

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
        if name in FLOW_ONLY and not getattr(career, 'tt_in_flow', False):
            continue
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
        if name in ENTERS_FLOW:
            career.tt_in_flow = True
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
    for name, action in TITLE_RULES:
        if title and find_similar_text(title, [name], 0.8) == name:
            career.tt_last_action_at = now
            log.info(f"Team trials: clearing {name!r}")
            if callable(action):
                action(ctx)
            else:
                ctx.ctrl.click_by_point(action)
            return True

    if title and _route_dialog(ctx, title):
        career.tt_last_action_at = now
        return True

    quiet = now - (getattr(career, 'tt_last_action_at', now) or now)
    if quiet >= STUCK_CAPTURE_SECONDS:
        _capture_stuck(ctx, quiet)
    if quiet > BACK_OUT_AFTER_SECONDS and not getattr(career, 'tt_raced', False):
        backs = getattr(career, 'tt_back_clicks', 0)
        if backs < MAX_BACK_CLICKS:
            career.tt_back_clicks = backs + 1
            career.tt_last_action_at = now
            # A session begins wherever the loop was standing still - Home
            # after a finished career, or the career start screens when a
            # declined TP prompt left the bot there. Back walks out of both.
            log.info(f"Team trials: not on Home yet - backing out ({backs + 1})")
            ctx.ctrl.click_by_point(TT_BACK)
            return True
        # Back is spent and not one screen has been recognised since the
        # session began, so this is not a place a session can work from - most
        # often the game is still coming up. Standing down hands the frames to
        # the ordinary handlers, which know how to reach Home, and keeps the
        # RP for the next loop.
        #
        # Waiting the quiet limit out instead cost 5.5 minutes on 24 Sep: six
        # clicks at a loading screen, then four minutes of silence, during
        # which the watchdog found the screen frozen and restarted the game.
        _stand_down(ctx, "nothing recognised and Back did not reach Home")
        return False
    if quiet > QUIET_LIMIT_SECONDS:
        _finish(ctx, f"nothing recognised for {round(quiet / 60)} min")
    elif now - career.tt_started_at > SESSION_LIMIT_SECONDS:
        _finish(ctx, "session ran long")
    return True


# Router dialogs a session hands over when they land in the middle of it. Only
# ones that can interrupt anything and mean the same thing wherever they do:
# the daily reset, connectivity, and the pop-ups the bot already clears
# elsewhere. The career dialogs stay out - 'Complete Career' or 'Confirm' mean
# nothing on the Race tab, and a session must not press their points there.
SESSION_ROUTED = {
    'Date Changed', 'Notices', 'Network Error', 'Connection Error',
    'Data Update', 'Data Download', 'Sparks', 'Perks', 'Borrow Card',
    'Follow Trainer', 'Rewards Collected', 'Event Story Unlocked',
}


def _route_dialog(ctx, title: str) -> bool:
    """Deal with a dialog the session's own rules do not name. True if handled.

    A session claims every frame, so the dialog router never sees what lands
    during one. On 25 Sep that was the daily reset: the session reached the
    Race tab at 11:00:08, something came up over it, nothing handled it, and
    the screen sat still until the watchdog restarted the game two minutes
    later. Nothing was logged and nothing was photographed, because both of
    those happen in the router.

    So a dialog the router knows and that is safe here goes to the router's
    own handler. One nobody knows is photographed and cleared the way the
    router clears unknowns everywhere else - which is also what made the
    'Sparks' and 'Daily Carat Pack' pictures possible. Career dialogs, and
    titles the router deliberately leaves alone, are still left alone.
    """
    from uma_it import dialogs   # deferred: dialogs imports this module
    from uma_it.asset.dialog_titles import ALL_TITLES
    known = find_similar_text(title, ALL_TITLES, dialogs.MATCH_THRESHOLD)
    if known in SESSION_ROUTED and known in dialogs.DIALOGS:
        log.info(f"Team trials: {known!r} came up - handing it to the dialog router")
        dialogs.DIALOGS[known](ctx)
        return True
    if not known:
        log.warning(f"Team trials: unknown dialog {title!r} - photographing and clearing it")
        dialogs._capture_unknown(ctx, title)
        dialogs._escape(ctx, f"Unhandled dialog during team trials {title!r}")
        return True
    return False


def _read_title(ctx, img) -> str:
    """The dialog title on this frame, or '' when there is no dialog."""
    try:
        found = image_match(img, UI_INFO)
        if not found.find_match:
            return ''
        pos = found.matched_area
        # Where the header sat, for handlers that bound a search to below it.
        # dialogs.read_title stashes the same thing; a session never goes
        # through it, so without this they would search the whole screen.
        career = getattr(ctx, 'career', None)
        if career is not None:
            career.dialog_header_pos = pos
        crop = img[pos[0][1] - 5:pos[1][1] + 5, pos[0][0] + 150:pos[1][0] + 405]
        return (ocr_line(crop) or '').strip()
    except Exception:
        return ''
