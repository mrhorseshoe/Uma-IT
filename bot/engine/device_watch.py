"""What the screen watchdog does when the device returns no screenshot at all.

Not a frozen frame - that is a capture stall the game survives, and restarting
the game is the known answer to it. This is `get_screen` returning nothing,
which means the bot cannot see the device, and restarting a game it cannot see
does nothing. The watchdog used to do exactly that, every 95 seconds:

  4 Oct  08:36-17:11  329 game restarts, no screenshot in 8 1/2 hours
  6 Oct  01:58-07:25  209 restarts, ended by the PC restarting
  12 Oct 04:20-08:32  MuMu crashed; the screenshot call never returned, so
                      the whole bot froze with nothing in the log for 4 hours

and on 16 Oct an emulator restart left the ADB server not listing the device
at all, which restarting the ADB server fixed.

So a spell without screenshots climbs a ladder instead, logging what the
device looks like at every step:

  RECONNECT_AFTER    reconnect uiautomator2
  ADB_RESTART_AFTER  restart the ADB server, then reconnect - and again every
                     ADB_RESTART_EVERY while the spell lasts
  GIVE_UP_AFTER      stop the loop, with a reason, until someone looks

Giving up stops the loop rather than failing a career: the career in the game
runs on regardless, and the next Start collects it.
"""
import time

import bot.base.log as logger

log = logger.get_logger(__name__)

RECONNECT_AFTER = 60
ADB_RESTART_AFTER = 120
ADB_RESTART_EVERY = 300
# Long enough for the ladder to try everything twice. On 5 Oct screenshots came
# back on their own after ~50 minutes; on 4 Oct they never did. Stopping costs a
# manual Start; waiting cost 8 1/2 hours.
GIVE_UP_AFTER = 900
# How often a spell re-logs the device's state between ladder steps.
LOG_EVERY = 60


class NoFrameLadder:
    """One per run. The watchdog calls `tick` every time it takes a screenshot."""

    def __init__(self, ctrl, clock=None):
        self.ctrl = ctrl
        self.clock = clock or (lambda: time.time())
        self.since = 0.0          # start of the current spell, 0 when none
        self.reconnected = False
        self.last_adb_restart = 0.0
        self.last_log = 0.0
        self.steps = []           # what this spell has tried, for the recovery line

    def _state(self) -> str:
        try:
            state = self.ctrl.device_state()
        except Exception as e:
            state = f"could not ask adb ({type(e).__name__}: {e})"
        err = getattr(self.ctrl, 'last_screen_error', '') or 'none recorded'
        return f"adb says: {state}; last screenshot error: {err}"

    def tick(self, got_frame: bool) -> str:
        """Advance the ladder. Returns 'give_up' once the spell is past saving."""
        now = self.clock()
        if got_frame:
            if self.since:
                tried = ', '.join(self.steps) if self.steps else 'nothing'
                log.info(f"Screenshots are back after {round(now - self.since)}s "
                         f"(tried: {tried})")
            self.since = 0.0
            self.reconnected = False
            self.last_adb_restart = 0.0
            self.steps = []
            return ''

        if not self.since:
            self.since = now
            self.last_log = now
            log.warning(f"No screenshot from the device - {self._state()}")
            return ''
        gone = now - self.since

        if gone >= GIVE_UP_AFTER:
            log.error(f"No screenshot for {round(gone / 60)} min despite reconnecting "
                      f"({', '.join(self.steps) or 'nothing tried'}) - {self._state()}. "
                      f"Stopping the loop; check the emulator, then start it again.")
            return 'give_up'

        if gone >= ADB_RESTART_AFTER and now - self.last_adb_restart >= ADB_RESTART_EVERY:
            self.last_adb_restart = now
            self.steps.append('ADB server restart')
            log.warning(f"No screenshot for {round(gone)}s - restarting the ADB server "
                        f"and reconnecting ({self._state()})")
            self._try(self.ctrl.restart_adb_server)
            self._try(self.ctrl.reconnect)
            self.last_log = now
            return ''

        if gone >= RECONNECT_AFTER and not self.reconnected:
            self.reconnected = True
            self.steps.append('reconnect')
            log.warning(f"No screenshot for {round(gone)}s - reconnecting to the device "
                        f"({self._state()})")
            self._try(self.ctrl.reconnect)
            self.last_log = now
            return ''

        if now - self.last_log >= LOG_EVERY:
            self.last_log = now
            log.warning(f"Still no screenshot after {round(gone)}s - {self._state()}")
        return ''

    @staticmethod
    def _try(step):
        try:
            step()
        except Exception as e:
            log.warning(f"  that step failed: {type(e).__name__}: {e}")
