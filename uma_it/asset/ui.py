"""The 22 screens an Independent Training career can reach.

Absent on purpose: everything that only appears while playing a career turn by
turn or racing. In Independent Training the game plays the career itself, so
the bot never sees a training screen, a race, an event choice or a goal dialog.
"""
from bot.base.resource import UI
import uma_it.asset.template as template

# Home: the bottom nav with the Home tab lit, and *not* a career setup screen or
# a dialog on top of it.
#
# The nav bar alone cannot tell Home from the screens reached from it -
# Scenario Select, Legacy Select and Support Formation all keep the Home tab
# lit - and nothing on Home itself is both stable and Home's alone: measured
# over 19 Home frames from 19-25 Sep, every region that stays still (team rank,
# the TP bar) is on the other screens too, and everything that is Home's (the
# trainee, the banners, the badges) keeps changing. So Home is the nav bar
# *minus* the screens that share it, each recognised by its own template, which
# is reliable where the nav bar is not: 1.000 on its own screen, at most 0.54
# on any Home frame.
#
# What this replaced was broken both ways. The old crop of the Home tab matched
# 0 of those 19 Home frames and scored 0.998 on Scenario Select, so the Home
# handler ran on setup screens and pressed its fixed CAREER point there - the
# Sparks button on Legacy Select, the Perks button on Support Formation, for
# hours at a time. Verified through the executor's own matcher: all 19 Home
# frames now resolve to MAIN_MENU, every setup capture to its own screen, a
# dialog over Home to INFO, and none of 93 other captures to Home.
MAIN_MENU = UI("MAIN_MENU", [template.UI_MAIN_MENU_2], [
    template.UI_INFO,
    template.UI_CULTIVATE_SCENARIO_SELECT,
    template.UI_CULTIVATE_UMAMUSUME_SELECT,
    template.UI_CULTIVATE_EXTEND_UMAMUSUME_SELECT,
    template.UI_CULTIVATE_SUPPORT_CARD_SELECT,
    template.UI_CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT,
])
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
