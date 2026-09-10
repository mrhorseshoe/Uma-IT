"""What a user configures, and what survives a restart.

Nineteen settings, against the parent project's fifty. The ones that are gone
configure a career this app does not play: training weights, tactics, event
choice weights, motivation and rest thresholds, pal preferences, extra race
lists, Aoharu and Fujikiseki. In Independent Training the game plays the
career, so there is nothing for them to influence.

Two rules govern every field here, and both were paid for in the parent
project.

**Read with a default, always** - `data.get(key, default)`, never `data[key]`.
Tasks saved before a field existed are restored from disk without it, and a
KeyError here is not a visible error: the loader catches it, drops the task,
and the next save writes the shortened list back. That is how a task list
becomes empty, and it has happened.

**Anything needing continuity lives here, not on the run context.** The process
soft-restarts after every career, so `loops_done` is only correct because it is
a task field - serialized with the task and reloaded at boot. The run context
is rebuilt from nothing every time.
"""
from enum import Enum

from bot.base.task import Task, TaskExecuteMode, TaskStatus
import bot.base.log as logger

from uma_it.define import ScenarioType

log = logger.get_logger(__name__)

APP_NAME = "uma-it"


class TaskDetail:
    """The settings, as read off the task payload.

    Handlers read these through `ctx.task.detail`. They are deliberately not
    copied onto the run context: in the parent project every setting existed in
    both places, and adding one meant editing four files with the copy step the
    easy one to forget. Here a setting exists once.
    """
    # -- the career to start ------------------------------------------------
    scenario: ScenarioType
    follow_support_card_name: str
    follow_support_card_level: int
    use_last_parents: bool

    # -- the loop -----------------------------------------------------------
    loop_count: int          # 0 = run until stopped
    loops_done: int          # durable; see the module docstring
    # 0 never restores TP, so a career fails rather than being paid for.
    # Higher values authorise spending, carats included - which is real
    # currency, so the default stays 0.
    allow_recover_tp: int

    # -- skill buying, off by default ---------------------------------------
    skip_learn_skill: bool
    learn_skill_list: list[list[str]]
    learn_skill_blacklist: list[str]
    learn_skill_only_user_provided: bool
    learn_skill_threshold: int
    manual_purchase_at_end: bool

    # -- spark reroll, off by default ---------------------------------------
    # Targets map a spark name to its own minimum star count. Mode 'and'
    # requires a hit in both the blue and pink groups, 'or' in either.
    spark_reroll_enabled: bool
    spark_reroll_targets: dict[str, int]
    spark_reroll_mode: str
    spark_reroll_min_stars: int
    spark_reroll_use_carats: bool
    stop_at_spark_reroll: bool


class EndTaskReason(Enum):
    TP_NOT_ENOUGH = "Not enough TP to start a run"
    STOP_AT_SPARK_REROLL = "Stopped at the spark reroll screen"


class UmaItTaskType(Enum):
    UNKNOWN = 0
    CAREER = 1


class UmaItTask(Task):
    detail: TaskDetail

    def end_task(self, status, reason) -> None:
        """Count the finished run here, not in the scheduler.

        The process soft-restarts immediately after each execution, so the
        scheduler's polling loop may never observe the finished status.
        end_task runs before the task list is written, which is the only point
        where incrementing the counter and persisting it are guaranteed to
        happen in that order.
        """
        try:
            detail = getattr(self, 'detail', None)
            if detail is not None and status in (TaskStatus.TASK_STATUS_SUCCESS,
                                                 TaskStatus.TASK_STATUS_FAILED):
                detail.loops_done = (getattr(detail, 'loops_done', 0) or 0) + 1
                limit = getattr(detail, 'loop_count', 0) or 0
                log.info("Loop run %d/%s finished"
                         % (detail.loops_done, limit if limit else "unlimited"))
        except Exception:
            pass
        super().end_task(status, reason)

    def start_task(self) -> None:
        super().start_task()


def _int(value, default, low=None, high=None):
    """int(value) with a default, because payloads arrive from JSON and users."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        n = max(low, n)
    if high is not None:
        n = min(high, n)
    return n


def build_task(task_execute_mode: TaskExecuteMode, task_type: int,
               task_desc: str, cron_job_config: dict,
               attachment_data: dict) -> UmaItTask:
    """Build a task from a submitted or reloaded payload.

    Tolerates payloads written by the parent project: unknown keys are ignored
    and missing ones take their default, so a task exported from there loads
    here without translation.
    """
    data = attachment_data or {}
    td = TaskDetail()

    td.scenario = ScenarioType(_int(data.get('scenario'), 0, 0, 4))
    td.follow_support_card_name = str(data.get('follow_support_card_name') or '')
    td.follow_support_card_level = _int(data.get('follow_support_card_level'), 50, 0)
    td.use_last_parents = bool(data.get('use_last_parents', False))

    td.loop_count = _int(data.get('loop_count'), 0, 0)
    td.loops_done = _int(data.get('loops_done'), 0, 0)
    td.allow_recover_tp = _int(data.get('allow_recover_tp'), 0, 0)

    td.skip_learn_skill = bool(data.get('skip_learn_skill', True))
    td.learn_skill_list = [list(x) for x in (data.get('learn_skill_list') or [])
                           if isinstance(x, (list, tuple))]
    td.learn_skill_blacklist = list(data.get('learn_skill_blacklist') or [])
    td.learn_skill_only_user_provided = bool(
        data.get('learn_skill_only_user_provided', False))
    td.learn_skill_threshold = _int(data.get('learn_skill_threshold'), 888, 0)
    td.manual_purchase_at_end = bool(data.get('manual_purchase_at_end', False))

    td.spark_reroll_enabled = bool(data.get('spark_reroll_enabled', False))
    td.spark_reroll_min_stars = _int(data.get('spark_reroll_min_stars'), 3, 1, 3)
    targets = data.get('spark_reroll_targets', {})
    if isinstance(targets, dict):
        td.spark_reroll_targets = {
            str(k): _int(v, td.spark_reroll_min_stars, 1, 3)
            for k, v in targets.items()}
    elif isinstance(targets, (list, tuple)):
        # legacy payloads: a flat list sharing one global minimum
        td.spark_reroll_targets = {str(t): td.spark_reroll_min_stars for t in targets}
    else:
        td.spark_reroll_targets = {}
    td.spark_reroll_mode = 'and' if data.get('spark_reroll_mode') == 'and' else 'or'
    td.spark_reroll_use_carats = bool(data.get('spark_reroll_use_carats', False))
    td.stop_at_spark_reroll = bool(data.get('stop_at_spark_reroll', False))

    task = UmaItTask(app_name=APP_NAME,
                     task_execute_mode=task_execute_mode,
                     task_type=UmaItTaskType(_int(task_type, 1, 0, 1)),
                     task_desc=task_desc)
    task.cron_job_config = cron_job_config
    task.detail = td
    return task
