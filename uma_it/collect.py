"""Collecting the result once a run finishes.

A chain of result screens - stats, ratings, the cup - each of which needs one
click. The only one carrying a decision is the finish screen, which is where a
career either ends or goes off to buy skills.
"""
import bot.base.log as logger

from uma_it.asset.point import (
    CULTIVATE_RESULT_CONFIRM,
    CULTIVATE_FINISH_CONFIRM,
    CULTIVATE_LEVEL_RESULT_CONFIRM,
    HISTORICAL_RATING_UPDATE_CONFIRM,
    SCENARIO_RATING_UPDATE_CONFIRM,
    CULTIVATE_RECEIVE_CUP_CLOSE,
)

log = logger.get_logger(__name__)


def _confirm(point, what: str):
    """A result screen that needs one click and carries no decision."""
    def action(ctx):
        log.info(what)
        ctx.ctrl.click_by_point(point)
    return action


script_cultivate_result = _confirm(CULTIVATE_RESULT_CONFIRM,
                                   "Cultivation Result - confirming")
script_cultivate_level_result = _confirm(CULTIVATE_LEVEL_RESULT_CONFIRM,
                                         "Level Result - confirming")
script_historical_rating_update = _confirm(HISTORICAL_RATING_UPDATE_CONFIRM,
                                           "Historical Rating Update - confirming")
script_scenario_rating_update = _confirm(SCENARIO_RATING_UPDATE_CONFIRM,
                                         "Scenario Rating Update - confirming")
script_receive_cup = _confirm(CULTIVATE_RECEIVE_CUP_CLOSE,
                              "Cup received - closing")


def script_cultivate_finish(ctx):
    """The end-of-career screen: buy skills, or finish.

    With `skip_learn_skill` - the default, and how the loop is actually run -
    this goes straight to Confirm and skips the skill screen entirely.

    Skill buying is not implemented in this app yet, so a task that asks for it
    is told so and the career is still finished rather than being left sitting
    on this screen. The parent's version of this handler is 124 lines, of which
    all but a dozen are the manual-purchase mode: it POSTs to the web server
    and then blocks the bot thread in a `while True` polling loop, with a bare
    `input()` as its fallback. None of that comes across. When skill buying is
    written here, it gets a design that does not block the executor.
    """
    career = ctx.career
    if not career.career_finished:
        if getattr(ctx.task.detail, 'skip_learn_skill', True):
            log.info("Skill buying is off for this task - skipping the skill sweep")
        else:
            log.warning("Skill buying is not implemented in this app yet - "
                        "finishing the career without it")
        career.career_finished = True
    ctx.ctrl.click_by_point(CULTIVATE_FINISH_CONFIRM)
