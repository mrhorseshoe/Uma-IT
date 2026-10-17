"""When the device stops returning screenshots.

Three real failures drove this (see bot/engine/device_watch.py): the watchdog
restarting a game it could not see 329 times on 4 Oct, the bot freezing inside
a screenshot call for four hours on 12 Oct, and the ADB server losing the
device after an emulator restart on 16 Oct.

Checked here without a device: the ladder against a fake clock; the screenshot
time limit and the adb helpers against a fake client; and the real executor's
watchdog, end to end, against a fake controller and a fast clock - nothing in
the run is real except the code under test.
"""
import os, sys, time as _real_time, threading, types
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import bot.engine.device_watch as dw
import bot.conn.u2_ctrl as u2c

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


logged = []
for _lvl in ('info', 'warning', 'error'):
    setattr(dw.log, _lvl, (lambda lvl: lambda msg, *a, **k: logged.append((lvl, msg)))(_lvl))


class Dev:
    """The device-facing half of a controller, scripted."""
    def __init__(self, state="emulator-5554 is not listed"):
        self.state = state
        self.calls = []
        self.last_screen_error = "screenshot did not return within 15s"

    def device_state(self):
        return self.state

    def reconnect(self):
        self.calls.append('reconnect')

    def restart_adb_server(self):
        self.calls.append('adb restart')


# --- the ladder -----------------------------------------------------------
print("\nthe ladder, against a fake clock")
now = [1000.0]
dev = Dev()
lad = dw.NoFrameLadder(dev, clock=lambda: now[0])
check("a good frame with no spell does nothing", lad.tick(True) == '' and not logged)
lad.tick(False)
check("the first missing screenshot is logged with what adb says",
      logged and logged[-1][0] == 'warning' and 'not listed' in logged[-1][1]
      and 'did not return' in logged[-1][1], str(logged[-1:]))
check("  and nothing is tried yet", dev.calls == [], str(dev.calls))
results = []
for t in range(30, dw.GIVE_UP_AFTER + 31, 30):     # the watchdog ticks every 30s
    now[0] = 1000.0 + t
    results.append((t, lad.tick(False), list(dev.calls)))
first = {}
for t, r, calls in results:
    for c in calls:
        first.setdefault(c, t)
check(f"it reconnects after {dw.RECONNECT_AFTER}s", first.get('reconnect') == dw.RECONNECT_AFTER,
      str(first))
check(f"  restarts the ADB server after {dw.ADB_RESTART_AFTER}s",
      first.get('adb restart') == dw.ADB_RESTART_AFTER, str(first))
adb_times = [t for t, r, calls in results
             if calls.count('adb restart') > ([0] + [c.count('adb restart') for _, _, c in results])[results.index((t, r, calls))]]
check(f"  and again every {dw.ADB_RESTART_EVERY}s while the spell lasts",
      adb_times[:3] == [120, 420, 720], str(adb_times))
gave_up = [t for t, r, _ in results if r == 'give_up']
check(f"it gives up at {dw.GIVE_UP_AFTER}s, not before", gave_up and gave_up[0] == dw.GIVE_UP_AFTER,
      str(gave_up))
check("  saying what it tried and what adb says",
      any(l == 'error' and 'ADB server restart' in m and 'not listed' in m for l, m in logged))

logged.clear()
now[0] = 5000.0
dev = Dev()
lad = dw.NoFrameLadder(dev, clock=lambda: now[0])
for t in (0, 30, 60, 90):
    now[0] = 5000.0 + t
    lad.tick(False)
now[0] = 5120.0
check("screenshots coming back ends the spell", lad.tick(True) == '')
check("  and says how long it lasted and what was tried",
      any(l == 'info' and 'back after 120s' in m and 'reconnect' in m for l, m in logged),
      str(logged[-1:]))
now[0] = 5150.0
lad.tick(False)
now[0] = 5200.0
lad.tick(False)
check("a new spell starts its own clock - no instant reconnect or give-up",
      dev.calls == ['reconnect'], str(dev.calls))

dev = Dev()
dev.reconnect = lambda: (_ for _ in ()).throw(TimeoutError("reconnecting did not finish"))
lad = dw.NoFrameLadder(dev, clock=lambda: now[0])
now[0] = 9000.0; lad.tick(False)
now[0] = 9060.0
try:
    lad.tick(False)
    check("a failing step is logged, not raised", True)
