"""Starting a career, and recovering one that is already running.

Three dialogs, and between them the most consequential clicks the bot makes:

* **Final Confirmation** - the career start dialog. Confirm here commits 30 TP
  and fifty minutes.
* **Choose Career Mode** - only present while a trainer event runs, with the
  event option preselected. Confirm is the *only* way out of it, so confirming
  the wrong option starts an event career.
* **Independent Training (pending)** - raised when CAREER is pressed on Home
  while a run is outstanding. Its green button enters the run; **Delete Data
  sits on the same dialog** and would throw the career away.

Everything here follows the same rule: where a wrong click cannot be undone,
verify the state first and give up rather than guess. Each of the three has a
try budget, and each budget ends in stopping or in a fallback that is safe -
never in a confirm made hopefully.

**Nothing in this file has ever run against the live game.** It was written
after the loop it replaces had already been stopped. `check_start.py` covers
the decisions, but a check cannot tell you the tab template still matches after
a game update, so treat the first live career as the real test.
"""
import time

import cv2

import bot.base.log as logger
from bot.base.task import TaskStatus, EndTaskReason
from bot.recog.image_matcher import image_match
from bot.recog.ocr import ocr_line

from uma_it import agenda
from uma_it.asset.point import (
    CULTIVATE_FINAL_CHECK_START,
    FINAL_CONFIRMATION_TAB_INDEPENDENT,
    AGENDA_EDIT,
    CAREER_MODE_NORMAL,
    CAREER_MODE_CONFIRM,
    INDEPENDENT_TRAINING_PENDING_CAREER,
)
from uma_it.asset.template import REF_INDEPENDENT_TRAINING_TAB
from uma_it.parse import agenda_schedule_counts, find_green_button

log = logger.get_logger(__name__)

# Where the event career's giveaway text sits on the career-mode dialog.
EVENT_MODE_REGION = (585, 630, 25, 320)     # y1, y2, x1, x2

# Try budgets. Each is a different kind of giving up, so they are not shared.
MAX_CAREER_MODE_SWITCHES = 5    # then stop; confirming would start an event run
MAX_TAB_SWITCHES = 3            # then start on whatever tab is showing
MAX_PENDING_ENTRIES = 20        # then stop clicking, but keep saying so


def _event_mode_selected(ctx) -> bool:
    """True while the dialog has the event career picked.

    The event option carries a "Selected Test" section that Normal Mode does
    not, which is the cheapest way to tell the two states apart.

    **An unreadable frame returns True on purpose.** Guessing "not selected"
    would let the caller confirm, and Confirm is the one-way door into an event
    run. Guessing "selected" only costs another attempt.
    """
    try:
        y1, y2, x1, x2 = EVENT_MODE_REGION
        screen = ctx.ctrl.get_screen()
        text = (ocr_line(cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)) or '').lower()
        return 'selected test' in text
    except Exception:
        return True


def script_choose_career_mode(ctx) -> None:
    """The dialog a trainer event inserts between the scenario and trainee
    pickers, with the event option preselected.

    A loop wants a plain career, so switch to Normal Mode - and verify the
    switch took before confirming, because there is no way back out.
    """
    career = getattr(ctx, 'career', None)
    if _event_mode_selected(ctx):
        tries = getattr(career, 'career_mode_switch_tries', 0) + 1
        if career is not None:
            career.career_mode_switch_tries = tries
        if tries > MAX_CAREER_MODE_SWITCHES:
            # Stopping is the right failure here. Falling through to Confirm
            # would start an event career, which cannot be undone and is not
            # what any task on this app asked for.
            log.error("Career mode dialog: could not switch to Normal Mode after "
                      f"{tries - 1} attempts - stopping instead of starting an event run")
            ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.SYSTEM_ERROR)
            return
        log.info(f"Career mode dialog: event mode selected - switching to Normal Mode "
                 f"(attempt {tries})")
        ctx.ctrl.click_by_point(CAREER_MODE_NORMAL)
        time.sleep(1)
        return
    if career is not None:
        career.career_mode_switch_tries = 0
    log.info("Career mode dialog: Normal Mode selected - confirming")
    ctx.ctrl.click_by_point(CAREER_MODE_CONFIRM)


