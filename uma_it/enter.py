"""Getting from Home into a started career.

Home -> Scenario Select -> trainee -> legacy -> borrow a support card -> the
start dialog. `start.py` takes over from there.

None of these screens carries a decision worth much: the game remembers the
Training Focus and Prioritized Skills the user set by hand, so this is mostly
pressing Next. The two that matter are Home, where the CAREER button moves,
and the borrow screen, where the wrong card is a worse run.
"""
import time

import bot.base.log as logger
from bot.base.task import TaskStatus, EndTaskReason
from bot.recog.image_matcher import image_match

from uma_it.asset.point import (
    TITLE_TAP,
    TO_CULTIVATE_SCENARIO_CHOOSE,
    TO_CULTIVATE_PREPARE_NEXT,
    TO_CULTIVATE_PREPARE_AUTO_SELECT,
    TO_CULTIVATE_PREPARE_INCLUDE_GUEST,
    TO_CULTIVATE_PREPARE_CONFIRM,
    TO_FOLLOW_SUPPORT_CARD_SELECT,
    FOLLOW_SUPPORT_CARD_SELECT_REFRESH,
    CULTIVATE_FINAL_CHECK_START,
)
from uma_it.asset.template import (
    UI_SCENARIO_URA,
    UI_SCENARIO_AOHARUHAI,
    UI_SCENARIO_TRACKBLAZER,
    UI_SCENARIO_GRANDCONCERT,
    REF_CULTIVATE_SUPPORT_CARD_EMPTY,
    REF_BORROW_CARD,
)
from uma_it.define import ScenarioType
from uma_it.parse import (
    find_green_button,
    describe_green_candidates,
    find_support_card,
)

log = logger.get_logger(__name__)

SCENARIO_TEMPLATES = {
    ScenarioType.URA: UI_SCENARIO_URA,
    ScenarioType.AOHARUHAI: UI_SCENARIO_AOHARUHAI,
    ScenarioType.TRACKBLAZER: UI_SCENARIO_TRACKBLAZER,
    ScenarioType.GRAND_CONCERT: UI_SCENARIO_GRANDCONCERT,
}

# Where the CAREER button sits on Home, as a region to search rather than a
# point to press. Verified against a live Home capture: the search finds a
# 146x47 blob at (543, 1112), which no shape filter rejects.
CAREER_REGION = (380, 1020, 715, 1160)

# How many consecutive misses to wait out before using the fixed point. A miss
# is normally the screen mid-transition, and the fallback's value is covering a
# button whose art has changed - which is not a transient condition, so it can
# afford to wait.
CAREER_MISSES_BEFORE_FALLBACK = 3

# The carousel holds more scenarios than this app can start a run in, and it
# opens wherever it was left, so swipe far enough to cycle it from any
# starting position rather than tying attempts to the number of scenarios.
SCENARIO_SWIPES = 6

# How many times to refresh the borrow list looking for the wanted card.
BORROW_REFRESHES = 18


# How many taps the title screen gets before it is left to the click guard.
# The guard restarts the game at eleven clicks on one point, and a restart is
# the right answer to a title screen that will not start - but only after
# tapping has honestly been tried.
MAX_TITLE_TAPS = 6
# Between taps. The screen takes a moment to react, and a tap per frame would
# reach the guard in about twelve seconds.
TITLE_TAP_INTERVAL = 3


def script_game_loading(ctx):
    """The "Now Loading" screen. Clicks nothing, on purpose.

    The game shows this for anything from a few seconds to three and a half
    minutes after a restart, and the bot restarts the game itself - the
    watchdog and the click guard both do it. Until this screen had a name it
    fell to the blind fallback, which taps a corner once a frame; eleven taps
    tripped the guard, the guard restarted the game, and the game came back to
    this screen. Turnovers on 24 Sep cost two to four restarts each that way.

    Nothing to click here: the screen goes away by itself. Logged once per run
    so a long load is visible without three hundred lines of it.
    """
    career = getattr(ctx, 'career', None)
    if career is not None and not getattr(career, 'loading_logged', False):
        career.loading_logged = True
        log.info("Game is loading - waiting, clicking nothing")
    time.sleep(2)


