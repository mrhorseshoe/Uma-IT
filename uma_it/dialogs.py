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

from uma_it import agenda, spark, start, team_trials, tp
from uma_it.asset.template import UI_INFO, REF_NEXT
from uma_it.asset.dialog_titles import ALL_TITLES
from uma_it.parse import find_green_button, is_spark_selection_screen
from uma_it.asset.point import (
    EXIT_WITHOUT_LEARNING_SKILLS_OK,
    ESCAPE,
    CULTIVATE_FINISH_RETURN_CONFIRM,
    CULTIVATE_FINISH_CONFIRM_AGAIN,
    CULTIVATE_RESULT_CONFIRM,
    CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN,
    CULTIVATE_LEARN_SKILL_DONE_CONFIRM,
    STORY_REWARDS_COLLECTED_CLOSE,
    HOME_TAB,
    NETWORK_ERROR_CONFIRM,
    SPARKS_CLOSE,
    RESTORE_NO,
    TO_RECOVER_TP,
    TO_CULTIVATE_PREPARE_NEXT,
    CULTIVATE_GOAL_RACE_INTER_3,
)
from uma_it.task import EndTaskReason

log = logger.get_logger(__name__)

# Frames in a row matching no screen before the fallback tries the Home tab.
# The executor dispatches about once a second, so this is roughly a minute -
# long enough that no ordinary transition reaches it, short enough that a trap
# costs a minute rather than the five hours it cost on 19 Sep.
UNKNOWN_FRAMES_BEFORE_HOME = 40

# Titles this table owns are matched only at the tight threshold. The parent
# runs a second pass at 0.6, which is loose enough that 'Fan' once scored
# against 'Fantasy'.
MATCH_THRESHOLD = 0.8


# Unknown dialogs this process has already photographed. One frame each is
# enough to identify a screen, and a dialog the bot bounces off 170 times an
# hour would otherwise fill the disk with the same picture.
_captured = set()


def _capture_unknown(ctx, raw: str):
    """Keep one frame of a dialog no entry matched.

    A title the router cannot place gets the blind corner click, and the log
    then says only what was read. That is not enough to fix it: 'Sparks' has
    been bounced off 720 times this week and nobody can say what it is, and on
    20 Sep a 'Schedule Race' dialog landed in the middle of the agenda load and
    the career started two races short. Both are unfalsifiable from text.

    One picture per title per process, written beside the other debug
    captures, and never at the cost of the frame it is clearing.
    """
    key = (raw or '').strip().lower()
    if not key or key in _captured:
        return
    _captured.add(key)
    try:
        import os, re
        import cv2
        os.makedirs('screenshot/dialogs', exist_ok=True)
        safe = re.sub(r'[^A-Za-z0-9]+', '_', raw)[:40] or 'blank'
        path = f'screenshot/dialogs/{time.strftime("%Y%m%d_%H%M%S")}_{safe}.png'
        img = ctx.current_screen if getattr(ctx, 'current_screen', None) is not None \
            else ctx.ctrl.get_screen()
        cv2.imwrite(path, img)
        log.info(f"Kept a frame of the unrecognised dialog {raw!r} at {path}")
    except Exception as e:
        log.debug(f"unknown-dialog capture failed: {e}")


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


def _confirm(ctx):
    """The 'Confirm' title, which the game puts on two unrelated prompts.

    One is the TP restore offer. The other is "Exit without learning skills?",
    raised by the Back click `skills._leave` makes on its way off the skill
    screen - so it appears once per career, but only when skill buying is on.

    Routing both to `_tp_recovery` ended every career of the 11 Sep run the
    moment its skills were bought: the bot read a prompt it had raised itself
    as an out-of-TP offer, declined it, and failed the run. Three loops burned
    in three minutes, each one re-entering the skill screen the last had never
    left. The title match was never wrong; the title is simply not enough, and
    the body is what separates them.
    """
    career = getattr(ctx, 'career', None)
    header = getattr(career, 'dialog_header_pos', None)
    body = read_body(ctx, header) if header else ''
    if 'learning skill' in body.lower():
        log.info(f"Skill screen exit prompt ({body!r}) - confirming")
        ctx.ctrl.click_by_point(EXIT_WITHOUT_LEARNING_SKILLS_OK)
        time.sleep(1)
        return
    _tp_recovery(ctx, body)