except Exception as e:
    check("a failing step is logged, not raised", False, repr(e))


# --- the controller -------------------------------------------------------
print("\nthe screenshot time limit")
u2c.SCREENSHOT_TIMEOUT = 0.3
u2c.RECONNECT_TIMEOUT = 0.5
ctrl = u2c.U2AndroidController()
release = threading.Event()
frame = np.full((1280, 720, 3), 90, np.uint8)


class Client:
    def __init__(self, mode):
        self.mode = mode

    def screenshot(self, format=None):
        if self.mode == 'hang':
            release.wait(30)
            return None
        if self.mode == 'raise':
            raise ConnectionError("Connection refused")
        return frame


ctrl.u2client = Client('hang')
t0 = _real_time.time()
img = ctrl.get_screen()
took = _real_time.time() - t0
check("a screenshot that never returns comes back as None", img is None)
check("  after the time limit, not forever", took < 2, f"{took:.2f}s")
check("  and says why", 'did not return' in ctrl.last_screen_error, ctrl.last_screen_error)
ctrl.get_screen(); ctrl.get_screen()
t0 = _real_time.time()
ctrl.get_screen()
check("once three are hung it stops starting more", _real_time.time() - t0 < 0.1
      and 'never returned' in ctrl.last_screen_error, ctrl.last_screen_error)

ctrl.init_env = lambda: setattr(ctrl, 'u2client', Client('ok'))
ctrl.reconnect()
img = ctrl.get_screen()
check("a reconnect forgets the hung calls, and screenshots work again",
      img is not None and ctrl.last_screen_error == '', ctrl.last_screen_error)
release.set()

ctrl.u2client = Client('raise')
check("a screenshot that raises is None", ctrl.get_screen() is None)
check("  and the error is kept", 'ConnectionError' in ctrl.last_screen_error, ctrl.last_screen_error)

ctrl.init_env = lambda: _real_time.sleep(5)
t0 = _real_time.time()
try:
    ctrl.reconnect()
    check("a reconnect that hangs is given up on", False)
except TimeoutError:
    check("a reconnect that hangs is given up on", _real_time.time() - t0 < 2)

print("\nwhat adb says")
listing = "List of devices attached\nemulator-5554\toffline\n127.0.0.1:16384\tdevice\n\n"
ctrl._adb = lambda *a, **k: listing
check("the device's state is read off 'adb devices'",
      ctrl.device_state() == "emulator-5554 is 'offline'", ctrl.device_state())
listing = "List of devices attached\n127.0.0.1:16384\tdevice\n\n"
check("  and a missing device says what is listed instead",
      ctrl.device_state() == "emulator-5554 is not listed (listed: 127.0.0.1:16384)",
      ctrl.device_state())
import subprocess as _sp
ctrl._adb = lambda *a, **k: (_ for _ in ()).throw(_sp.TimeoutExpired('adb', 10))
check("  and an adb that does not answer says so",
      'did not answer' in ctrl.device_state(), ctrl.device_state())
ran = []
ctrl._adb = lambda *a, **k: ran.append(a) or ''
u2c.time.sleep = lambda s: None
ctrl.restart_adb_server()
u2c.time.sleep = _real_time.sleep
check("the ADB server restart kills and starts the server",
      ran == [('kill-server',), ('start-server',)], str(ran))


# --- the real watchdog, end to end ----------------------------------------
print("\nthe executor's watchdog, end to end")
import bot.engine.executor as ex
from bot.base.task import TaskStatus, EndTaskReason
from bot.base.manifest import APP_MANIFEST_LIST
from bot.engine.scheduler import scheduler

clock = [100000.0]
lock = threading.Lock()


def fsleep(s):
    with lock:
        clock[0] += s
    _real_time.sleep(min(s, 30) * 0.003)


fake_time = types.SimpleNamespace(sleep=fsleep, time=lambda: clock[0],
                                  strftime=_real_time.strftime, localtime=_real_time.localtime)
ex.time = fake_time
dw.time = fake_time
for name in ('save_task_data', 'save_scheduler_tasks', 'save_scheduler_state',
             'soft_process_restart', 'push_system_notification', 'purge_all'):
    setattr(ex, name, lambda *a, **k: None)


