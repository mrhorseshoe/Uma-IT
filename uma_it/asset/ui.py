"""The 22 screens an Independent Training career can reach.

Absent on purpose: everything that only appears while playing a career turn by
turn or racing. In Independent Training the game plays the career itself, so
the bot never sees a training screen, a race, an event choice or a goal dialog.
"""
from bot.base.resource import UI
import uma_it.asset.template as template

MAIN_MENU = UI("MAIN_MENU", [template.UI_MAIN_MENU], [])
# Same name and same handler: two ways of seeing one screen, the way
# CULTIVATE_RESULT already has three. Either match means Home.
MAIN_MENU_2 = UI("MAIN_MENU", [template.UI_MAIN_MENU_2], [])
GAME_LOADING = UI("GAME_LOADING", [template.UI_GAME_LOADING], [])
GAME_TITLE = UI("GAME_TITLE", [template.UI_GAME_TITLE], [])
CULTIVATE_SCENARIO_SELECT = UI("CULTIVATE_SCENARIO_SELECT", [template.UI_CULTIVATE_SCENARIO_SELECT], [])
CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT = UI("CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT",
                                          [template.UI_CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT], [])
CULTIVATE_UMAMUSUME_SELECT = UI("CULTIVATE_UMAMUSUME_SELECT",
                                [template.UI_CULTIVATE_UMAMUSUME_SELECT], [])
CULTIVATE_EXTEND_UMAMUSUME_SELECT = UI("CULTIVATE_EXTEND_UMAMUSUME_SELECT",
                                       [template.UI_CULTIVATE_EXTEND_UMAMUSUME_SELECT], [])
CULTIVATE_SUPPORT_CARD_SELECT = UI("CULTIVATE_SUPPORT_CARD_SELECT",
                                   [template.UI_CULTIVATE_SUPPORT_CARD_SELECT], [])
CULTIVATE_FINAL_CHECK = UI("CULTIVATE_FINAL_CHECK", [template.UI_CULTIVATE_FINAL_CHECK], [])
INDEPENDENT_TRAINING_WAIT = UI("INDEPENDENT_TRAINING_WAIT", [template.UI_INDEPENDENT_TRAINING_WAIT], [])
INDEPENDENT_TRAINING_RESULTS = UI("INDEPENDENT_TRAINING_RESULTS", [template.UI_INDEPENDENT_TRAINING_RESULTS], [])
INFO = UI("INFO", [template.UI_INFO], [])
CULTIVATE_RESULT = UI("CULTIVATE_RESULT", [template.UI_CULTIVATE_RESULT], [])
CULTIVATE_RESULT_1 = UI("CULTIVATE_RESULT", [template.UI_CULTIVATE_RESULT_1], [])
CULTIVATE_RESULT_2 = UI("CULTIVATE_RESULT", [template.UI_CULTIVATE_RESULT_2], [])
CULTIVATE_FINISH = UI("CULTIVATE_FINISH", [template.UI_CULTIVATE_FINISH], [])
CULTIVATE_LEARN_SKILL = UI("CULTIVATE_LEARN_SKILL",
                           [template.UI_CULTIVATE_LEARN_SKILL_1, template.UI_CULTIVATE_LEARN_SKILL_2], [])
CONFIRMATION_LEARNSKILL_BUTTON = UI("CONFIRMATION_LEARNSKILL_BUTTON",
                                    [template.UI_CONFIRMATION_LEARNSKILL_BUTTON], [])
RECEIVE_CUP = UI("CULTIVATE_RECEIVE_CUP",[template.UI_RECEIVE_CUP], [])
CULTIVATE_LEVEL_RESULT = UI("CULTIVATE_LEVEL_RESULT", [template.UI_CULTIVATE_LEVEL_RESULT], [])
# the "Sparks" label matches the reroll screen too, so FACTOR_RECEIVE must
# require the reroll button to be absent (detect_ui races UIs in parallel)
FACTOR_RECEIVE = UI("FACTOR_RECEIVE", [template.UI_FACTOR_RECEIVE], [template.UI_FACTOR_REROLL])
FACTOR_REROLL = UI("FACTOR_REROLL", [template.UI_FACTOR_REROLL], [])
HISTORICAL_RATING_UPDATE = UI("HISTORICAL_RATING_UPDATE", [template.UI_HISTORICAL_RATING_UPDATE], [])
# Named for itself, unlike in the parent project, where the label on the line
# above was copied onto it. It is a distinct screen with its own template and
# its own handler there, so every Scenario Rating Update frame logged as a
# Historical one. A ui_name is a label, not calibration; fixing it costs
# nothing and stops the logs lying.
SCENARIO_RATING_UPDATE = UI("SCENARIO_RATING_UPDATE", [template.UI_SCENARIO_RATING_UPDATE], [])
