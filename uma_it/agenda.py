"""The race agenda picker: Edit -> My Agendas -> row 1 -> Overwrite -> close.

Three screens, driven as one state machine across frames. The executor calls a
handler once per frame and nothing carries over inside a function, so the phase
lives on `ctx.career` and each call decides what this frame should do.

Phases, in the order a run passes through them:

    ''              nothing in flight
    'opening'       Edit clicked; the editor is expected next
    'list'          My Agendas clicked; the slot list is expected
    'load_clicked'  a row's Load List clicked; the Overwrite dialog is expected
    'loaded'        overwrite confirmed; close the editor
    'done'          finished, or given up - either way stop touching these

The flow is started elsewhere: the Final Confirmation handler in `start.py`
sets the phase to 'opening', counts a step, and clicks Edit. In the parent that
handler lived in a different module and these attribute names were a
cross-module interface that could be renamed on one side only. Here both ends
are in this package.

## Row 1, and why the rule is that blunt

The user copies the agenda they want into the first slot. Nothing is matched by
name, and nothing is chosen by the user per task. Both of the more obvious
designs were tried and both failed the same way - by silently running the wrong
schedule, which looks exactly like running the right one:

* **By position** clicked the topmost *visible* row without knowing which row
  that was. The list opens wherever it was last left, so the top button is only
  row 1 when the list is scrolled to the top. Fifteen careers ran a four-race
  agenda before anyone noticed.
* **By name** fixed that and added a blank state. A task saved with the field
  empty disabled the picker, and eleven careers ran the game's 8-race default.

So the scrollbar is read first and nothing is clicked until it says row 1 is on
top. **An unreadable scrollbar is never treated as row 1** - that assumption is
the original bug. Row names are still OCR'd, but only for the log line.
"""
import time

import bot.base.log as logger

from uma_it.asset.point import (
    AGENDA_MY_AGENDAS,
    AGENDA_CLOSE,
    AGENDA_OVERWRITE_CONFIRM,
    AGENDA_OVERWRITE_CANCEL,
)
from uma_it.parse import (
    agenda_first_visible_row,
    agenda_load_buttons,
    agenda_row_names,
)

log = logger.get_logger(__name__)

# How many frames the whole flow may take before it gives up and starts the run
# on whatever schedule the game already has. Without a budget a flow that stops
# making progress ping-pongs between these screens until the repetitive-click
# guard restarts the app.
AGENDA_MAX_STEPS = 24


def _phase(ctx) -> str:
    return getattr(getattr(ctx, 'career', None), 'agenda_phase', '')


def _set_phase(ctx, phase: str) -> None:
    career = getattr(ctx, 'career', None)
    if career is not None:
        career.agenda_phase = phase
        career.agenda_waits = 0


def _wait(ctx, limit: int = 3) -> bool:
    """True while it is still worth sitting out a frame.

    The screens either side of a Load List click flicker for a second or two
    before the overwrite dialog lands, and closing out on that flicker is what
    made every run load its agenda twice.
    """
    career = getattr(ctx, 'career', None)
    waited = getattr(career, 'agenda_waits', 0) + 1
    if career is not None:
        career.agenda_waits = waited
    return waited <= limit


def _step(ctx) -> bool:
    """Count one frame of the flow; False once it has taken too many."""
    career = getattr(ctx, 'career', None)
    steps = getattr(career, 'agenda_steps', 0) + 1
    if career is not None:
        career.agenda_steps = steps
    if steps > AGENDA_MAX_STEPS:
        log.warning(f"Agenda picker: giving up after {steps} steps - starting the run "
                    "on the schedule the game already has")
        _set_phase(ctx, 'done')
        return False
    return True


