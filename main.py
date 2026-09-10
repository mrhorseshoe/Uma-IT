"""Start the bot: pick a device, check it, restore state, then serve.

Deliberately short. The parent project's equivalent is 607 lines; about 360 of
those are device handling, which lives in `device.py` here, and about 100 are a
time-window feature that never ran (see below). What is left is the order in
which things have to happen, which is the part worth being able to read in one
go.

That order matters in two places:

* **The device must be healthy before the scheduler starts.** A scheduler
  thread that starts against an offline device begins failing careers
  immediately.
* **Tasks must be restored before the scheduler is told to start.** The saved
  scheduler flag says whether the loop was running when the process last
  stopped, and the process soft-restarts after every career - so this path is
  taken far more often than a cold boot.

**Not carried over: the time-window enforcer.** The parent runs a thread that
wakes every 60 seconds to decide whether the bot is allowed to run at this hour.
Its window is `start_time = 0` to `end_time = 24`, both module-level constants
that nothing reads from config, the UI, or anywhere else - and its
`KEEPALIVE_ACTIVE` flag is written but never read. So the check is always
`0 <= hour < 24`, and the thread has never once paused anything. If a run
window is wanted here, it should be a task setting with a UI behind it rather
than a constant nobody can reach.
"""
import os
import sys
import threading
import time

# Checked before the first third-party import, not inside main(). The packages
# live in system Python 3.10's site-packages, so running this on any other
# interpreter fails at `import cv2` with a bare ModuleNotFoundError that says
# nothing about the actual cause. `python` on this machine is 3.14.
if sys.version_info[:2] != (3, 10):
    sys.exit(
        f"\033[31mUma-IT needs Python 3.10; this is "
        f"{sys.version.split()[0]}.\033[0m\n"
        f"Its packages are installed in system Python 3.10, so run:\n\n"
        f"    py -3.10 main.py\n")

import cv2

# Give OpenCV and the BLAS backends every core before anything imports them.
try:
    cores = str(os.cpu_count() or 1)
    os.environ.setdefault("MKL_NUM_THREADS", cores)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", cores)
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", cores)
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    cv2.setUseOptimized(True)
    cv2.setNumThreads(int(cores))
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

import bot.base.gpu_utils as gpu_utils
import bot.base.log as logger
from bot.base.manifest import register_app
from bot.engine.scheduler import scheduler

import device
from uma_it.manifest import UmaItManifest

log = logger.get_logger(__name__)

HOST = "127.0.0.1"
PORT = 8071
URL = f"http://{HOST}:{PORT}"

# Set by the restart wrapper. When it is on, the device is taken from config
# instead of being chosen, and no browser window is opened - the process
# soft-restarts after every career, and a browser tab per career is not wanted.
AUTORESTART = os.environ.get("UAT_AUTORESTART", "0") == "1"


def configure_gpu():
    if gpu_utils.detect_gpu_capabilities():
        opencv = gpu_utils.configure_opencv_gpu()
        log.info(f"GPU acceleration enabled: PaddleOCR=Yes, "
                 f"OpenCV={'Yes' if opencv else 'No'}")


def choose_device():
    """The configured device on a restart, otherwise ask."""
    if AUTORESTART:
        try:
            import yaml
            with open("config.yaml", 'r', encoding='utf-8') as f:
                name = yaml.safe_load(f)['bot']['auto']['adb']['device_name']
            if name:
                return name
        except Exception:
            pass
    return device.select_device()


def prepare_device(device_id: str) -> bool:
    """Health checks, with one recovery attempt, then a stabilisation pass."""
    if not device.run_health_checks():
        print("⚠️  Health checks failed. Attempting auto-recovery...")
        device._soft_recover_device(device_id)
        print("🔄 Retrying health checks...")
        if not device.run_health_checks():
            print("❌ Health checks failed again after recovery.")
            return False
    print("🔧 Finalizing device services…")
    device._finalize_services_light(device_id)
    return bool(device.update_config(device_id))


def restore_state() -> None:
    """Bring back the task list and whether the loop was running.

    Both come from `userdata/`, and both matter more than they look. The task
    list is the durable store - this project's parent lost a task definition
    once because it was not. The scheduler flag is why a soft restart resumes
    the loop instead of quietly stopping it after one career.
    """
    restored, was_active = False, None
    try:
        from bot.base.purge import load_saved_tasks, load_scheduler_state
        restored = load_saved_tasks()
        was_active = load_scheduler_state()
    except Exception as e:
        log.warning(f"Could not restore saved state: {e}")

    threading.Thread(target=scheduler.init, daemon=True).start()
    if was_active is True or (was_active is None and restored):
        try:
            scheduler.start()
            log.info("Scheduler resumed - the loop was running when the process stopped")
        except Exception as e:
            log.warning(f"Could not resume the scheduler: {e}")
    else:
        log.info("Scheduler idle - start it from the dashboard or POST /action/bot/start")


def main() -> int:
    try:
        from bot.base.purge import acquire_instance_lock
        acquire_instance_lock()
    except Exception:
        pass

    configure_gpu()

    device_id = choose_device()
    if device_id is None:
        print("❌ No device selected.")
        return 1
    if not prepare_device(device_id):
        return 1

    register_app(UmaItManifest)
    restore_state()

    print(f"🚀 Uma-IT running on {URL}")
    if not AUTORESTART:
        threading.Thread(
            target=lambda: (time.sleep(1), __import__('webbrowser').open(URL)),
            daemon=True).start()

    from uvicorn import run
    run("bot.server.handler:server", host=HOST, port=PORT, log_level="error")
    return 0


if __name__ == '__main__':
    sys.exit(main())
