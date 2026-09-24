"""Templates for the Independent Training path - 28 of the old module's 179.

Every crop here is copied byte-for-byte from the original project. They are
calibrated against the live game and re-cropping them is how this project's
worst bugs were made, so they are moved, never redrawn.
"""
from bot.base.resource import Template
from bot.base.common import Area, ImageMatchConfig

UI_TEMPLATE_PATH = "/uma_it/ui"
REF_TEMPLATE_PATH = "/uma_it/ref"

UI_INFO = Template("INFO", UI_TEMPLATE_PATH)
# The two screens the game shows while it is coming up, and the only two the
# bot sees after a restart - which it performs itself, through the watchdog and
# the repetitive-click guard, several times a day. Until they were named, both
# fell to the blind fallback: a corner click every frame, eleven of them, the
# guard restarting the game, and the same screen again. Turnovers on 24 Sep
# cost two to four restarts each.
#
# "Now Loading" is the text, not the comic panel above it, which rotates. The
# title screen is matched on the game's logo rather than the key art behind it,
# which rotates with events. Both crops carry their own search region, so a
# frame that is neither costs two small correlations.
UI_GAME_LOADING = Template("GAME_LOADING", UI_TEMPLATE_PATH,
                           ImageMatchConfig(match_area=Area(380, 1180, 700, 1280)))
UI_GAME_TITLE = Template("GAME_TITLE", UI_TEMPLATE_PATH,
                         ImageMatchConfig(match_area=Area(40, 820, 700, 1000)))
UI_MAIN_MENU = Template("MAIN_MENU", UI_TEMPLATE_PATH)
# A second way to recognise Home, because the first one has stopped working.
# UI_MAIN_MENU is the bottom-nav Home tab, chosen because that tab "does not
# change" - and then an event decorated it. Measured against three real Home
# frames five days apart it scores 0.562, 0.715 and 0.784 against a threshold
# of 0.86, so most Home frames are not recognised as Home at all. The frames
# that miss fall to the blind fallback, which taps a corner once a frame until
# the click guard restarts the game: two to four restarts per turnover on
# 24 Sep, every one of them landing back on the loading screen.
#
# This crop is the Race and Scout tabs at the bottom right, picked by diffing
# those same three frames for a region that had not changed at all: mean
# difference 0.00, and it scores 1.000 on all three while no other captured
# screen beats 0.721. Kept alongside the old crop rather than replacing it -
# either one matching is enough, and the old one is still calibrated for
# whatever it does still match.
UI_MAIN_MENU_2 = Template("MAIN_MENU_2", UI_TEMPLATE_PATH,
                          ImageMatchConfig(match_area=Area(500, 1160, 720, 1280)))