def _tp_recovery(ctx, body: str = ''):
    """The TP prompt, and the decision behind it.

    This is how the loop ends when the account runs dry: Independent Training
    costs 30 TP and regenerates far slower than a career consumes it, so after
    a couple of dozen back-to-back runs this appears.

    `allow_recover_tp` at 0 fails the career rather than paying. Above 0 the
    restore actually runs - see `tp.py`, which prefers a TP item and falls back
    to carats. The parent stops at accepting the prompt: its own handler for
    the screen that follows is commented out, which is why 332 `Recover TP`
    frames appear in its logs with nothing acting on them.
    """
    # The RP prompt wears the same 'Confirm' title as the TP one. Read as TP it
    # cost a career on 19 Sep: the bot declined "restore RP?" and held the loop
    # for half an hour while a career was still running.
    if team_trials.is_rp_prompt(body):
        log.info(f"Not enough RP ({body!r}) - declining; RP is not worth carats")
        ctx.ctrl.click_by_point(RESTORE_NO)
        time.sleep(1)
        return
    if not tp.allowed(ctx):
        _wait_for_tp(ctx, body, "allow_recover_tp is 0")
        return
    career = getattr(ctx, 'career', None)
    header = getattr(career, 'dialog_header_pos', None)
    if not tp.step(ctx, body, header):
        _wait_for_tp(ctx, body, "the restore could not proceed")


def _wait_for_tp(ctx, body: str, why: str):
    """Hold the loop until TP has come back, rather than failing the career.

    Declining costs nothing - the career has not started - so being a few TP
    short is not a failed run, it is an early one. It used to be counted as a
    failure, and three in a row stop the loop: on 19 Sep that ended a session
    at 05:03 while the game was asking for **one** more TP, and the next two
    attempts came 13 and 12 seconds later.

    The resume time goes on the task, so it survives the restart after each
    career, and the scheduler starts nothing until it passes.
    """
    # Say No first, but only to the prompt itself - its No button is at a
    # coordinate that means something else on the Recover TP screen behind it.
    # The prompt is modal: a run that ends with it still up leaves the game
    # behind a popup, and everything that would fill the wait - team trials
    # especially - is stuck there. On 19 Sep that left three RP unspent.
    if body and ('restore' in body.lower() or tp.shortfall(body)):
        ctx.ctrl.click_by_point(RESTORE_NO)
        time.sleep(1)
    missing = tp.shortfall(body)
    seconds = tp.wait_seconds(missing)
    ctx.task.detail.resume_after = int(time.time()) + seconds
    # RP regenerates whether or not it is used and caps at 5, so a wait is
    # exactly when team trials are free. The session runs first; the wait
    # outlives it and still holds the next career back. `due` rather than
    # `wanted`: RP emptied minutes ago is still empty, and asking again means
    # walking to the Race tab to be told so.
    if team_trials.due(ctx):
        ctx.task.detail.tt_pending = True
    log.info(f"TP restore offered ({body!r}) - declining ({why}); "
             f"{missing if missing else 'an unknown amount of'} TP short, "
             f"waiting {round(seconds / 60)} min, until "
             f"{time.strftime('%H:%M', time.localtime(ctx.task.detail.resume_after))}")
    ctx.task.end_task(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.TP_WAIT)


# How far off centre the green button has to sit before the dialog is read as
# a two-button one. A single centred button is its own mirror, so mirroring it
# would click the very thing being declined.
TWO_BUTTON_OFFSET = 60


def decline_daily_sale(ctx):
    """Cancel the shop's Daily Sale offer, wherever it appears.

    Cancel rather than the corner click the parent project makes at (0, 0): a
    tap outside is a dismissal the dialog may or may not honour, and this one
    is stubborn. On 20 Sep it landed during a team trials session, nothing
    recognised it, and the screen sat still long enough for the watchdog to
    restart the game.

    The button is found, not hardcoded. Cancel is the white button mirroring
    the green purchase one, so the green one's position gives it - the trick
    `spark.intercept_dialog` already uses to decline a TP restore, and it holds
    whatever height the dialog happens to be. A green button near the centre is
    a *single* button, so there is no Cancel to mirror and the popup is cleared
    the way the parent clears it.
    """
    screen = getattr(ctx, 'current_screen', None)
    if screen is None:
        screen = ctx.ctrl.get_screen()
    career = getattr(ctx, 'career', None)
    header = getattr(career, 'dialog_header_pos', None)
    top = header[1][1] if header else 400
    ok = None
    try:
        ok = find_green_button(screen, 70, top, 660, 1270)
    except Exception as e:
        log.debug(f"Daily Sale: the green button search failed ({e})")
    if ok and abs(ok[0] - 360) >= TWO_BUTTON_OFFSET:
        ctx.ctrl.click(720 - ok[0], ok[1], "Daily Sale - Cancel")
        time.sleep(1)
        return
    where = "no green button found" if not ok else f"one centred button at {ok}"
    _escape(ctx, f"Daily Sale offer ({where})")


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
    # The shop's offer of the day. Always declined - the bot spends nothing.
    'Daily Sale':       decline_daily_sale,
    # The legacy Sparks list, opened from the parent pickers. It is nearly the
    # whole screen, so the blind corner click lands *on* it and does nothing:
    # on 23 Sep the bot bounced off this dialog 441 times in 2h41m and the
    # click guard restarted the game 322 times. Its one button is Close.
    'Sparks':           _tap(SPARKS_CLOSE, "Legacy Sparks list - closing"),

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
    # Only seen when skill buying is on.
    'Skills Learned':       _tap(CULTIVATE_LEARN_SKILL_DONE_CONFIRM,
                                 "Skills Learned - confirming"),
    'Rewards Collected':    _tap(STORY_REWARDS_COLLECTED_CLOSE,
                                 "Rewards Collected - closing"),
    'Event Story Unlocked': _tap(STORY_REWARDS_COLLECTED_CLOSE,
                                 "Event Story Unlocked - closing"),

    # -- entering a career ---------------------------------------------------
    'Auto Select':  _auto_select,
    'Race Details': _tap(CULTIVATE_GOAL_RACE_INTER_3, "Race Details - confirming"),

    # -- running out of TP, which is how the loop stops ----------------------
    # 'Recover TP' is the offer screen; 'Confirm' is the prompt in front of it,
    # and also the title of the skill screen's exit prompt, so it goes through
    # a body-text check first. Both reach the same stepper, which recognises
    # whichever screen it is looking at.
    'Confirm':      _confirm,
    'Recover TP':   _tp_recovery,

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