def script_game_title(ctx):
    """The title screen, which says Tap to Start and means it.

    Tapped rather than waited out, and spaced out rather than once a frame:
    the guard counts eleven clicks on one point, so a tap per frame would have
    it restart the game in about twelve seconds - which is the thing this
    handler exists to stop. After a few honest tries it stops tapping and
    leaves the screen to the guard, because a title screen that will not start
    is exactly what a restart is for.
    """
    career = getattr(ctx, 'career', None)
    taps = getattr(career, 'title_taps', 0) if career is not None else 0
    if taps >= MAX_TITLE_TAPS:
        time.sleep(TITLE_TAP_INTERVAL)
        return
    if career is not None:
        career.title_taps = taps + 1
    log.info(f"Title screen - tapping to start ({taps + 1})")
    ctx.ctrl.click_by_point(TITLE_TAP)
    time.sleep(TITLE_TAP_INTERVAL)


def script_main_menu(ctx):
    """Home. Either the loop is done, or a new career starts here.

    Home is recognised by the bottom nav tab, **not** by the CAREER button.
    That button's art rotates with in-game events - one chibi and dumbbells one
    day, two Champions Meeting characters the next - and the lettering moves
    with it, so no crop matches both rotations. Twice in one week a rotation
    left the parent unable to find Home at all.

    CAREER is then located by colour, which keeps the button being pressed
    where it actually is rather than where it usually is.

    That search works, contrary to a note carried in the parent claiming it
    had "135 failures with no recorded success". It logs only its failures, and
    both paths clicked under the same name, so the successes were invisible. A
    DEBUG career on 10 Sep 2026 settled it from the tap coordinates: one Home
    frame tapped (540, 1116), which is the search's own result, and the next -
    two seconds later, mid-transition - warned and tapped the fixed point at
    (548, 1083). The search succeeds; it just cannot see a button that is
    currently being pressed. Successes are logged now, and the two clicks have
    different names.
    """
    career = ctx.career
    if career.career_finished:
        ctx.task.end_task(TaskStatus.TASK_STATUS_SUCCESS, EndTaskReason.COMPLETE)
        return

    # A new career begins here, so forget what the agenda picker did for the
    # last one. Normally the process soft-restarts between careers and rebuilds
    # this, but when a career ends without the task ending, a stale 'done'
    # makes the next career skip the agenda and run the game's default
    # schedule - silently, which is this project's worst failure mode.
    if career.agenda_phase:
        log.info("New career - resetting the agenda picker")
        career.agenda_phase = ''
        career.agenda_steps = 0
        career.agenda_waits = 0

    try:
        img = ctx.current_screen if ctx.current_screen is not None else ctx.ctrl.get_screen()
        btn = find_green_button(img, *CAREER_REGION)
        if btn:
            career.career_button_misses = 0
            log.info(f"Home: CAREER found by colour at {btn}")
            ctx.ctrl.click(btn[0], btn[1], "CAREER (found by colour)")
            return

        # A miss here is usually the screen still transitioning after CAREER was
        # already pressed - the button is not green while it is being tapped -
        # so the first few are waited out rather than clicked through. Falling
        # back immediately means a second, redundant tap on Home.
        career.career_button_misses += 1
        why = describe_green_candidates(img, *CAREER_REGION)
        if career.career_button_misses <= CAREER_MISSES_BEFORE_FALLBACK:
            log.info(f"Home: CAREER not green yet "
                     f"(miss {career.career_button_misses}) - waiting [{why}]")
            return
        log.warning("Home: could not find the CAREER button by colour - "
                    f"using the fixed point [{why}]")
    except Exception as e:
        log.warning(f"Home: CAREER button search failed ({e}) - using the fixed point")
    career.career_button_misses = 0
    ctx.ctrl.click_by_point(TO_CULTIVATE_SCENARIO_CHOOSE)


def script_scenario_select(ctx):
    """The scenario carousel. Swipe until the task's scenario is on screen."""
    wanted = ctx.task.detail.scenario
    template = SCENARIO_TEMPLATES.get(wanted)
    if template is None:
        log.error(f"No scenario template for {wanted} - cannot start a career")
        ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.SCENARIO_NOT_FOUND)
        return

    time.sleep(2)   # a slow connection can still be drawing the carousel
    for _ in range(SCENARIO_SWIPES):
        if image_match(ctx.ctrl.get_screen(to_gray=True), template).find_match:
            log.info(f"Scenario Select: found {wanted.name}")
            ctx.ctrl.click_by_point(TO_CULTIVATE_PREPARE_NEXT)
            return
        ctx.ctrl.swipe(x1=400, y1=600, x2=500, y2=600, duration=300, name="next scenario")
        time.sleep(1)

    log.error(f"Scenario Select: {wanted.name} not found after "
              f"{SCENARIO_SWIPES} swipes")
    ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.SCENARIO_NOT_FOUND)


