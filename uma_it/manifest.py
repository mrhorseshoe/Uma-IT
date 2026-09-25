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
from typing import Any, Callable, Dict

from bot.base.manifest import AppManifest
from uma_it import team_trials
from bot.base.resource import NOT_FOUND_UI, UI
import bot.base.log as logger

from uma_it.asset.ui import (
    INFO,
    GAME_LOADING,
    GAME_TITLE,
    MAIN_MENU,
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
    FACTOR_RECEIVE,
    FACTOR_REROLL,
    CULTIVATE_LEARN_SKILL,
    CONFIRMATION_LEARNSKILL_BUTTON,
)
from uma_it import career, collect, enter, skills, spark
from uma_it.context import build_context
from uma_it.dialogs import script_dialog, script_not_found_ui
from uma_it.screens import scan_ui_list
from uma_it.task import APP_NAME, UmaItTaskType, build_task
from uma_it import presets
from uma_it import skills_db
from uma_it import spark_db

log = logger.get_logger(__name__)


# --- routes this app adds to the engine's server --------------------------
# Registered here rather than in bot/server/handler.py: presets are a thing
# this app has, not something the engine should know about. Importing the
# server at module scope is how the parent does it too.
from bot.server.handler import server


@server.get("/api/skill-presets")
def list_skill_presets():
    return presets.read_all()


@server.post("/api/skill-presets")
def save_skill_preset(preset: Dict[str, Any]):
    try:
        return {"ret": 0, "name": presets.write(preset)}
    except Exception as e:
        log.warning(f"Could not save skill preset: {e}")
        return {"ret": 1, "msg": str(e)}


@server.delete("/api/skill-presets")
def delete_skill_preset(body: Dict[str, Any]):
    return {"ret": 0, "deleted": presets.delete(body.get("name", ""))}


@server.get("/api/sparks")
def list_sparks():
    """The spark vocabulary the dashboard offers as reroll targets.

    White only - blue and pink already have their own chips, and a green spark
    is a unique skill nobody can choose to inherit. Kind is returned so the
    picker can group skills, races and scenarios rather than showing one flat
    list of 273 names.
    """
    return [s for s in spark_db.load_all()
            if s.get('kind') in spark_db.WHITE_KINDS]


@server.get("/api/skills/source")
def skills_source():
    """Where the game database is, so the page knows whether to ask.

    `found` false is not an error - it is the first press on a machine whose
    install is somewhere unusual, and the page shows the picker.
    """
    found = skills_db.resolve()
    return {"remembered": skills_db.remembered_source(),
            "found": found,
            "using_user_list": skills_db.active_path() == skills_db.USER_PATH,
            # What the list in force was built from, so the page can say which
            # game version it is current to without a second request.
            "meta": skills_db.read_meta()}


@server.post("/api/skills/sync")
def sync_skills(body: Dict[str, Any] = None):
    """Add any skills the game knows and the list does not.

    `path` is whatever the user typed - the game folder, the master folder, or
    master.mdb itself. Empty means "use the remembered one, or look in the
    usual places".
    """
    return skills_db.sync(str((body or {}).get("path", "") or ""))


@server.post("/api/skills/prune")
def prune_skills(body: Dict[str, Any] = None):
    """Drop entries for skills the game does not have.

    Separate from the sync because this one deletes. It refuses outright if the
    database reads back implausibly small, rather than emptying the list.
    """
    return skills_db.prune(str((body or {}).get("path", "") or ""))


def _keep_catch_all_last():
    """Move the server's catch-all behind the routes registered here.

    `bot/server/handler.py` ends with `@server.get("/{whatever:path}")`, which
    serves the dashboard for any unmatched path. FastAPI matches in
    registration order, and this module can only register after importing that
    one - so without this, a GET added here is swallowed by the catch-all and
    answers with index.html instead of JSON. POST and DELETE are unaffected,
    the catch-all being GET-only, which is a confusing way to find out.

    This is very likely why the parent project reads its presets over POST.
    """
    routes = server.router.routes
    for route in [r for r in routes if getattr(r, 'path', '') == '/{whatever:path}']:
        routes.remove(route)
        routes.append(route)


_keep_catch_all_last()

# The Global client. Same package as the parent project - it is the same game.
APP_PACKAGE_NAME = "com.cygames.umamusume"
APP_ACTIVITY_NAME = "jp.co.cygames.umamusume_activity.UmamusumeActivity"


