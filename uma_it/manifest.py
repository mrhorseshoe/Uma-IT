"""What makes this app real to the engine.

`bot/engine/executor.py` looks up `APP_MANIFEST_LIST[task.app_name]` and drives
whatever it finds: the manifest's `ui_list` is matched against every frame, the
resulting screen is handed to `script`, and `build_task` / `build_context`
create the objects those handlers work on. Registering an app is one call to
`register_app`; `main.py` makes it.

The handler table is filled in as handlers are written. A screen with no entry
is a logged warning, never a silent drop - the parent project printed to stdout
and moved on, which meant an unhandled screen looked exactly like a handled
one.
"""
from typing import Callable, Dict

from bot.base.manifest import AppManifest
from bot.base.resource import NOT_FOUND_UI, UI
import bot.base.log as logger

from uma_it.context import build_context
from uma_it.screens import scan_ui_list
from uma_it.task import APP_NAME, UmaItTaskType, build_task

log = logger.get_logger(__name__)

# The Global client. Same package as the parent project - it is the same game.
APP_PACKAGE_NAME = "com.cygames.umamusume"
APP_ACTIVITY_NAME = "jp.co.cygames.umamusume_activity.UmamusumeActivity"


# screen -> handler, per task type. Empty entries are screens whose handler is
# not written yet; see STATUS.md for the order they are being done in.
script_dicts: Dict[UmaItTaskType, Dict[UI, Callable]] = {
    UmaItTaskType.CAREER: {
        # every dialog with the green diagonal header
        # INFO: dialogs.script_dialog,

        # entering a career
        # MAIN_MENU: ...,
        # CULTIVATE_SCENARIO_SELECT: ...,
        # CULTIVATE_UMAMUSUME_SELECT: ...,
        # CULTIVATE_EXTEND_UMAMUSUME_SELECT: ...,
        # CULTIVATE_SUPPORT_CARD_SELECT: ...,
        # CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT: ...,
        # CULTIVATE_FINAL_CHECK: ...,

        # the run itself
        # INDEPENDENT_TRAINING_WAIT: career.script_wait,
        # INDEPENDENT_TRAINING_RESULTS: ...,

        # collecting the result
        # CULTIVATE_RESULT / _1 / _2, CULTIVATE_FINISH, CULTIVATE_LEVEL_RESULT,
        # HISTORICAL_RATING_UPDATE, SCENARIO_RATING_UPDATE, RECEIVE_CUP

        # optional: CULTIVATE_LEARN_SKILL, CONFIRMATION_LEARNSKILL_BUTTON,
        # FACTOR_RECEIVE, FACTOR_REROLL

        # NOT_FOUND_UI: the blind fallback. It must exist before the app is
        # run: with no entry the executor does nothing on an unrecognised
        # frame, and several screens on this path are only ever advanced by
        # that fallback's click.
    }
}


def exec_script(ctx):
    """Dispatch one frame to its handler."""
    table = script_dicts.get(ctx.task.task_type)
    if table and ctx.current_ui in table:
        table[ctx.current_ui](ctx)
        return
    name = getattr(ctx.current_ui, 'ui_name', ctx.current_ui)
    if ctx.current_ui is NOT_FOUND_UI:
        log.warning("uma-it: no fallback handler yet - frame unrecognised and "
                    "nothing was clicked")
    else:
        log.warning("uma-it: no handler for screen %s", name)


# before_hook / after_hook are deliberately None. What the parent project runs
# in them, and what that means here:
#
#   apply_rules()   - a no-op for this app, provably. Its rule table has one
#                     key, TASK_EXECUTE_MODE_TEAM_TRIALS, and an Independent
#                     Training task runs in LOOP mode, so the lookup returns []
#                     and the function returns False before doing any work.
#
#   before_hook     - its two branches are the Home gift popup and the Resume
#                     Career dialog. The first returns immediately when the
#                     task is an Independent Training one, by an explicit check
#                     added there. The second defers to the handler when the
#                     dialog is the Independent Training pending-run one, which
#                     on this path it is.
#
#   after_hook      - presses the game's Skip buttons (BTN_SKIP, BTN_SKIP_OFF,
#                     BTN_SKIP_SPEED_1), then does turn-by-turn work that
#                     cannot apply here.
#
# The skip presses are UNRESOLVED and must be settled before the first live
# run. They may be what dismisses the result animations at the end of a career.
# The 26 careers' logs cannot answer it: clicks are logged at DEBUG
# (`click >> <name>` in bot/conn/u2_ctrl.py) and those logs are INFO, so the
# absence of "Skip" in them is not evidence. Settle it by running one career on
# the parent project at DEBUG and grepping for `click >> Skip`.
UmaItManifest = AppManifest(
    app_name=APP_NAME,
    app_package_name=APP_PACKAGE_NAME,
    app_activity_name=APP_ACTIVITY_NAME,
    build_context=build_context,
    build_task=build_task,
    ui_list=scan_ui_list,
    script=exec_script,
    before_hook=None,
    after_hook=None,
)
