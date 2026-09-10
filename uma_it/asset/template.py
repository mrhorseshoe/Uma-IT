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
UI_MAIN_MENU = Template("MAIN_MENU", UI_TEMPLATE_PATH)
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
