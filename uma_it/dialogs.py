"""The dialog router.

Almost everything on this path is a dialog. Counted across the careers that
preceded this project: 654 `Agenda` frames, 332 `Recover TP`, 284 `Final
Confirmation`, 218 `My Agendas`, and so on down to single frames of `Data
Update` and `Auto Select`. Dialogs carry no distinguishing template - anything
with the green diagonal header matches `INFO` - so they are told apart by the
title OCR'd out of that header.

Two things differ from the router this replaces.

**Titles are keys, not indices.** The parent compares against `TITLE[48]`,
`TITLE[11]`, `TITLE[31]`, and its own comments record entries having been
mis-indexed ("FIXED: was ..."). A dict cannot drift that way.

**There is nowhere to defer to.** In the parent this table sat in front of a
1,162-line handler that caught everything it did not claim. Here it is the
whole router, so every title that can occur has to be accounted for - as an
action, or as a deliberate silence. Which one each gets was decided by counting
what actually appears, not by reading the parent's table.

The three outcomes for a frame:

* **A title with an action** - dispatched.
* **A title with none** - logged at debug, and *nothing is clicked*. The parent
  behaves this way for `Recover TP` and `Items Selected` (both are in its title
  list; neither has a live branch, one being commented out), so clicking here
  would be new behaviour on a screen nobody has studied.
* **No title clears the threshold** - the blind fallback click, and a warning
  worth reading. That click is load-bearing: replacing it with a no-op hung the
  parent on its first run and had to be reverted. Naming a screen is the fix
  for fallback noise; removing the click is not.
"""
import time

import cv2

from bot.recog.image_matcher import image_match
from bot.recog.ocr import ocr_line, find_similar_text
from bot.base.task import TaskStatus
import bot.base.log as logger

from uma_it import agenda, start
from uma_it.asset.template import UI_INFO, REF_NEXT
from uma_it.asset.dialog_titles import ALL_TITLES
from uma_it.asset.point import (
    ESCAPE,
    CULTIVATE_FINISH_RETURN_CONFIRM,
    CULTIVATE_FINISH_CONFIRM_AGAIN,
    CULTIVATE_RESULT_CONFIRM,
    CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN,
    STORY_REWARDS_COLLECTED_CLOSE,
    NETWORK_ERROR_CONFIRM,
    TO_RECOVER_TP,
    TO_CULTIVATE_PREPARE_NEXT,
    CULTIVATE_GOAL_RACE_INTER_3,
)
from uma_it.task import EndTaskReason

log = logger.get_logger(__name__)

# Titles this table owns are matched only at the tight threshold. The parent
# runs a second pass at 0.6, which is loose enough that 'Fan' once scored
# against 'Fantasy'.
MATCH_THRESHOLD = 0.8


def _escape(ctx, what: str):
    """Clear a screen with the corner click the blind fallback would make.

    Named, so the log says which screen was cleared and why.

    Logs the raw OCR and the header's position because `Follow Trainer`
    sometimes needs several clears in a row - 1, 1, 1, 2, 2, 1, 3, 1, 4 across
    nine occurrences - and two explanations remain open:

      * several prompts stacked, one cleared per click, in which case the count
        varies with how many the career earned and nothing is wrong;
      * one dialog that ignores the click and has to be hit again.

    Identical text *and* identical geometry across consecutive attempts means
    one stubborn dialog. Different geometry means separate prompts. That is the
    discriminator, and the next multi-clear career settles it.

    Already ruled out, so do not re-run it: `click_by_point` drops a repeat on
    the same point inside `same_point_operation_interval`, but that is 0.27 s
    against roughly 2.5 s between these attempts, and its warning has never
    appeared here.
    """
    career = getattr(ctx, 'career', None)
    n = getattr(career, 'dialog_repeat', 1) if career is not None else 1
    raw = getattr(career, 'dialog_raw_title', '')
    hdr = getattr(career, 'dialog_header_box', None)
    where = f", header {hdr}" if hdr else ""
    if n >= 5:
        # Not a no-op. The click guard tripping at 11 is the designed backstop
        # for a screen that will not clear; keep clicking, and make the run-up
        # to it loud rather than silent.
        log.warning(f"{what} - clearing it, attempt {n} (OCR {raw!r}{where}) - "
                    f"this screen is not clearing; the click guard trips at 11")
    else:
        log.info(f"{what} - clearing it (attempt {n}, OCR {raw!r}{where})")
    ctx.ctrl.click_by_point(ESCAPE)
    time.sleep(1)


def _tap(point, what: str):
    """A dialog that needs one click on a fixed point and nothing else."""
    def action(ctx):
        log.info(what)
        ctx.ctrl.click_by_point(point)
        time.sleep(1)
    return action


def _tap_xy(x, y, what: str):
    """Same, for the handful the parent clicks by raw coordinate."""
    def action(ctx):
        log.info(what)
        ctx.ctrl.click(x, y, what)
        time.sleep(1)
    return action