def script_agenda(ctx) -> None:
    """The Agenda editor - the race grid behind the start dialog's Edit button.

    Only reached because this flow clicked Edit, so the job is to go on to the
    slot list and, once a slot has loaded, close back to the start dialog.
    """
    phase = _phase(ctx)

    # 'Agenda' and 'My Agendas' are 0.75 similar, so a smudged title can read
    # as the other one. The slot list is the screen with the green "Load List"
    # buttons down its right side - trust that over the title.
    if phase == 'list' and len(agenda_load_buttons(ctx.ctrl.get_screen())) >= 2:
        script_my_agendas(ctx)
        return

    if phase == 'opening':
        if not _step(ctx):
            ctx.ctrl.click_by_point(AGENDA_CLOSE)
            return
        log.info("Agenda editor - opening the saved agenda list")
        _set_phase(ctx, 'list')
        ctx.ctrl.click_by_point(AGENDA_MY_AGENDAS)
        time.sleep(1)
        return

    if phase == 'loaded':
        log.info("Agenda loaded - closing the editor")
        _set_phase(ctx, 'done')
        ctx.ctrl.click_by_point(AGENDA_CLOSE)
        time.sleep(1)
        return

    if phase == 'load_clicked':
        # The overwrite dialog was asked for but has not drawn; this frame is
        # the gap. Sit still - clicking here throws the flow back to the start
        # dialog and costs a second trip through it.
        #
        # This is also where the known first-click stumble shows up: the first
        # Load List click of a run reliably fails to raise the dialog, the wait
        # budget runs out, the list is reopened and the second click works,
        # costing about ten seconds. Three explanations - transient flicker,
        # swipe-versus-tap, and the list entering then backing out - were each
        # disproved by measurement, so the cause is genuinely unknown and a
        # guess here would be the fourth.
        #
        # One possibility has since been closed off. The title on these frames
        # reads 'Agenda', but the two screens are 0.75 similar, so the list
        # might never have closed and only the title been misread. Counting the
        # Load List buttons separates them, and it is 0 on every occurrence:
        # the list really does close. Whatever remains is about the game's
        # response, not the bot's perception.
        try:
            n = len(agenda_load_buttons(ctx.ctrl.get_screen()))
        except Exception:
            n = -1
        if _wait(ctx):
            log.info(f"Agenda editor while a load is in flight - waiting for the "
                     f"overwrite dialog (load buttons visible: {n})")
            return
        log.warning(f"Agenda load never raised the overwrite dialog "
                    f"(load buttons visible: {n}) - reopening the list")
        _set_phase(ctx, 'list')
        ctx.ctrl.click_by_point(AGENDA_MY_AGENDAS)
        time.sleep(1)
        return

    # nothing of ours in flight: back out to the start dialog
    log.info(f"Agenda editor with nothing in flight (phase {phase!r}) - closing it")
    ctx.ctrl.click_by_point(AGENDA_CLOSE)
    time.sleep(1)


def script_my_agendas(ctx) -> None:
    """The saved agenda slots, three visible at a time. Scroll to the top of
    the list and load row 1.

    See the module docstring for why row 1 is the whole selection rule and why
    an unreadable scrollbar loads nothing.
    """
    phase = _phase(ctx)
    if phase == 'load_clicked':
        # The row has been clicked and the overwrite dialog is on its way.
        # Waiting beats closing the list and starting over.
        if _wait(ctx):
            log.info("Agenda list still up after the load click - waiting for the "
                     "overwrite dialog")
            return
        log.warning("Agenda load click did not take - trying the row again")
        _set_phase(ctx, 'list')
        return
    if phase != 'list':
        log.info(f"Agenda list with nothing in flight (phase {phase!r}) - closing it")
        ctx.ctrl.click_by_point(AGENDA_CLOSE)
        time.sleep(1)
        return
    if not _step(ctx):
        ctx.ctrl.click_by_point(AGENDA_CLOSE)
        return

    screen = ctx.ctrl.get_screen()
    buttons = agenda_load_buttons(screen)
    if not buttons:
        log.warning("Agenda list: no Load List buttons found - nudging the list "
                    "and retrying")
        ctx.ctrl.swipe(x1=360, y1=950, x2=360, y2=730, duration=600, name="agenda list")
        return

    first = agenda_first_visible_row(screen)
    if first is None:
        # Never assume row 1 here. An unreadable scrollbar is exactly the state
        # where the top button could be any row, so scroll up and look again;
        # the step budget ends this if it never becomes readable.
        log.warning("Agenda list: cannot read the scrollbar - scrolling to the top "
                    "before loading anything")
        ctx.ctrl.swipe(x1=360, y1=500, x2=360, y2=940, duration=600, name="agenda list")
        return
    if first > 1:
        log.info(f"Agenda list starts at row {first} - scrolling up to row 1")
        ctx.ctrl.swipe(x1=360, y1=500, x2=360, y2=940, duration=600, name="agenda list")
        return

    # Row 1 is on top: its Load List is the first button down the list.
    x, y = buttons[0]
    # The name is read only so the log says which agenda a run actually loaded.
    # Nothing branches on it - a bad read costs a vague log line, not a career.
    name = (agenda_row_names(screen, buttons[:1]) or [''])[0]
    log.info(f"Agenda: loading row 1{f' named {name!r}' if name else ''}")
    _set_phase(ctx, 'load_clicked')
    ctx.ctrl.click(x, y, "Load agenda row 1")
    time.sleep(1)


def script_agenda_overwrite(ctx) -> None:
    """Confirms loading a saved agenda over the current schedule.

    The game warns that the replaced schedule cannot be retrieved, so only ever
    confirm the dialog this flow opened; anything else is cancelled.
    """
    if _phase(ctx) != 'load_clicked':
        log.warning("Overwrite dialog with no agenda load in progress - cancelling")
        ctx.ctrl.click_by_point(AGENDA_OVERWRITE_CANCEL)
        time.sleep(1)
        return
    log.info("Agenda row 1: confirming the overwrite")
    _set_phase(ctx, 'loaded')
    ctx.ctrl.click_by_point(AGENDA_OVERWRITE_CONFIRM)
    time.sleep(1)