UI_CULTIVATE_SCENARIO_SELECT = Template("CULTIVATE_SCENARIO_SELECT", UI_TEMPLATE_PATH)
UI_CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT = Template("CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT", UI_TEMPLATE_PATH)
UI_CULTIVATE_SUPPORT_CARD_SELECT = Template("CULTIVATE_SUPPORT_CARD_SELECT", UI_TEMPLATE_PATH)
UI_CULTIVATE_EXTEND_UMAMUSUME_SELECT = Template("CULTIVATE_EXTEND_UMAMUSUME_SELECT", UI_TEMPLATE_PATH)
UI_CULTIVATE_UMAMUSUME_SELECT = Template("CULTIVATE_UMAMUSUME_SELECT", UI_TEMPLATE_PATH)
UI_CULTIVATE_FINAL_CHECK = Template("CULTIVATE_FINAL_CHECK", UI_TEMPLATE_PATH)
# Independent Training: the screen the game parks on while the career plays
# itself out in real time (about 50 minutes), showing "Time Left ... left".
UI_INDEPENDENT_TRAINING_WAIT = Template("INDEPENDENT_TRAINING_WAIT", UI_TEMPLATE_PATH)
# ... and the Training Log a finished run parks on, which has to be dismissed
# before the usual Complete Career flow appears
UI_INDEPENDENT_TRAINING_RESULTS = Template("INDEPENDENT_TRAINING_RESULTS", UI_TEMPLATE_PATH)
UI_CULTIVATE_RACE_LIST_2 = Template("CULTIVATE_RACE_LIST_2", UI_TEMPLATE_PATH)
UI_CULTIVATE_RESULT = Template("CULTIVATE_RESULT", UI_TEMPLATE_PATH)
UI_CULTIVATE_RESULT_1 = Template("CULTIVATE_RESULT_1", UI_TEMPLATE_PATH)
UI_CULTIVATE_RESULT_2 = Template("CULTIVATE_RESULT_2", UI_TEMPLATE_PATH)
UI_CULTIVATE_LEARN_SKILL_1 = Template("CULTIVATE_LEARN_SKILL_1", UI_TEMPLATE_PATH)
UI_CULTIVATE_LEARN_SKILL_2 = Template("CULTIVATE_LEARN_SKILL_2", UI_TEMPLATE_PATH)
UI_CONFIRMATION_LEARNSKILL_BUTTON = Template("CONFIRMATION_LEARNSKILL_BUTTON", UI_TEMPLATE_PATH)
UI_CULTIVATE_FINISH = Template("CULTIVATE_FINISH", UI_TEMPLATE_PATH)
UI_RECEIVE_CUP = Template("RECEIVE_CUP", UI_TEMPLATE_PATH)
UI_CULTIVATE_LEVEL_RESULT = Template("CULTIVATE_LEVEL_RESULT", UI_TEMPLATE_PATH)
UI_FACTOR_RECEIVE = Template("FACTOR_RECEIVE", UI_TEMPLATE_PATH)
# "Reroll Sparks" button on the end-of-run sparks screen (July 2026 patch)
UI_FACTOR_REROLL = Template("FACTOR_REROLL", UI_TEMPLATE_PATH)
UI_HISTORICAL_RATING_UPDATE = Template("HISTORICAL_RATING_UPDATE", UI_TEMPLATE_PATH)
UI_SCENARIO_RATING_UPDATE = Template("SCENARIO_RATING_UPDATE", UI_TEMPLATE_PATH)
REF_CULTIVATE_SUPPORT_CARD_EMPTY = Template("CULTIVATE_SUPPORT_CARD_EMPTY", REF_TEMPLATE_PATH)
REF_BORROW_CARD = Template("borrow_card", REF_TEMPLATE_PATH)
# The green (selected) "Independent Training" tab on the Final Confirmation
# dialog. It only matches while that tab is active, so its presence is what
# tells the two career modes apart - the inactive tab is white with dark text.
REF_INDEPENDENT_TRAINING_TAB = Template("independent_training_tab", REF_TEMPLATE_PATH)
REF_NEXT = Template("next", REF_TEMPLATE_PATH)

# Team trials, run while the loop waits for TP - see uma_it/team_trials.py.
# All nine crops are the parent project's, moved byte for byte.
REF_TT_HOME = Template("tt_home_gift", REF_TEMPLATE_PATH)
REF_TT_TEAM_TRIALS = Template("tt_team_trials", REF_TEMPLATE_PATH)
REF_TT_TEAM_RACE = Template("tt_team_race", REF_TEMPLATE_PATH)
REF_TT_SELECT_OPPONENT = Template("tt_select_opp", REF_TEMPLATE_PATH)
REF_TT_SEE_ALL = Template("tt_see_all", REF_TEMPLATE_PATH)
REF_TT_SEE_RESULTS = Template("tt_see_results", REF_TEMPLATE_PATH)
REF_TT_NEXT_RESULT = Template("tt_next2", REF_TEMPLATE_PATH)
# "You have no RP" - the session's expected end. Both are searched inside the
# region they occupy, because the crops are small enough to turn up elsewhere.
# The countdown screen's menu holds "To Home" - and "Give Up", which abandons
# the career, 330px to its right. This crop is why that click is never blind.
REF_TT_TO_HOME = Template("tt_to_home", REF_TEMPLATE_PATH)
REF_TT_CANT = Template("tt_cant_tt", REF_TEMPLATE_PATH,
                       ImageMatchConfig(match_area=Area(369, 586, 439, 609)))
REF_TT_CANT_2 = Template("tt_cant_tt2", REF_TEMPLATE_PATH,
                         ImageMatchConfig(match_area=Area(391, 43, 433, 81)))

# --- required by the vendored engine ------------------------------------
# The engine reaches for these two by name. They are not part of any screen
# definition, which is why they arrive separately from the 28 above.

# bot/conn/u2_ctrl.py safety_dont_click(): blocks a tap in the region
# (263..458, 559..808) when this marker is on screen.
REF_DONT_CLICK = Template("DONT_CLICK", REF_TEMPLATE_PATH)