def _silent(what: str):
    """A title that occurs and that the parent deliberately does not act on.

    Kept as an entry rather than left to the fallback, so the screen is named
    in the log and the fallback's warning keeps meaning "genuinely unknown".
    """
    def action(ctx):
        log.debug(f"{what} - no action, by design")
    return action


def _career_complete(ctx):
    """The end-of-career "Return to the home screen?" prompt. Always Cancel.

    The bot drives its own way back, and a trainer event relabels the green
    button "Event Home", so agreeing is not the harmless choice it looks. This
    used to ride a fuzzy match onto 'Training Complete', which happened to
    click the same point - a coincidence, until the event changed the label.
    """
    log.info("Career Complete dialog - cancelling the return prompt")
    ctx.ctrl.click_by_point(CULTIVATE_FINISH_RETURN_CONFIRM)
    time.sleep(1)


def _tp_recovery_confirm(ctx):
    """The dialog offering to restore TP, and the decision behind it.

    This is how the loop ends when the account runs dry: Independent Training
    costs 30 TP and regenerates far slower than a career consumes it, so after
    a couple of dozen back-to-back runs this appears. `allow_recover_tp` at 0
    fails the career rather than paying, which is the deliberate default -
    higher values authorise spending carats, which are real currency.
    """
    allow = getattr(ctx.task.detail, 'allow_recover_tp', 0)
    if not allow:
        log.info("TP recovery offered - declining and failing the career "
                 "(allow_recover_tp is 0)")
        ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.TP_NOT_ENOUGH)
        return
    log.info("TP recovery offered - accepting (allow_recover_tp is %s)", allow)
    ctx.ctrl.click_by_point(TO_RECOVER_TP)
    time.sleep(1)


def _auto_select(ctx):
    """The legacy/parents picker on the way into a career."""
    if getattr(ctx.task.detail, 'use_last_parents', False):
        log.info("Auto Select - keeping the last parents")
        ctx.ctrl.click_by_point(TO_CULTIVATE_PREPARE_NEXT)
    else:
        log.info("Auto Select - letting the game choose")
        ctx.ctrl.click(214, 832, "Auto Select")
    time.sleep(1)


# title -> action. Everything a frame on this path can show, and what to do
# about it. See the module docstring for the three outcomes.
DIALOGS = {
    # -- screens the parent's table has no entry for -------------------------
    # Each was reaching the blind fallback there; each does the same thing
    # here, named.
    'Perks':            lambda ctx: _escape(ctx, "Support Formation 'Perks' panel"),
    'Borrow Card':      lambda ctx: _escape(ctx, "Borrow Card prompt"),
    'Follow Trainer':   lambda ctx: _escape(ctx, "Follow Trainer prompt"),
    # The announcements popup after the game's daily reset. It turned up 49
    # seconds before a countdown expired and was cleared only because the
    # fallback exists.
    'Notices':          lambda ctx: _escape(ctx, "Daily reset 'Notices' popup"),

    # -- ending a career -----------------------------------------------------
    'Career Complete':      _career_complete,
    'Complete Career':      _tap(CULTIVATE_FINISH_CONFIRM_AGAIN,
                                 "Complete Career - confirming"),
    'Training Complete':    _tap(CULTIVATE_FINISH_RETURN_CONFIRM,
                                 "Training Complete - returning"),
    'Umamusume Details':    _tap(CULTIVATE_RESULT_CONFIRM,
                                 "Umamusume Details - confirming"),
    'Confirmation':         _tap(CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN,
                                 "Confirmation - confirming"),
    'Rewards Collected':    _tap(STORY_REWARDS_COLLECTED_CLOSE,
                                 "Rewards Collected - closing"),
    'Event Story Unlocked': _tap(STORY_REWARDS_COLLECTED_CLOSE,
                                 "Event Story Unlocked - closing"),

    # -- entering a career ---------------------------------------------------
    'Auto Select':  _auto_select,
    'Race Details': _tap(CULTIVATE_GOAL_RACE_INTER_3, "Race Details - confirming"),

    # -- running out of TP, which is how the loop stops ----------------------
    # 'Confirm' is the decision. 'Recover TP' is the offer screen behind it,
    # which the parent knows and deliberately does not act on - its branch is
    # commented out - so neither does this.
    'Confirm':      _tp_recovery_confirm,
    'Recover TP':   _silent("TP recovery offer"),

    # -- known, occurs, and the parent has no branch for it ------------------
    # Handled only in Team Trials mode there, which this app never runs.
    'Items Selected': _silent("'Items Selected' prompt"),

    # -- starting a career, and recovering one already running ---------------
    # The most consequential clicks the bot makes; see start.py.
    'Final Confirmation':   start.script_final_confirmation,
    'Independent Training': lambda ctx: start.script_independent_training_pending(
        ctx, getattr(getattr(ctx, 'career', None), 'dialog_header_pos',
                     ((0, 0), (0, 0)))),

    # -- the trainer-event failsafe ------------------------------------------
    # Confirm on the event dialog is a one-way door into an event career, so
    # 'Start Event' always backs out, and 'Choose Career Mode' verifies the
    # Normal Mode switch took before it confirms.
    'Choose Career Mode': start.script_choose_career_mode,
    'Start Event': lambda ctx: _escape(
        ctx, "Event start dialog - backing out to keep the loop on Normal Mode"),

    # -- the race agenda picker ----------------------------------------------
    # One state machine across three screens; see agenda.py. The phase it runs
    # on is set by the Final Confirmation handler, which clicks Edit to start
    # the flow.
    'Agenda':     agenda.script_agenda,
    'My Agendas': agenda.script_my_agendas,
    'Overwrite':  agenda.script_agenda_overwrite,

    # -- connectivity, which can interrupt any screen ------------------------
    'Network Error':    _tap(NETWORK_ERROR_CONFIRM, "Network Error - confirming"),
    'Connection Error': _tap_xy(383, 840, "Connection Error - reconnecting"),
    'Data Update':      _tap_xy(383, 840, "Data Update - confirming"),
    'Data Download':    _tap_xy(383, 840, "Data Download - confirming"),
    'Date Changed':     _tap_xy(383, 840, "Date Changed - confirming"),
}


