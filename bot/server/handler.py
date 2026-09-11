import os
import time
import json
import re
from typing import Dict, Any
import subprocess

from fastapi import FastAPI, Path
from fastapi.middleware.cors import CORSMiddleware

from bot.base.log import task_log_handler
from bot.engine import ctrl as bot_ctrl
from bot.server.protocol.task import *
from starlette.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional


class SafeJSONResponse(JSONResponse):
    _surrogate_re = re.compile(r"[\ud800-\udfff]")

    @classmethod
    def _sanitize(cls, obj):
        if isinstance(obj, str):
            return cls._surrogate_re.sub("\ufffd", obj)
        if isinstance(obj, list):
            return [cls._sanitize(x) for x in obj]
        if isinstance(obj, dict):
            return {k: cls._sanitize(v) for k, v in obj.items()}
        return obj

    def render(self, content) -> bytes:
        safe_content = self._sanitize(content)
        return json.dumps(
            safe_content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


server = FastAPI(default_response_class=SafeJSONResponse)

server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for manual skill notifications
manual_skill_notification_state = {
    "show": False,
    "message": "",
    "timestamp": 0,
    "confirmed": False,
    "cancelled": False
}

_sys_metric_cache = {
    "has_data": False,
    "metric_data": "",
    "timestamp": 0,
    "metric_type": ""
}

@server.post("/api/manual-skill-notification")
def manual_skill_notification(notification_data: Dict[str, Any]):
    """Receive manual skill purchase notification from bot"""
    global manual_skill_notification_state
    manual_skill_notification_state.update({
        "show": True,
        "message": notification_data.get("message", ""),
        "timestamp": notification_data.get("timestamp", time.time()),
        "confirmed": False,
        "cancelled": False
    })
    return {"status": "success"}

@server.get("/api/manual-skill-notification-status")
def get_manual_skill_notification_status():
    """Get current notification status for frontend polling"""
    global manual_skill_notification_state
    return manual_skill_notification_state

@server.post("/api/manual-skill-notification-confirm")
def confirm_manual_skill_notification():
    """Confirm manual skill purchase completion"""
    global manual_skill_notification_state
    manual_skill_notification_state.update({
        "show": False,
        "confirmed": True,
        "cancelled": False
    })
    return {"status": "confirmed"}

@server.post("/api/manual-skill-notification-cancel")
def cancel_manual_skill_notification():
    global manual_skill_notification_state
    manual_skill_notification_state.update({
        "show": False,
        "confirmed": False,
        "cancelled": True
    })
    return {"status": "cancelled"}

@server.post("/api/sys-health-check")
def sys_health_check(metric_data: Dict[str, Any]):
    global _sys_metric_cache
    _sys_metric_cache.update({
        "has_data": True,
        "metric_data": metric_data.get("metric_data", ""),
        "timestamp": metric_data.get("timestamp", 0),
        "metric_type": metric_data.get("metric_type", "")
    })
    return {"status": "success"}

@server.get("/api/sys-metrics")
def get_sys_metrics():
    global _sys_metric_cache
    return _sys_metric_cache


# The skill list is the app's, not the engine's: the user's copy in userdata/
# shadows the one shipped in resource/, and writes always go to userdata so a
# hand-added or synced skill never dirties a tracked file. See
# uma_it/skills_db.py. Resolved per call because a sync can create the user's
# copy while the server is running.
def _skills_read_path():
    from uma_it.skills_db import active_path
    return active_path()


def _skills_write_path():
    from uma_it.skills_db import USER_PATH
    return USER_PATH


class AddSkillRequest(BaseModel):
    name: str
    skill_type: str
    rarity: str = "Normal"
    description: str = ""
    tier: str = "A"
    strategy: str = ""
    distance: str = ""


@server.get("/api/skills")
def get_skills():
    with open(_skills_read_path(), 'r', encoding='utf-8') as f:
        return json.load(f)


@server.post("/api/skills")
def add_skill(req: AddSkillRequest):
    name = req.name.strip()
    if not name:
        return {"ret": 1, "msg": "Skill name is required"}
    with open(_skills_read_path(), 'r', encoding='utf-8') as f:
        skills = json.load(f)
    if any(s.get('name', '').lower() == name.lower() for s in skills):
        return {"ret": 1, "msg": f"Skill '{name}' already exists"}
    tier = req.tier.strip() or "A"
    entry = {
        "skill_id": tier + "_" + name.replace(" ", "-"),
        "name": name,
        "tier": tier,
        "skill_type": req.skill_type.strip() or "Others",
        "prerequisite_of": [],
        "prerequisites": [],
        "description": req.description.strip(),
        "purchase_option": "Direct",
        "rarity": req.rarity.strip() or "Normal",
    }
    # optional filter fields; existing entries omit them when not applicable
    if req.strategy.strip():
        entry["strategy"] = req.strategy.strip()
    if req.distance.strip():
        entry["distance"] = req.distance.strip()
    skills.append(entry)
    os.makedirs(os.path.dirname(_skills_write_path()), exist_ok=True)
    with open(_skills_write_path(), 'w', encoding='utf-8') as f:
        json.dump(skills, f, ensure_ascii=False, indent=1)
    # drop the bot's in-memory copy so OCR canonicalization sees the new
    # skill without a restart
    try:
        import module.umamusume.script.cultivate_task.parse as cultivate_parse
        cultivate_parse.skills_database_cache = None
    except Exception:
        pass
    return {"ret": 0, "msg": "Skill added"}


EVENTS_JSON_PATH = os.path.join('resource', 'umamusume', 'data', 'event_data.json')


class AddEventRequest(BaseModel):
    name: str
    option_count: int


def _event_option_count(value):
    # same logic the web build used: count choices, fall back to stats
    count = 0
    if isinstance(value, dict):
        choices = value.get('choices')
        if isinstance(choices, (list, dict)):
            count = len(choices)
        if not count and isinstance(value.get('stats'), dict):
            count = len(value['stats'])
    return count


@server.get("/api/events")
def get_events():
    with open(EVENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        events = json.load(f)
    return {
        "names": sorted(events.keys()),
        "counts": {name: _event_option_count(value) for name, value in events.items()},
    }


@server.post("/api/events")
def add_event(req: AddEventRequest):
    name = req.name.strip()
    if not name:
        return {"ret": 1, "msg": "Event name is required"}
    count = max(1, min(int(req.option_count), 5))
    with open(EVENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        events = json.load(f)
    if any(k.lower() == name.lower() for k in events):
        return {"ret": 1, "msg": f"Event '{name}' already exists"}
    # no stats: without a user override the bot falls back to choice 1,
    # so these entries exist mainly to be overridden in Event Settings
    events[name] = {
        "choices": {str(i): "Choice " + str(i) for i in range(1, count + 1)},
        "stats": {},
    }
    with open(EVENTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=1)
    # drop the bot's in-memory events database so the new entry is seen
    # without a restart
    try:
        import module.umamusume.script.cultivate_task.event.manifest as event_manifest
        event_manifest._events_database = None
    except Exception:
        pass
    return {"ret": 0, "msg": "Event added"}


@server.post("/task")
def add_task(req: AddTaskRequest):
    bot_ctrl.add_task(req.app_name, req.task_execute_mode, req.task_type, req.task_desc,
                      req.cron_job_config, req.attachment_data)


@server.delete("/task")
def delete_task(req: DeleteTaskRequest):
    bot_ctrl.delete_task(req.task_id)


@server.get("/task")
def get_task():
    return bot_ctrl.get_task_list()


class RuntimeThresholds(BaseModel):
    repetitive_threshold: Optional[int] = None
    watchdog_threshold: Optional[int] = None


@server.get("/api/runtime-state")
def get_runtime_state():
    try:
        from bot.base.runtime_state import get_state
        return get_state()
    except Exception:
        return {
            "repetitive_count": 0,
            "repetitive_other_clicks": 0,
            "repetitive_threshold": 11,
            "watchdog_unchanged": 0,
            "watchdog_threshold": 3,
        }


@server.post("/api/runtime-thresholds")
def set_runtime_thresholds(req: RuntimeThresholds):
    try:
        from bot.base.runtime_state import set_thresholds, save_persisted
        set_thresholds(req.repetitive_threshold, req.watchdog_threshold)
        save_persisted()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@server.get("/api/update-status")
def get_update_status():
    try:
        with open("debug_update_handler.log", "a", encoding="utf-8") as log_file:
            def dlog(msg):
                log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
                log_file.flush()

            dlog("--- Checking update status ---")
            repo_root = None
            base = os.path.abspath(os.path.dirname(__file__))
            for _ in range(8):
                if os.path.isdir(os.path.join(base, '.git')):
                    repo_root = base
                    break
                parent = os.path.dirname(base)
                if parent == base:
                    break
                base = parent
            
            if repo_root is None:
                tl = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=os.getcwd(), timeout=5)
                if tl.returncode == 0 and os.path.isdir(tl.stdout.strip()):
                    repo_root = tl.stdout.strip()
                else:
                    dlog("Git repo not found")
                    return {"has_update": False, "error": "git repo not found from server path"}
            
            dlog(f"Repo root: {repo_root}")
            
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=repo_root, timeout=5)
            if branch.returncode != 0:
                dlog(f"Branch check failed: {branch.stderr.strip()}")
                return {"has_update": False, "error": branch.stderr.strip()}
            branch_name = branch.stdout.strip()
            dlog(f"Branch: {branch_name}")

            upstream = subprocess.run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], capture_output=True, text=True, cwd=repo_root, timeout=5)
            if upstream.returncode == 0:
                upstream_ref = upstream.stdout.strip()
                dlog(f"Upstream: {upstream_ref}")
                remote_name = upstream_ref.split('/')[0]
                # Ensure we're checking against the correct repo URL
                remote_url = subprocess.run(["git", "remote", "get-url", remote_name], capture_output=True, text=True, cwd=repo_root, timeout=5)
                dlog(f"Remote URL: {remote_url.stdout.strip()}")
                
                subprocess.run(["git", "fetch", "--quiet", remote_name], capture_output=True, text=True, cwd=repo_root, timeout=10)
                revspec = f"HEAD...{upstream_ref}"
            else:
                dlog("Upstream NOT found or implicit")
                # Compare against a configured remote, and do not touch any
                # remote's URL.
                #
                # This branch used to run
                #   git remote set-url origin <the upstream project>
                # whenever the checked-out branch had no tracking ref - which
                # is the normal state of any branch that has not been pushed
                # yet. Merely opening the dashboard was therefore enough to
                # repoint origin away from whatever fork the user actually
                # pushes to, silently and permanently. A read-only status check
                # has no business rewriting the repository's remotes, and the
                # damage outlasts it: pushes fail with a 403 against someone
                # else's repo, and `git pull` in start.bat would merge that
                # project's history over the user's own work.
                remotes = subprocess.run(["git", "remote"], capture_output=True, text=True,
                                         cwd=repo_root, timeout=5).stdout.split()
                if "origin" in remotes:
                    remote_name = "origin"
                elif remotes:
                    remote_name = remotes[0]
                else:
                    dlog("No git remote configured")
                    return {"has_update": False, "error": "no git remote configured",
                            "branch": branch_name}
                dlog(f"No tracking ref; comparing against {remote_name}/{branch_name}")
                subprocess.run(["git", "fetch", "--quiet", remote_name], capture_output=True, text=True, cwd=repo_root, timeout=10)
                revspec = f"HEAD...{remote_name}/{branch_name}"
            
            dlog(f"Revspec: {revspec}")
            cmp = subprocess.run(["git", "rev-list", "--left-right", "--count", revspec], capture_output=True, text=True, cwd=repo_root, timeout=5)
            if cmp.returncode != 0:
                dlog(f"Rev-list failed: {cmp.stderr.strip()}")
                return {"has_update": False, "error": cmp.stderr.strip(), "branch": branch_name}
            
            dlog(f"Rev-list output: {cmp.stdout.strip()}")
            parts = cmp.stdout.strip().split()
            ahead = int(parts[0]) if len(parts) > 0 else 0
            behind = int(parts[1]) if len(parts) > 1 else 0
            
            res = {
                "has_update": bool(behind > 0),
                "branch": branch_name,
                "upstream": revspec.split('...')[1],
                "ahead": ahead,
                "behind": behind,
                "head": "", # simplified for log
                "remote": ""
            }
            dlog(f"Result: {res}")
            return res
    except Exception as e:
        try:
            with open("debug_update_handler.log", "a", encoding="utf-8") as log_file:
                 log_file.write(f"EXCEPTION: {e}\n")
        except:
            pass
        return {"has_update": False, "error": str(e)}