def script_umamusume_select(ctx):
    """The trainee picker. The game keeps the last choice, so just go on."""
    ctx.ctrl.click_by_point(TO_CULTIVATE_PREPARE_NEXT)


def script_extend_umamusume_select(ctx):
    """The legacy (parents) picker.

    With `use_last_parents` the game's own memory is enough. Otherwise run the
    auto-select flow, which is four clicks in a fixed order.
    """
    if getattr(ctx.task.detail, 'use_last_parents', False):
        ctx.ctrl.click_by_point(TO_CULTIVATE_PREPARE_NEXT)
        return
    for point in (TO_CULTIVATE_PREPARE_AUTO_SELECT,
                  TO_CULTIVATE_PREPARE_INCLUDE_GUEST,
                  TO_CULTIVATE_PREPARE_CONFIRM,
                  TO_CULTIVATE_PREPARE_NEXT):
        ctx.ctrl.click_by_point(point)
        time.sleep(1)


def script_support_card_select(ctx):
    """The support card deck. An empty borrow slot means go and fill it.

    Logged either way. Without it there is no record of whether the wanted card
    was borrowed or the slot was simply already full from the last career, and
    those look identical from outside.
    """
    if image_match(ctx.ctrl.get_screen(to_gray=True),
                   REF_CULTIVATE_SUPPORT_CARD_EMPTY).find_match:
        log.info(f"Support deck: borrow slot empty - looking for "
                 f"{ctx.task.detail.follow_support_card_name!r}")
        ctx.ctrl.click_by_point(TO_FOLLOW_SUPPORT_CARD_SELECT)
        return
    log.info("Support deck: borrow slot already filled - going on")
    ctx.ctrl.click_by_point(TO_CULTIVATE_PREPARE_NEXT)


def _still_on_borrow_screen(ctx, img) -> bool:
    """True while the borrow list is still the screen being looked at.

    Scrolling a list the bot has already left would click on whatever replaced
    it, so every pass re-checks the header before swiping again.
    """
    try:
        import cv2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        x1, y1, x2, y2 = 279, 48, 326, 76
        roi = gray[max(0, min(h, y1)):max(0, min(h, y2)),
                   max(0, min(w, x1)):max(0, min(w, x2))]
        return bool(image_match(roi, REF_BORROW_CARD).find_match)
    except Exception:
        # A failed check must not end the search; the refresh budget bounds it.
        return True


def script_follow_support_card_select(ctx):
    """The borrow list: find the card the task asked for, or refresh and retry.

    Each pass scrolls the visible list down and then back up, reading every
    card, before spending a refresh on a new set of players. The parent wrote
    those two directions as two identical blocks; they are one loop here, which
    changes nothing about the order of the swipes.
    """
    for _ in range(BORROW_REFRESHES):
        for direction, (y_from, y_to) in (("down", (1000, 400)), ("up", (400, 1000))):
            for _pass in range(3):
                img = ctx.ctrl.get_screen()
                if find_support_card(ctx, img):
                    return
                if not _still_on_borrow_screen(ctx, img):
                    log.info("Borrow list: no longer on the borrow screen - "
                             "stopping the card search")
                    return
                ctx.ctrl.swipe(x1=350, y1=y_from, x2=350, y2=y_to, duration=600,
                               name=f"scroll {direction} the borrow list")
                time.sleep(0.5)
        ctx.ctrl.click_by_point(FOLLOW_SUPPORT_CARD_SELECT_REFRESH)
        time.sleep(1.2)

    log.warning(f"Borrow list: {ctx.task.detail.follow_support_card_name!r} not "
                f"found after {BORROW_REFRESHES} refreshes - starting without it")
    ctx.ctrl.click_by_point(FOLLOW_SUPPORT_CARD_SELECT_REFRESH)


def script_cultivate_final_check(ctx):
    """The pre-start screen behind the Final Confirmation dialog."""
    ctx.ctrl.click_by_point(CULTIVATE_FINAL_CHECK_START)