# bot/conn/fetch.py read_mood(): the dashboard's motivation readout. Mood is a
# turn-by-turn concept and nothing in an Independent Training run branches on
# it - see STATUS.md before carrying this into the new UI.
REF_MOTIVATION_1 = Template("MOTIVATION_1", REF_TEMPLATE_PATH)
REF_MOTIVATION_2 = Template("MOTIVATION_2", REF_TEMPLATE_PATH)
REF_MOTIVATION_3 = Template("MOTIVATION_3", REF_TEMPLATE_PATH)
REF_MOTIVATION_4 = Template("MOTIVATION_4", REF_TEMPLATE_PATH)
REF_MOTIVATION_5 = Template("MOTIVATION_5", REF_TEMPLATE_PATH)
MOTIVATION_LIST = [REF_MOTIVATION_1, REF_MOTIVATION_2, REF_MOTIVATION_3,
                   REF_MOTIVATION_4, REF_MOTIVATION_5]

# --- entering a career ----------------------------------------------------
SCENARIO_TEMPLATE_PATH = "/uma_it/scenario"

# The scenario cards on the Scenario Select carousel. The carousel holds more
# scenarios than this app can start a run in, so the handler swipes until the
# one it wants matches rather than counting positions.
UI_SCENARIO_URA = Template("SCENARIO_URA", SCENARIO_TEMPLATE_PATH)
UI_SCENARIO_AOHARUHAI = Template("SCENARIO_AOHARUHAI", SCENARIO_TEMPLATE_PATH)
UI_SCENARIO_TRACKBLAZER = Template("SCENARIO_TRACKBLAZER", SCENARIO_TEMPLATE_PATH)
UI_SCENARIO_GRANDCONCERT = Template("SCENARIO_GRANDCONCERT", SCENARIO_TEMPLATE_PATH)

# The repeated label on each borrowable support card, used to find every card
# on the screen before reading its level and title.
REF_FOLLOW_SUPPORT_CARD_DETECT_LABEL = Template("FOLLOW_SUPPORT_CARD_DETECT_LABEL", REF_TEMPLATE_PATH)

# The repeated label on each spark row, used to walk the list one row at a
# time. Spark reroll only.
REF_FACTOR_DETECT_LABEL = Template("FACTOR_DETECT_LABEL", REF_TEMPLATE_PATH)

# --- restoring TP ---------------------------------------------------------
# The steps of the Recover TP flow, one screen each: the selection screen,
# the two confirms (item and carats take different ones), and the two result
# screens. TP_RECOVER_DRINK says a TP item is on offer at all.
REF_RECOVER_TP_1 = Template("RECOVER_TP_1", REF_TEMPLATE_PATH)
REF_RECOVER_TP_2 = Template("RECOVER_TP_2", REF_TEMPLATE_PATH)
REF_RECOVER_TP_2_CARROT = Template("RECOVER_TP_2_CARROT", REF_TEMPLATE_PATH)
REF_RECOVER_TP_3 = Template("RECOVER_TP_3", REF_TEMPLATE_PATH)
REF_RECOVER_TP_3_CARROT = Template("RECOVER_TP_3_CARROT", REF_TEMPLATE_PATH)
REF_TP_RECOVER_DRINK = Template("TP_RECOVER_DRINK", REF_TEMPLATE_PATH)

# The skill list: the repeated row label, the "already learned" marker, and the
# five hint-level badges. Skill buying only.
REF_SKILL_LIST_DETECT_LABEL = Template("SKILL_LIST_DETECT_LABEL", REF_TEMPLATE_PATH)
REF_SKILL_LEARNED = Template("SKILL_LEARNED", REF_TEMPLATE_PATH)
REF_HINT_LEVEL_1 = Template("hint_1", REF_TEMPLATE_PATH)
REF_HINT_LEVEL_2 = Template("hint_2", REF_TEMPLATE_PATH)
REF_HINT_LEVEL_3 = Template("hint_3", REF_TEMPLATE_PATH)
REF_HINT_LEVEL_4 = Template("hint_4", REF_TEMPLATE_PATH)
REF_HINT_LEVEL_5 = Template("hint_5", REF_TEMPLATE_PATH)
REF_HINT_LEVELS = [REF_HINT_LEVEL_1, REF_HINT_LEVEL_2, REF_HINT_LEVEL_3,
                   REF_HINT_LEVEL_4, REF_HINT_LEVEL_5]