@server.get("/log/{task_id}")
def get_task_log(task_id):
    return task_log_handler.get_task_log(task_id)


@server.post("/action/bot/reset-task")
def reset_task(req: ResetTaskRequest):
    bot_ctrl.reset_task(req.task_id)


@server.post("/action/bot/start")
def start_bot():
    bot_ctrl.start()


@server.post("/action/bot/stop")
def stop_bot():
    bot_ctrl.stop()


@server.post("/action/bot/stop-after-run")
def stop_after_run():
    return {"stop_after_run": bot_ctrl.toggle_stop_after_run()}


@server.get("/action/bot/status")
def bot_status():
    return bot_ctrl.get_status()


@server.get("/api/pal-defaults")
def get_pal_defaults():
    # "Pal" support-card defaults are a turn-by-turn career feature; this app
    # has no equivalent. Kept as an empty result rather than a 500 so a stale
    # dashboard build cannot break on it.
    return {}



@server.get("/")
async def get_index():
    return FileResponse('public/index.html', headers={
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    })


@server.get("/{whatever:path}")
async def get_static_files_or_404(whatever):
    # try open file for path
    file_path = os.path.join("public", whatever)
    # 设置防缓存头
    no_cache_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    if os.path.isfile(file_path):
        if file_path.endswith((".js", ".mjs")):
            return FileResponse(file_path, media_type="application/javascript", headers=no_cache_headers)
        else:
            return FileResponse(file_path, headers=no_cache_headers)
    return FileResponse('public/index.html', headers=no_cache_headers)
