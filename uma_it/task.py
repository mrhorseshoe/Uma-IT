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

# Failed careers in a row before the loop stops itself. Three, because a single
# failure is usually a recoverable screen mishap and the run after it succeeds,
# while a real cause - no TP, a game update, a changed screen - fails every
# time and would otherwise retry until someone noticed.
MAX_CONSECUTIVE_FAILURES = 3


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
    use_last_parents: bool
    # No `follow_support_card_level`. It gated the borrow on a level OCR'd off
    # the card row, and that read gave 150 for a card that caps at 50 - so it
    # passed everything, and would have passed a low card misread the same way.
    # The name match selects the card; see find_support_card.

    # -- the loop -----------------------------------------------------------
    loop_count: int          # 0 = run until stopped
    loops_done: int          # durable; see the module docstring
    # Runs that ended FAILED, since the last one that did not. Durable for the
    # same reason `loops_done` is, and it exists because the two counters mean
    # different things: a career that never started is not a career the user
    # asked for. See `UmaItTask.end_task`.
    consecutive_failures: int
    # 0 never restores TP, so a career fails rather than being paid for.
    # Higher values authorise spending, carats included - which is real
    # currency, so the default stays 0.
    allow_recover_tp: int

    # -- skill buying, off by default ---------------------------------------
    skip_learn_skill: bool
    learn_skill_list: list[list[str]]
    learn_skill_blacklist: list[str]
    learn_skill_only_user_provided: bool
    # No `learn_skill_threshold`. In the parent it gates mid-career buying on
    # the per-turn skill point total, and there are no turns here: skills are
    # only ever bought at the end of a run.
    # No `manual_purchase_at_end`. It exists in the parent to pause the bot
    # while the user buys skills by hand, through a flow that blocks the bot
    # thread polling the web server, with a bare input() as its fallback.
    # Neither the flow nor the flag is ported.

    # -- spark reroll, off by default ---------------------------------------
    # Targets map a spark name to its own minimum star count. Mode 'and'
    # requires a hit in both the blue and pink groups, 'or' in either.
    spark_reroll_enabled: bool
    spark_reroll_targets: dict[str, int]
    spark_reroll_mode: str
    spark_reroll_min_stars: int
    stop_at_spark_reroll: bool
    # White sparks - skills, races, scenarios - as requirement rows. Every row
    # must be satisfied, and any one entry satisfies its row:
    #
    #   [[{'name': 'URA Finale', 'stars': 2}],
    #    [{'name': 'Corner Recovery', 'stars': 2},
    #     {'name': 'Swinging Maestro', 'stars': 1}]]
    #
    # reads "URA Finale, and either Corner Recovery or Swinging Maestro".
    #
    # Rows rather than a chain of AND/OR operators because the structure *is*
    # the precedence - there is nothing to disambiguate, and both degenerate
    # cases fall out: one entry per row is a pure AND, one row holding
    # everything is a pure OR. Measured on 140 captured rolls, a specific pair
    # of skills co-occurs in about 2-4% of them while "any of five" lands near
    # 56%, so the arrangement people need most often is the cheap one here.
    spark_skill_targets: list
    # Runs whose kept sparks met every requirement, since the loop was last
    # started fresh (Run again clears it with loops_done). Durable for the same
    # reason loops_done is; counted at the spark decision, in `uma_it/spark.py`,
    # because that is where the result is known.
    spark_goal_runs: int
    # No `spark_reroll_use_carats`. In the parent that flag authorises a
    # 66-line flow that drives the in-game shop to buy TP with carats, and it
    # is not ported: carats are real currency, `allow_recover_tp` already
    # defaults to refusing to spend, and a flag whose behaviour does not exist
    # is worse than no flag. Declining the reroll keeps the original sparks,
    # which costs nothing - the career is already over by then.


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

        **Only a career that completed counts.** A FAILED run used to increment
        `loops_done` as well, which made "2 of 2 runs" true of two careers that
        never started: on 11 Sep a two-run loop reported itself finished in
        thirty seconds, both runs having died on the TP prompt before the
        career began. A user asking for two careers is asking for two careers.

        The counter was doing a second job, though - it was also the only thing
        stopping a loop that fails instantly from retrying forever, which is
        what an out-of-TP account would do. So failures are still counted,
        separately: `MAX_CONSECUTIVE_FAILURES` in a row stops the scheduler,
        and the flag is persisted by the same end-of-run save that writes this
        counter, so the soft restart does not resume it.
        """
        try:
            detail = getattr(self, 'detail', None)
            if detail is not None and status == TaskStatus.TASK_STATUS_SUCCESS:
                detail.consecutive_failures = 0
                detail.loops_done = (getattr(detail, 'loops_done', 0) or 0) + 1
                limit = getattr(detail, 'loop_count', 0) or 0
                log.info("Loop run %d/%s finished"
                         % (detail.loops_done, limit if limit else "unlimited"))
            elif detail is not None and status == TaskStatus.TASK_STATUS_FAILED:
                failures = (getattr(detail, 'consecutive_failures', 0) or 0) + 1
                detail.consecutive_failures = failures
                done = getattr(detail, 'loops_done', 0) or 0
                limit = getattr(detail, 'loop_count', 0) or 0
                log.warning("Career failed (%s) - run %d/%s not counted, "
                            "%d consecutive failure(s)"
                            % (getattr(reason, 'value', reason), done + 1,
                               limit if limit else "unlimited", failures))
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    log.error("%d careers failed in a row without one completing "
                              "- stopping the loop rather than retrying. Fix the "
                              "cause, then start it again from the dashboard."
                              % failures)
                    from bot.engine.scheduler import scheduler
                    scheduler.stop()
        except Exception:
            pass
        super().end_task(status, reason)

    def start_task(self) -> None:
        super().start_task()


def _skill_requirement_rows(value):
    """Coerce the white-spark requirement rows into their one valid shape.

    Read defensively because this arrives from a dashboard payload and from
    tasks saved before the field existed. Anything unrecognisable becomes an
    empty list, which means "no white requirement" - the safe reading, since a
    malformed rule that silently matched everything would keep bad rolls.
    """
    rows = []
    if not isinstance(value, list):
        return rows
    for row in value:
        # A bare string or dict is a row of one; people and older payloads
        # both write it that way.
        if isinstance(row, (str, dict)):
            row = [row]
        if not isinstance(row, list):
            continue
        entries = []
        for entry in row:
            if isinstance(entry, str):
                entry = {'name': entry}
            if not isinstance(entry, dict):
                continue
            name = str(entry.get('name') or '').strip()
            if not name:
                continue
            entries.append({'name': name,
                            'stars': _int(entry.get('stars'), 1, 1, 3)})
        if entries:
            rows.append(entries)
    return rows


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
    td.use_last_parents = bool(data.get('use_last_parents', False))

    td.loop_count = _int(data.get('loop_count'), 0, 0)
    td.loops_done = _int(data.get('loops_done'), 0, 0)
    td.consecutive_failures = _int(data.get('consecutive_failures'), 0, 0)
    td.allow_recover_tp = _int(data.get('allow_recover_tp'), 0, 0)

    td.skip_learn_skill = bool(data.get('skip_learn_skill', True))
    td.learn_skill_list = [list(x) for x in (data.get('learn_skill_list') or [])
                           if isinstance(x, (list, tuple))]
    td.learn_skill_blacklist = list(data.get('learn_skill_blacklist') or [])
    td.learn_skill_only_user_provided = bool(
        data.get('learn_skill_only_user_provided', False))

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
    td.stop_at_spark_reroll = bool(data.get('stop_at_spark_reroll', False))
    td.spark_skill_targets = _skill_requirement_rows(data.get('spark_skill_targets'))
    td.spark_goal_runs = _int(data.get('spark_goal_runs'), 0, 0)

    task = UmaItTask(app_name=APP_NAME,
                     task_execute_mode=task_execute_mode,
                     task_type=UmaItTaskType(_int(task_type, 1, 0, 1)),
                     task_desc=task_desc)
    task.cron_job_config = cron_job_config
    task.detail = td
    return task