# screen -> handler, per task type. Empty entries are screens whose handler is
# not written yet; see STATUS.md for the order they are being done in.
script_dicts: Dict[UmaItTaskType, Dict[UI, Callable]] = {
    UmaItTaskType.CAREER: {
        # Every dialog with the green diagonal header, which on this path is
        # most frames. The router dispatches on the OCR'd title.
        INFO: script_dialog,

        # entering a career
        GAME_LOADING: enter.script_game_loading,
        GAME_TITLE: enter.script_game_title,
        MAIN_MENU: enter.script_main_menu,
        CULTIVATE_SCENARIO_SELECT: enter.script_scenario_select,
        CULTIVATE_UMAMUSUME_SELECT: enter.script_umamusume_select,
        CULTIVATE_EXTEND_UMAMUSUME_SELECT: enter.script_extend_umamusume_select,
        CULTIVATE_SUPPORT_CARD_SELECT: enter.script_support_card_select,
        CULTIVATE_FOLLOW_SUPPORT_CARD_SELECT: enter.script_follow_support_card_select,
        CULTIVATE_FINAL_CHECK: enter.script_cultivate_final_check,

        # the run itself - fifty of a career's fifty-two minutes
        INDEPENDENT_TRAINING_WAIT: career.script_wait,
        INDEPENDENT_TRAINING_RESULTS: career.script_results,

        # collecting the result. Three crops of the same result screen share
        # one handler.
        CULTIVATE_RESULT: collect.script_cultivate_result,
        CULTIVATE_RESULT_1: collect.script_cultivate_result,
        CULTIVATE_RESULT_2: collect.script_cultivate_result,
        CULTIVATE_FINISH: collect.script_cultivate_finish,
        CULTIVATE_LEVEL_RESULT: collect.script_cultivate_level_result,
        HISTORICAL_RATING_UPDATE: collect.script_historical_rating_update,
        SCENARIO_RATING_UPDATE: collect.script_scenario_rating_update,
        RECEIVE_CUP: collect.script_receive_cup,

        # The end-of-career sparks screens. Reading them is unconditional;
        # rerolling only happens when the task enables it and names a target.
        FACTOR_RECEIVE: spark.script_factor_receive,
        FACTOR_REROLL: spark.script_factor_reroll,

        # Skill buying. These are two different screens, not two crops of one:
        # CONFIRMATION_LEARNSKILL_BUTTON is a crop of the **Learn** button on
        # the "Learn the above skills?" dialog, so it matches that dialog
        # alone. Pointing both at script_learn_skill made the bot click Cancel
        # on its own purchase - see skills.script_confirm_learn.
        CULTIVATE_LEARN_SKILL: skills.script_learn_skill,
        CONFIRMATION_LEARNSKILL_BUTTON: skills.script_confirm_learn,

        # The blind fallback, for a frame matching no screen at all. Several
        # screens on this path are advanced only by its corner click.
        NOT_FOUND_UI: script_not_found_ui,
    }
}


def exec_script(ctx):
    """Dispatch one frame to its handler."""
    # A team trials session claims every frame it runs through: the bot is on
    # the Race tab, where the career handlers' click points mean other things.
    # This sits here rather than in before_hook because the engine calls that
    # and then dispatches anyway - a hook cannot claim a frame.
    if team_trials.active(ctx) and team_trials.run_frame(ctx):
        return
    table = script_dicts.get(ctx.task.task_type)
    if table and ctx.current_ui in table:
        # A screen with a handler means the bot is somewhere it knows, so the
        # run of unrecognised frames is over - see script_not_found_ui, which
        # presses Home once that run gets long.
        career = getattr(ctx, 'career', None)
        if career is not None and ctx.current_ui is not NOT_FOUND_UI:
            career.unknown_frames = 0
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
# The skip presses were the open question, and they are SETTLED: they never
# fire on this path. Measured on 10 Sep 2026 by running one full career on the
# parent project with file logging raised to DEBUG, so every click was recorded
# by name. The career completed - 16:12 to 17:04, including the whole collect
# phase where those presses would have to happen - and `click >> Skip` appears
# zero times. Every click it did make is accounted for: 15 blind fallback
# clicks, 3 Next buttons, and named handler clicks.
#
# So all three are inert here and None is correct. Do not re-open this without
# new evidence; the experiment is cheap to repeat but it has been run.
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
