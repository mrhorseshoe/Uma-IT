"""The screens an Independent Training career can reach.

Every UI in `scan_ui_list` is template-matched against every frame in a thread
pool, roughly once a second for the length of a run. A screen that cannot occur
on this path is therefore not merely clutter - it is work repeated about three
thousand times per career.

Twenty-two, against the parent project's forty-nine. What is deliberately
absent is everything that only appears while a career is played turn by turn or
raced: training screens, races, event choices, goal dialogs. In Independent
Training the game plays the career itself, so the bot never sees them. Aoharu
Cup, the catch-doll minigame and the Fujikiseki show are inherited from an
upstream project and do not occur on Global at all.
"""
from uma_it.asset.ui import (
    # the game coming up, which is where a restart lands
    GAME_LOADING,
    GAME_TITLE,
    # entering a career
    MAIN_MENU,
    MAIN_MENU_2,
    CULTIVATE_SCENARIO_SELECT,
    CULTIVATE_UMAMUSUME_SELECT,
    CULTIVATE_EXTEND_UMAMUSUME_SELECT,
    CULTIVATE_SUPPORT_CARD_SELECT,
    CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT,
    CULTIVATE_FINAL_CHECK,
    # the run itself
    INDEPENDENT_TRAINING_WAIT,
    INDEPENDENT_TRAINING_RESULTS,
    # collecting the result
    CULTIVATE_RESULT,
    CULTIVATE_RESULT_1,
    CULTIVATE_RESULT_2,
    CULTIVATE_FINISH,
    CULTIVATE_LEVEL_RESULT,
    HISTORICAL_RATING_UPDATE,
    SCENARIO_RATING_UPDATE,
    RECEIVE_CUP,
    # optional features: off in the default task, supported
    CULTIVATE_LEARN_SKILL,
    CONFIRMATION_LEARNSKILL_BUTTON,
    FACTOR_RECEIVE,
    FACTOR_REROLL,
    # every dialog with the green diagonal header
    INFO,
)

# Ordering is not significant - the executor matches all of them against each
# frame and collects whichever assert true. Grouped here by phase for reading.
scan_ui_list = [
    # First, because they are where a restart lands and the bot restarts the
    # game itself several times a day.
    GAME_LOADING,
    GAME_TITLE,

    MAIN_MENU,
    MAIN_MENU_2,
    CULTIVATE_SCENARIO_SELECT,
    CULTIVATE_UMAMUSUME_SELECT,
    CULTIVATE_EXTEND_UMAMUSUME_SELECT,
    CULTIVATE_SUPPORT_CARD_SELECT,
    CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT,
    CULTIVATE_FINAL_CHECK,

    INDEPENDENT_TRAINING_WAIT,
    INDEPENDENT_TRAINING_RESULTS,

    CULTIVATE_RESULT,
    CULTIVATE_RESULT_1,
    CULTIVATE_RESULT_2,
    CULTIVATE_FINISH,
    CULTIVATE_LEVEL_RESULT,
    HISTORICAL_RATING_UPDATE,
    SCENARIO_RATING_UPDATE,
    RECEIVE_CUP,

    CULTIVATE_LEARN_SKILL,
    CONFIRMATION_LEARNSKILL_BUTTON,
    FACTOR_RECEIVE,
    FACTOR_REROLL,

    INFO,
]
