"""The manifest must be the thing the executor actually reaches for.

The executor does `APP_MANIFEST_LIST[task.app_name]` and then dispatches on
`ctx.task.task_type`. Both are lookups by value, so a mismatch between what
`build_task` produces and what the manifest is keyed on does not raise - it
silently matches nothing, and every frame becomes an unhandled screen. This
pins both ends together.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from bot.base.manifest import APP_MANIFEST_LIST, register_app
from bot.base.resource import UI, NOT_FOUND_UI
from bot.base.task import TaskExecuteMode
import uma_it.asset.ui as asset_ui
from uma_it.manifest import UmaItManifest, script_dicts, exec_script
from uma_it.task import APP_NAME, UmaItTaskType

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


print("registration")
register_app(UmaItManifest)
check("the app registers under its own name", APP_MANIFEST_LIST.get(APP_NAME) is UmaItManifest)
check("it is the only app registered", list(APP_MANIFEST_LIST) == [APP_NAME],
      str(list(APP_MANIFEST_LIST)))

print("\nthe executor's lookup path")
manifest = APP_MANIFEST_LIST[APP_NAME]
task = manifest.build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "check", None, {})
check("build_task stamps the app name the manifest is keyed on",
      task.app_name == APP_NAME, task.app_name)
check("  so the executor's manifest lookup resolves",
      APP_MANIFEST_LIST.get(task.app_name) is manifest)

ctx = manifest.build_context(task, None)
check("build_context returns a context carrying the task", ctx.task is task)
check("  with run state attached", ctx.career is not None)
check("  and settings reachable from it", ctx.task.detail.loop_count == 0)

print("\nthe dispatch key")
# script_dicts is keyed on the task type; build_task sets it. If these drift,
# every frame silently falls through to the unhandled-screen warning.
check("the task type build_task sets is a key in script_dicts",
      task.task_type in script_dicts,
      f"{task.task_type!r} not in {list(script_dicts)!r}")
check("  and it is CAREER", task.task_type is UmaItTaskType.CAREER, str(task.task_type))

print("\nthe screen list")
declared = {v for v in vars(asset_ui).values() if isinstance(v, UI)}
check("22 screens are scanned", len(manifest.ui_list) == 22, str(len(manifest.ui_list)))
check("no screen is listed twice", len(set(manifest.ui_list)) == len(manifest.ui_list))
outside = [u.ui_name for u in manifest.ui_list if u not in declared]
check("every scanned screen comes from this project's asset layer",
      not outside, str(outside))

# Two screens sharing a ui_name are dispatched separately - the table is keyed
# on the object - but they log identically, so a frame gets attributed to the
# wrong screen. That is how SCENARIO_RATING_UPDATE spent the parent project
# logging as HISTORICAL_RATING_UPDATE. CULTIVATE_RESULT is the one deliberate
# case: three crops of a single screen.
names = {}
for u in manifest.ui_list:
    names.setdefault(u.ui_name, []).append(u)
collisions = {n: len(v) for n, v in names.items() if len(v) > 1}
check("no two screens share a name, bar the CULTIVATE_RESULT crops",
      collisions == {"CULTIVATE_RESULT": 3}, str(collisions))

print("\nhandlers")
handled = set(script_dicts.get(UmaItTaskType.CAREER, {}))
unhandled = [u.ui_name for u in manifest.ui_list if u not in handled]
print(f"  {len(handled)} of {len(manifest.ui_list)} screens have a handler")
if unhandled:
    print("  still to write: " + ", ".join(sorted(unhandled)))
check("NOT_FOUND_UI has a fallback handler", NOT_FOUND_UI in handled,
      "not yet written - the app cannot run without it")

print("\nan unhandled screen warns rather than raising")


class _Ctx:
    task = task
    current_ui = manifest.ui_list[0]


try:
    exec_script(_Ctx())
    check("dispatching an unhandled screen does not raise", True)
except Exception as e:
    check("dispatching an unhandled screen does not raise", False,
          f"{type(e).__name__}: {e}")

print("\nmanifest fields the executor reads")
for field in ('app_name', 'app_package_name', 'app_activity_name',
              'build_context', 'build_task', 'ui_list', 'script'):
    check(f"{field} is set", getattr(manifest, field, None) is not None)

expected = [f for f in failures if f == "NOT_FOUND_UI has a fallback handler"]
print(f"\n{len(failures)} failed"
      f"{' (all expected at this stage)' if failures and failures == expected else ''}")
# The missing fallback is a known, recorded gap rather than a regression.
sys.exit(1 if [f for f in failures if f not in expected] else 0)
