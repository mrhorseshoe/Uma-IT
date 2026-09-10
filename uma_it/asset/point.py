"""Click points for the Independent Training path - 38 of the old module's 106.

Coordinates are moved verbatim from the original project; each was calibrated
against the live game at 720x1280.
"""
from bot.base.common import Area, Coordinate
from bot.base.point import ClickPoint, ClickPointType
from uma_it.asset.template import *

# cultivate
TO_CULTIVATE_SCENARIO_CHOOSE = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(545, 1085), "Go to Scenario Selection", None)
TO_CULTIVATE_PREPARE_NEXT = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(355, 1080), "Cultivation Preparation - Next Step")
TO_CULTIVATE_PREPARE_AUTO_SELECT = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(518, 972), "Cultivation Preparation - Auto Select")
TO_CULTIVATE_PREPARE_INCLUDE_GUEST = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(279, 694), "Cultivation Preparation - Include Guest")
TO_CULTIVATE_PREPARE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(519, 831), "Cultivation Preparation - Confirm")
CULTIVATE_FINAL_CHECK_START = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(500, 1185), "Start Cultivation")
FINAL_CONFIRMATION_TAB_INDEPENDENT = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(530, 216), "Final Confirmation - Independent Training tab")
INDEPENDENT_TRAINING_RESULTS_OK = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1178), "Independent Training Results - OK")
# Race agenda picker, reached from the Independent Training tab of the Final
# Confirmation dialog: Edit -> My Agendas -> a slot's "Load List" -> Overwrite.
AGENDA_EDIT = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(628, 614), "Final Confirmation - Edit Agenda")
AGENDA_MY_AGENDAS = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(601, 1088), "Agenda - My Agendas")
AGENDA_CLOSE = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1182), "Agenda - Close")
AGENDA_OVERWRITE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(517, 918), "Agenda - Overwrite the current schedule")
AGENDA_OVERWRITE_CANCEL = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(202, 918), "Agenda - Cancel the overwrite")
# "Independent Training" dialog, shown when CAREER is pressed on Home with a
# run pending. Its green Career button enters the run; "Delete Data" sits at the
# top right and must never be touched.
INDEPENDENT_TRAINING_PENDING_CAREER = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(517, 827), "Independent Training - enter the pending run")
# "Choose Career Mode" dialog, shown while a trainer event is running
CAREER_MODE_NORMAL = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 225), "Choose Career Mode - Normal Mode")
CAREER_MODE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(517, 1182), "Choose Career Mode - Confirm")
TO_FOLLOW_SUPPORT_CARD_SELECT = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(570, 680), "Borrow Support Card")
FOLLOW_SUPPORT_CARD_SELECT_REFRESH = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(650, 1010), "Borrow Support Card - Refresh")
GOAL_ACHIEVE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(370,1110), "Goal Achieved - Confirm", None)
GOAL_FAIL_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(370,1190), "Goal Failed - Confirm", None)
NEXT_GOAL_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360,1110), "Next Goal - Confirm", None)
NETWORK_ERROR_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(520,835), "Network Error - Confirm", None)
CULTIVATE_RECEIVE_CUP_CLOSE = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(365,920), "Receive Cup - Close", None)
CULTIVATE_FINISH_LEARN_SKILL = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(215, 1050), "Cultivation Complete - Learn Skills", None)
CULTIVATE_FINISH_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(512,1050), "Cultivation Complete - Confirm", None)
CULTIVATE_FINISH_CONFIRM_AGAIN = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(520,924), "Cultivation Complete - Confirm Again (Abandon remaining skill points)", None)
CULTIVATE_RESULT_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(360,1185), "Cultivation Result - Confirm", None)
CULTIVATE_FINISH_RETURN_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(190, 835), "Cultivation End - Return", None)
CULTIVATE_LEARN_SKILL_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(360,1082), "Skill Learning - Confirm", None)
CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE,None, Coordinate(516,1185), "Skill Learning - Confirm Again", None)
RETURN_TO_CULTIVATE_FINISH = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(90, 1190), "Return to Cultivation Interface", None)
CULTIVATE_LEVEL_RESULT_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1175), "Cultivation Level - Next Page", None)
CULTIVATE_FACTOR_RECEIVE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1175), "Factor Acquisition - Next Page", None)
CULTIVATE_FACTOR_REROLL_SKIP = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(513, 1178), "Spark Reroll - Confirm Without Rerolling", None)
HISTORICAL_RATING_UPDATE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1115), "Historical Rating Update - Next Page", None)
SCENARIO_RATING_UPDATE_CONFIRM = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1115), "Historical Rating Update - Next Page", None)
STORY_REWARDS_COLLECTED_CLOSE = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(360, 1180), "Story Rewards Collected - Close", None)
ESCAPE = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(5, 715), "escape", None)

# --- dialogs that only script_info handled in the parent ------------------
# Not reachable from any screen definition, which is why they arrive after the
# 38 above. Both are copied verbatim; see uma_it/dialogs.py for what fires them.

# The TP recovery confirm. Pressed only when the task authorises spending.
TO_RECOVER_TP = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(520, 830), "Recover Training Points", None)

# The 'Race Details' dialog's confirm. Rare on this path - three frames in 26
# careers - but the parent clicks it, so this app does too.
CULTIVATE_GOAL_RACE_INTER_3 = ClickPoint(ClickPointType.CLICK_POINT_TYPE_COORDINATE, None, Coordinate(520,920), "Start Career Race - Confirm", None)
