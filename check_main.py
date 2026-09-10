"""Startup order, and the one place getting it wrong is silent.

`load_saved_tasks` rebuilds each saved task by calling into the engine's
`add_task`, which does `APP_MANIFEST_LIST[app_name]`. If the app has not been
registered yet that raises KeyError - and the loader catches every exception
with `except Exception: continue`, drops the task, and the next save writes the
shortened list back to disk.

So registering the app after restoring tasks does not fail loudly. It empties
the task list, permanently, on the first run. This project's parent has already
lost a task definition to that exact shape of bug, by a different route.

This checks both halves: that the ordering requirement is real (tasks really
are dropped when the app is unknown), and that `main.py` actually does it in
that order.
"""
import ast, io, json, os, shutil, sys, tempfile
os.chdir(os.path.dirname(os.path.abspath(__file__)))
REPO = os.getcwd()
sys.path.insert(0, REPO)

# Import everything while the working directory is still the repo: config.yaml
# and the templates are resolved relative to it at import time.
from bot.base.manifest import APP_MANIFEST_LIST, register_app
from bot.base.purge import load_saved_tasks, save_scheduler_tasks
from bot.engine.scheduler import scheduler
from uma_it.manifest import UmaItManifest
from uma_it.task import APP_NAME

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


SAVED = [{
    "task_id": "checkmain0001",
    "app_name": APP_NAME,
    "task_execute_mode": 3,
    "task_type": 1,
    "task_desc": "Training",
    "attachment_data": {"scenario": 4, "loop_count": 0, "loops_done": 7,
                        "follow_support_card_name": "Wave of Gratitude"},
    "cron_job_config": None,
}]


def load_in_sandbox(register: bool):
    """Run a restore in a scratch userdata/, and report what survived."""
    APP_MANIFEST_LIST.clear()
    scheduler.task_list = []
    if register:
        register_app(UmaItManifest)
    tmp = tempfile.mkdtemp(prefix="umait-check-")
    try:
        os.makedirs(os.path.join(tmp, "userdata"))
        with io.open(os.path.join(tmp, "userdata", "saved_tasks.json"),
                     'w', encoding='utf-8') as f:
            json.dump(SAVED, f)
        os.chdir(tmp)
        load_saved_tasks()
        tasks = list(scheduler.get_task_list())
        # what a following persist would write back
        save_scheduler_tasks()
        with io.open(os.path.join(tmp, "userdata", "saved_tasks.json"),
                     encoding='utf-8') as f:
            on_disk = json.load(f)
        return tasks, on_disk
    finally:
        os.chdir(REPO)
        shutil.rmtree(tmp, ignore_errors=True)


print("restoring with the app registered")
tasks, on_disk = load_in_sandbox(register=True)
check("the saved task comes back", len(tasks) == 1, f"{len(tasks)} tasks")
if tasks:
    check("  with its settings intact", tasks[0].detail.loops_done == 7,
          str(tasks[0].detail.loops_done))
    check("  and its id", tasks[0].task_id == "checkmain0001", tasks[0].task_id)
check("  and a later save keeps it on disk", len(on_disk) == 1, f"{len(on_disk)} entries")

print("\nrestoring before the app is registered - the failure being guarded")
tasks, on_disk = load_in_sandbox(register=False)
check("the task is dropped, silently", len(tasks) == 0, f"{len(tasks)} tasks")
check("  and the next save writes the empty list back", on_disk == [], str(on_disk))

# Leave the process in the state the rest of a run expects.
APP_MANIFEST_LIST.clear()
register_app(UmaItManifest)
scheduler.task_list = []

print("\nthe order main.py actually uses")
tree = ast.parse(io.open('main.py', encoding='utf-8').read())
main_fn = next(n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'main')
# Sorted by source position, not by ast.walk order - walk is breadth-first, so
# a call nested inside an `if` comes back after one at the top level whatever
# the source says. Getting that wrong here would make these assertions pass or
# fail for reasons unrelated to the order they are meant to check.
calls = [n.func.id for n in sorted(
    (n for n in ast.walk(main_fn)
     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)),
    key=lambda n: (n.lineno, n.col_offset))]
check("main() registers the app", 'register_app' in calls, str(calls))
check("main() restores state", 'restore_state' in calls, str(calls))
if 'register_app' in calls and 'restore_state' in calls:
    check("  and registers before restoring",
          calls.index('register_app') < calls.index('restore_state'), str(calls))

check("the device is prepared before either",
      'prepare_device' in calls
      and calls.index('prepare_device') < calls.index('register_app'), str(calls))

print("\nwhat startup pulls in")
check("main.py imports without side effects on the parent project",
      not [m for m in sys.modules if m == 'module' or m.startswith('module.')],
      str([m for m in sys.modules if m.startswith('module')]))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
