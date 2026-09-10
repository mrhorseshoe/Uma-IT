"""Collecting the result once a run finishes.

A chain of result screens - stats, ratings, the cup - each of which needs one
click. The only one carrying a decision is the finish screen, which is where a
career either ends or goes off to buy skills.
"""
import bot.base.log as logger

from uma_it.asset.point import (
    CULTIVATE_RESULT_CONFIRM,
    CULTIVATE_FINISH_CONFIRM,
    CULTIVATE_FINISH_LEARN_SKILL,
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

    With `skip_learn_skill` - the default, and how the loop is usually run -
    this goes straight to Confirm and never opens the skill screen.

    Otherwise it runs the sweep. The screen is visited more than once: buying
    skills spends points, and what was unaffordable on the first pass may be
    affordable after a gold skill supersedes a cheaper one, so it goes back for
    as long as the last visit actually selected something. A visit that selects
    nothing is the signal to confirm.

    The parent's version of this is 124 lines, of which all but a dozen are the
    manual-purchase mode - it POSTs to the web server and then blocks the bot
    thread in a `while True` poll, with a bare `input()` as its fallback. None
    of that is here.
    """
    career = ctx.career
    if getattr(ctx.task.detail, 'skip_learn_skill', True):
        if not career.career_finished:
            log.info("Skill buying is off for this task - skipping the skill sweep")
            career.career_finished = True
        ctx.ctrl.click_by_point(CULTIVATE_FINISH_CONFIRM)
        return

    if not career.career_finished:
        career.career_finished = True
        career.final_skill_sweep_active = True
        career.reset_skill_learn()
        log.info("Career finished - opening the skill screen")
        ctx.ctrl.click_by_point(CULTIVATE_FINISH_LEARN_SKILL)
        return

    if career.final_skill_sweep_active:
        if career.learn_skill_selected:
            # Something was bought last visit; there may be more within reach.
            career.reset_skill_learn()
            log.info("Skills bought - going back for another pass")
            ctx.ctrl.click_by_point(CULTIVATE_FINISH_LEARN_SKILL)
            return
        career.final_skill_sweep_active = False
        log.info("Nothing more to buy - finishing the career")

    ctx.ctrl.click_by_point(CULTIVATE_FINISH_CONFIRM)