def read_title(ctx):
    """The dialog's title, or None when this frame is not a dialog.

    Same crop as the parent: the header runs to the right of the match, and
    the OCR is on greyscale.
    """
    img = cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
    result = image_match(img, UI_INFO)
    if not result.find_match:
        return None
    pos = result.matched_area
    title_img = img[pos[0][1] - 5:pos[1][1] + 5, pos[0][0] + 150: pos[1][0] + 405]
    text = (ocr_line(title_img) or '').strip()
    # Stash what was read and where the header sat. A handler firing twice in a
    # row cannot otherwise tell a second prompt from the first refusing to
    # close.
    career = getattr(ctx, 'career', None)
    if career is not None:
        career.dialog_raw_title = text
        career.dialog_header_box = (int(pos[0][0]), int(pos[0][1]),
                                    int(pos[1][0]), int(pos[1][1]))
        # the nested form, which the pending-run handler indexes as pos[1][1]
        # to bound its colour search below the header
        career.dialog_header_pos = pos
    return text


def script_dialog(ctx):
    """Dispatch one dialog frame."""
    try:
        raw = read_title(ctx)
    except Exception as e:
        log.warning(f"Dialog router could not read a title ({e}) - "
                    f"falling back")
        _escape(ctx, "Unreadable dialog")
        return

    if raw is None:
        # INFO matched but the header did not; treat it as unknown rather than
        # guessing at a screen.
        log.debug("INFO matched with no readable header - clearing")
        _escape(ctx, "Headerless dialog")
        return

    title = find_similar_text(raw, ALL_TITLES, MATCH_THRESHOLD)

    # How many frames in a row this same title has been dispatched. Reset by
    # any other dialog, so it measures "this screen will not go away" rather
    # than a running total across the career.
    career = getattr(ctx, 'career', None)
    if career is not None:
        if getattr(career, 'dialog_last_title', None) == title:
            career.dialog_repeat = getattr(career, 'dialog_repeat', 0) + 1
        else:
            career.dialog_last_title = title
            career.dialog_repeat = 1

    if title in DIALOGS:
        DIALOGS[title](ctx)
        return

    if title:
        # A distractor won. It is a real title, just not one this app acts on -
        # and it exists in the scoring set precisely so it could win here
        # rather than letting a shorter title of ours steal the frame.
        log.info(f"Dialog {title!r} (OCR {raw!r}) - not handled by this app, clearing")
    else:
        log.warning(f"Unknown dialog title - OCR: {raw!r}")
    _escape(ctx, f"Unhandled dialog {title or raw!r}")


def script_not_found_ui(ctx):
    """The blind fallback, for a frame matching no screen at all.

    Load-bearing, and smaller than the parent's. What was dropped and why:

    * Goal Achieved / Failed / Next screens - turn-by-turn only. The game plays
      the career here, so the bot never sees them.
    * The race-list ROI probe and the cultivation-result OCR heuristics
      ('rewards', 'bond level', 'total fans') - every result screen they guess
      at has a real template in `screens.py`, matched before this is reached.
    * The spark-selection interception - belongs with the spark reroll handler,
      which is not written. Anything reaching here while a reroll is in flight
      gets the corner click, which is what the parent does when its own
      heuristics miss.

    What is kept is the part that earns its place: a visible Next button, then
    the corner click that advances screens nobody has templated.
    """
    if ctx.current_screen is not None:
        try:
            img = cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
            match = image_match(img, REF_NEXT)
            if match.find_match:
                x, y = match.center_point[0], match.center_point[1]
                ctx.ctrl.click(x, y, "Next button")
                return
        except Exception as e:
            log.debug(f"Next-button probe failed: {e}")

    # The corner click. Note the fixed name: eleven of these in a row trip the
    # engine's repetitive-click guard and restart the game, which is the
    # designed backstop for a screen that will not advance.
    log.debug("No screen matched - default fallback click")
    ctx.ctrl.click(719, 1, "Default fallback click")