def read_body(ctx, header_pos) -> str:
    """The dialog's body text, read below the header.

    Only needed where the title does not identify the prompt. Measured on the
    stuck frame of 11 Sep: with the header box at ((8, 391), (136, 440)), the
    body sits at y 616 and the buttons at y 834, so a window of 60-300 below
    the header holds the sentence and nothing else.
    """
    try:
        img = cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
        bottom = header_pos[1][1]
        return (ocr_line(img[bottom + 60:bottom + 300, 30:690]) or '').strip()
    except Exception as e:
        log.debug(f"Dialog body unreadable: {e}")
        return ''


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

    # A reroll in flight owns its own dialogs, and they have to be judged by
    # body text - the title dispatch below would click a point behind them.
    # This also has to come before 'Confirm' reaches the TP handler, which
    # would end the career over a reroll the run does not need.
    career = getattr(ctx, 'career', None)
    if career is not None and getattr(career, 'spark_reroll_phase', ''):
        if spark.intercept_dialog(ctx, career.dialog_header_pos):
            return

    title = find_similar_text(raw, ALL_TITLES, MATCH_THRESHOLD)

    # How many frames in a row this same title has been dispatched. Reset by
    # any other dialog, so it measures "this screen will not go away" rather
    # than a running total across the career.
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
        _capture_unknown(ctx, raw)
    _escape(ctx, f"Unhandled dialog {title or raw!r}")


def script_not_found_ui(ctx):
    """The blind fallback, for a frame matching no screen at all.

    Load-bearing, and smaller than the parent's. What was dropped and why:

    * Goal Achieved / Failed / Next screens - turn-by-turn only. The game plays
      the career here, so the bot never sees them.
    * The race-list ROI probe and the cultivation-result OCR heuristics
      ('rewards', 'bond level', 'total fans') - every result screen they guess
      at has a real template in `screens.py`, matched before this is reached.

    What is kept is the part that earns its place: the spark-selection
    interception, a visible Next button, and the corner click that advances
    screens nobody has templated.
    """
    # The Spark Selection screen and the reroll animation have no template, so
    # they land here. Intercept before the generic heuristics can click
    # something on them.
    career = getattr(ctx, 'career', None)

    # An unknown screen this blind click cannot advance is a trap: the clicks
    # trip the repetitive-click guard, the guard restarts the game, the game
    # comes back to the same screen. On 19 Sep that ran for five hours, ended
    # only by a daily-reset dialog the bot happened to know. After a minute of
    # frames nobody recognises, press the bottom nav's Home tab, which exists
    # on every screen outside a career and leads somewhere this app knows.
    if career is not None:
        seen = getattr(career, 'unknown_frames', 0) + 1
        career.unknown_frames = seen
        if seen % UNKNOWN_FRAMES_BEFORE_HOME == 0:
            log.warning(f"{seen} frames in a row match no screen - pressing Home "
                        f"to get back to something known")
            ctx.ctrl.click_by_point(HOME_TAB)
            time.sleep(2)
            return
    phase = getattr(career, 'spark_reroll_phase', '') if career else ''
    if phase in ('reroll_clicked', 'selected') and ctx.current_screen is not None:
        if is_spark_selection_screen(ctx.current_screen):
            spark.handle_spark_selection(ctx)
            return
        if phase == 'reroll_clicked':
            # most likely the reroll animation; tap a neutral spot to skip it
            log.debug("Waiting for the Spark Selection screen")
            ctx.ctrl.click_by_point(ESCAPE)
            time.sleep(1)
            return

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