def script_final_confirmation(ctx) -> None:
    """The career start dialog: make sure the Independent Training tab is up,
    load the agenda, then confirm.

    The tab is *checked* rather than assumed. Both tabs keep whatever was
    picked last, so a run started on the wrong one plays a turn-by-turn career
    that this app has no handlers for at all. Everything else on the dialog -
    Training Focus, Prioritized Skills - is remembered from the user's own
    setup, so there is nothing else to set.
    """
    career = getattr(ctx, 'career', None)
    on_independent = image_match(ctx.ctrl.get_screen(to_gray=True),
                                 REF_INDEPENDENT_TRAINING_TAB).find_match

    if not on_independent:
        tries = getattr(career, 'final_confirmation_tab_tries', 0) + 1
        if career is not None:
            career.final_confirmation_tab_tries = tries
        if tries <= MAX_TAB_SWITCHES:
            log.info(f"Career start: switching to the Independent Training tab "
                     f"(attempt {tries})")
            ctx.ctrl.click_by_point(FINAL_CONFIRMATION_TAB_INDEPENDENT)
            time.sleep(1)
            return
        # Don't keep tapping: eleven identical clicks trip the repetitive-click
        # guard and restart the app. Fall through and start on whatever tab the
        # game is showing rather than looping here.
        log.warning("Career start: could not select the Independent Training tab - "
                    "starting on the tab the game is showing")

    if career is not None:
        career.final_confirmation_tab_tries = 0

    # Load the first saved agenda before starting. The Agenda block lives on
    # this tab, and loading is idempotent - the game replaces the user-race
    # set, so re-applying the same slot every run does not stack races.
    #
    # This is the handoff into agenda.py: set the phase, click Edit, and the
    # Agenda / My Agendas / Overwrite handlers take it from there.
    if on_independent and agenda._phase(ctx) != 'done':
        if agenda._step(ctx):
            log.info("Career start: loading the first saved agenda before starting")
            agenda._set_phase(ctx, 'opening')
            ctx.ctrl.click_by_point(AGENDA_EDIT)
            time.sleep(1)
            return

    if on_independent:
        # Say what this run actually starts with. The agenda picker can load
        # the wrong entry with no error anywhere - these counts are the only
        # visible sign, and the reason a four-race agenda once ran for fifteen
        # careers unnoticed.
        try:
            counts = agenda_schedule_counts(ctx.current_screen)
            if counts:
                log.info(f"Starting with {counts['scheduled']} scheduled races "
                         f"(G1 {counts['g1']}, G2 {counts['g2']}, G3 {counts['g3']})")
            else:
                log.warning("Could not read the scheduled race counts off the start dialog")
        except Exception as e:
            log.warning(f"Could not read the scheduled race counts: {e}")

    log.info(f"Career start: confirming on the "
             f"{'Independent Training' if on_independent else 'Normal Career'} tab")
    ctx.ctrl.click_by_point(CULTIVATE_FINAL_CHECK_START)


def script_independent_training_pending(ctx, title_pos) -> None:
    """The dialog the game raises when CAREER is pressed on Home while a run is
    pending - either still counting down, or finished and waiting to be
    collected.

    The bot normally never sees it, because it is already inside the run when
    the timer ends. It appears after the game restarts mid-run, which is
    exactly when the loop needs to recover. Escaping it just lands back on
    Home, where the bot presses CAREER again - that round trip is what wedged
    the loop for an hour once.

    The green Career button is found **by colour**, not by a fixed point,
    because "Delete Data" sits on the same dialog and would throw the career
    away. The fixed point is only a fallback for when the colour search fails.
    """
    career = getattr(ctx, 'career', None)
    tries = getattr(career, 'pending_run_tries', 0) + 1
    if career is not None:
        career.pending_run_tries = tries
    if tries > MAX_PENDING_ENTRIES:
        # Stop clicking rather than feed the click guard, but keep saying so:
        # a loop that cannot get back into its own run is stuck, and silence
        # here would look like a healthy wait.
        if tries % MAX_PENDING_ENTRIES == 0:
            log.error("Independent Training run pending - still not entering after "
                      f"{tries} attempts; the loop cannot proceed without it")
        return

    ok = find_green_button(ctx.current_screen, 70, title_pos[1][1], 660, 1270)
    if not ok:
        log.warning("Independent Training run pending - green button not found, "
                    "using the fixed point")
        ctx.ctrl.click_by_point(INDEPENDENT_TRAINING_PENDING_CAREER)
        time.sleep(1)
        return
    log.info(f"Independent Training run pending - entering it at {ok} (attempt {tries})")
    ctx.ctrl.click(ok[0], ok[1], "Enter the pending Independent Training run")
    # Let the entry animation finish before the next screenshot, so the run's
    # own screens are what gets matched next.
    time.sleep(4)