class FakeCtrl:
    def __init__(self, screens):
        self.screens = screens          # callable -> image or None
        self.calls = []
        self.last_screen_error = 'screenshot did not return within 15s'

    def init_env(self): pass
    def start_app(self, *a): self.calls.append('start_app')
    def click(self, *a, **k): pass
    def destroy(self): pass
    def get_screen(self, to_gray=False):
        img = self.screens(self)
        return None if img is None else (img[:, :, 0] if to_gray else img)
    def execute_adb_shell(self, cmd, sync):
        self.calls.append(cmd)
    def device_state(self): return 'emulator-5554 is not listed'
    def reconnect(self): self.calls.append('reconnect')
    def restart_adb_server(self): self.calls.append('adb restart')


class FakeTask:
    def __init__(self):
        self.app_name = 'fake'
        self.task_status = TaskStatus.TASK_STATUS_PENDING
        self.ended = []

    def start_task(self): pass

    def end_task(self, status, reason):
        self.ended.append((status, reason))
        self.task_status = status


def run(screens, finish_after=None, limit=60):
    """One run of the real work flow. Returns the task and the controller."""
    ctrl = FakeCtrl(screens)
    ex.get_controller = lambda: ctrl
    state = {'frames': 0}

    def build_context(task, c):
        def finish():
            state['frames'] += 1
            return finish_after is not None and clock[0] >= finish_after
        return types.SimpleNamespace(is_task_finish=finish, current_ui=None)

    APP_MANIFEST_LIST['fake'] = types.SimpleNamespace(
        ui_list=[], before_hook=None, after_hook=None, app_package_name='p',
        app_activity_name='a', build_context=build_context, script=lambda ctx: None)
    ex.Executor.detect_ui = lambda self, ui_list, target: ex.NOT_FOUND_UI
    task = FakeTask()
    e = ex.Executor()
    e.active = True
    t = threading.Thread(target=e.run_work_flow, args=(task,), daemon=True)
    t.start()
    t.join(limit)
    check("  (the run finished)", not t.is_alive())
    e.active = False
    return task, ctrl


# A: the device is gone for good.
clock[0] = 100000.0
scheduler.active = True
task, ctrl = run(lambda c: None)
check("a device that never answers ends the run as DEVICE_LOST",
      task.ended[:1] == [(TaskStatus.TASK_STATUS_FAILED, EndTaskReason.DEVICE_LOST)], str(task.ended))
check("  and stops the loop", scheduler.active is False)
force_stops = [c for c in ctrl.calls if 'force-stop' in str(c)]
check("  without once restarting a game it cannot see", force_stops == [], str(force_stops))
check("  having reconnected and restarted the ADB server first",
      'reconnect' in ctrl.calls and 'adb restart' in ctrl.calls, str(ctrl.calls))

# B: the device comes back after the reconnect.
clock[0] = 200000.0
scheduler.active = True
seq = [0]


def comes_back(c):
    if 'reconnect' not in c.calls:
        return None
    seq[0] += 1
    return np.full((1280, 720, 3), (seq[0] * 37) % 255, np.uint8)


task, ctrl = run(comes_back, finish_after=200000.0 + 400)
check("a device that comes back after the reconnect finishes its run normally",
      task.ended[:1] == [(TaskStatus.TASK_STATUS_SUCCESS, EndTaskReason.COMPLETE)], str(task.ended))
check("  with the loop still running", scheduler.active is True)
check("  and no ADB restart, no game restart",
      'adb restart' not in ctrl.calls and not [c for c in ctrl.calls if 'force-stop' in str(c)],
      str(ctrl.calls))

# C: a frozen frame - screenshots arrive, identical - still restarts the game.
clock[0] = 300000.0
still = np.full((1280, 720, 3), 120, np.uint8)
task, ctrl = run(lambda c: still, finish_after=300000.0 + 200)
check("a frozen screen still restarts the game, as before",
      any('force-stop' in str(c) for c in ctrl.calls), str(ctrl.calls))
check("  and never touches the device ladder",
      'reconnect' not in ctrl.calls and 'adb restart' not in ctrl.calls, str(ctrl.calls))
scheduler.active = False

print()
print("all passed" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
