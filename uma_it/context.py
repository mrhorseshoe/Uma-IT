"""State for one career, and nothing else.

The split from `task.py` is deliberate and is the one structural change this
project makes to how the parent works:

- **`task.detail` holds settings.** It is serialized, reloaded at boot, and
  survives the soft restart that happens after every career.
- **`ctx.career` holds run state.** It is built fresh for each career and is
  *expected* to be lost. Nothing here may be the only copy of something that
  has to outlive the run.

The parent project copied every setting from the task onto its run context, so
each one existed twice and adding a setting meant editing four files. Nothing
is copied here. Handlers read settings from `ctx.task.detail` and run state
from `ctx.career`.

The attribute is `ctx.career`, where the parent calls it `ctx.cultivate_detail`.
Code moved across will raise AttributeError rather than read a stale value,
which is the failure worth having.
"""
from bot.base.context import BotContext
import bot.base.log as logger

from uma_it.task import UmaItTask, UmaItTaskType

log = logger.get_logger(__name__)


class CareerContext:
    """Everything the handlers need to remember within a single career."""

    def __init__(self):
        # -- overall ---------------------------------------------------------
        self.career_finished: bool = False
        # Accumulated result screens, for the run summary.
        self.career_result: dict = {}

        # -- the race agenda picker -----------------------------------------
        # One state machine across three screens (Agenda / My Agendas /
        # Overwrite). `agenda_steps` is a hard stop: the picker gives up and
        # starts on whatever schedule the game already has rather than clicking
        # forever.
        self.agenda_phase: str = ''
        self.agenda_steps: int = 0
        self.agenda_waits: int = 0

        # -- starting a career ----------------------------------------------
        # Retry counters for the three one-way doors. Confirming the wrong
        # option on the career-mode dialog starts an event career that cannot
        # be backed out of, so each of these gives up rather than guessing.
        self.final_confirmation_tab_tries: int = 0
        self.career_mode_switch_tries: int = 0
        self.pending_run_tries: int = 0

        # -- the dialog router ----------------------------------------------
        # `dialog_repeat` counts consecutive frames resolving to the same
        # title. A dialog that will not clear is worth a warning well before
        # the engine's repetitive-click guard restarts the game at 11.
        self.dialog_last_title: str = ''
        self.dialog_repeat: int = 0
        self.dialog_header_box = None
        self.dialog_header_pos = ((0, 0), (0, 0))

        # -- the countdown ---------------------------------------------------
        # The run sits here for about fifty minutes. Only the remaining time
        # changing is worth a log line.
        self.last_countdown_log: str = ''

        # -- skill buying, only when the task enables it ---------------------
        # A per-run copy of the task's priority list. The buying pass removes
        # skills from it as they are learned, and the task's own list must not
        # be what gets edited: it is serialized to disk, so mutating it would
        # delete them from the user's saved preset permanently. None until the
        # first pass copies it.
        self.remaining_skills = None
        self.learn_skill_done: bool = False
        self.learn_skill_selected: bool = False
        self.final_skill_sweep_active: bool = False
        self.manual_purchase_completed: bool = False
        self.manual_purchase_initiated: bool = False

        # -- spark reroll, only when the task enables it ---------------------
        # Phase: '' not evaluated yet -> 'keep' the first roll satisfied the
        # targets -> 'reroll_clicked' waiting for the comparison screen ->
        # 'done' a set was chosen, or automation gave up.
        self.parse_factor_done: bool = False
        self.spark_reroll_phase: str = ''
        self.spark_reroll_clicks: int = 0
        self.spark_reroll_result: dict = {}
        self.spark_reroll_abort_tries: int = 0
        self.spark_reroll_recover_tries: int = 0

    def skills_wanted(self, task_detail):
        """The priority list this run is still trying to buy.

        Copied from the task on first use so the saved preset is never edited.
        """
        if self.remaining_skills is None:
            self.remaining_skills = [list(x) for x in
                                     (getattr(task_detail, 'learn_skill_list', None) or [])]
        return self.remaining_skills

    def reset_skill_learn(self):
        """Forget skill-buying progress, for a screen that can be re-entered."""
        self.learn_skill_done = False
        self.learn_skill_selected = False
        self.manual_purchase_completed = False
        self.manual_purchase_initiated = False


class UmaItContext(BotContext):
    task: UmaItTask
    career: CareerContext

    def __init__(self, task, ctrl):
        super().__init__(task, ctrl)
        self.career = CareerContext()

    def is_task_finish(self) -> bool:
        """Always False - the scheduler owns the loop.

        `bot/engine/scheduler.py` compares `detail.loops_done` against
        `detail.loop_count` and stops the task itself. Returning True here
        would end the run mid-career.
        """
        return False


def build_context(task: UmaItTask, ctrl) -> UmaItContext:
    ctx = UmaItContext(task, ctrl)
    if task.task_type != UmaItTaskType.CAREER:
        log.warning("uma-it: unexpected task type %s", task.task_type)
    return ctx
