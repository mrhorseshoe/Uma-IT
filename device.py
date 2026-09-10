"""Finding the emulator, and getting it into a state the bot can drive.

Moved from the parent project's `main.py` essentially unchanged. This is
infrastructure rather than game logic: ADB discovery, the soft recovery that
brings an offline device back, a screenshot probe that proves capture actually
works, and the health checks that run before anything else starts.

It is kept out of `main.py` so that file stays short enough to read in one
go - the parent's is 607 lines, of which about 360 are this.

The one thing to know: `PACKAGE_NAME` is the only game-specific string here,
and it is the same client the parent drives.
"""
import os
import subprocess
import threading
import time

import cv2
import yaml

import bot.base.log as logger

log = logger.get_logger(__name__)

PACKAGE_NAME = "com.cygames.umamusume"


def _get_adb_path():
    """Resolve bundled adb path."""
    return os.path.join("deps", "adb", "adb.exe")


def _run_adb(args, timeout=15, capture_output=True, text=True):
    """Run an adb command with the bundled binary and return CompletedProcess."""
    adb_path = _get_adb_path()
    return subprocess.run([adb_path] + args, capture_output=capture_output, text=text, timeout=timeout)


def _soft_recover_device(device_id):
    """Attempt a non-destructive recovery of adb/uiautomator2 for a single device.

    Steps:
    - Remove adb forwards for the device (cleans stale 7912 bindings)
    - Kill/start adb server (what you usually do manually)
    - Wait for device to be ready again
    - Run uiautomator2 healthcheck to restart atx-agent if needed
    """
    try:
        print("   ♻️  Attempting auto-recovery (safe)…")
        
        # 1. Try simple reconnect for offline devices
        try:
            print("   🔄 Attempting 'adb reconnect offline'...")
            _run_adb(["reconnect", "offline"], timeout=10)
            # Give it a moment to reconnect
            time.sleep(2)
            # Check if it worked
            res = _run_adb(["devices"], timeout=5)
            if device_id in res.stdout and "offline" not in res.stdout:
                print("   ✅ Device seems back online!")
                return
        except Exception:
            pass
            
        # 1.5 Special handling for emulators (often stuck offline)
        if device_id.startswith("emulator-"):
            try:
                # emulator-5554 -> port 5554 (console) -> port 5555 (adb)
                serial_port = int(device_id.split("-")[1])
                adb_port = serial_port + 1
                print(f"   💊 attempting to re-engage emulator via TCP {adb_port}...")
                _run_adb(["connect", f"127.0.0.1:{adb_port}"], timeout=10)
                time.sleep(1)
            except Exception:
                pass

        # 2. Heavier recovery
        # Best-effort forward removal (ignore failures)
        try:
            _run_adb(["-s", device_id, "forward", "--remove-all"], timeout=5)
        except Exception:
            pass

        # Kill any existing adb processes to clear stale connections
        try:
            print("   🧹 Cleaning up stale ADB processes...")
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe", "/T"], capture_output=True, timeout=5)
            time.sleep(1)
        except Exception:
            pass

        # Restart adb server
        try:
            _run_adb(["kill-server"], timeout=10)
        except Exception:
            pass
        _run_adb(["start-server"], timeout=15)

        # Ensure target device comes back online - increased timeout to 60s
        print(f"   ⏳ Waiting for device {device_id} to reconnect (up to 60s)...")
        try:
            _run_adb(["-s", device_id, "wait-for-device"], timeout=60)
        except subprocess.TimeoutExpired:
            print("   🥶 Device still unresponsive.")
            if device_id.startswith("emulator-"):
                print("   👉 ACTION REQUIRED: Your emulator appears frozen. Please restart the emulator manually.")
            raise

        # Ping device quickly
        pong = _run_adb(["-s", device_id, "shell", "echo", "pong"], timeout=5)
        if pong.returncode != 0:
            print("   ⚠️  Device not responsive yet; will still try healthcheck…")

        # Light uiautomator2 warmup (avoid heavy healthcheck that may reinstall UIA APKs)
        try:
            import uiautomator2 as u2
            d = u2.connect(device_id)
            # Warm up a simple RPC that doesn't require UIAutomator service
            _ = d.window_size()
            # Also ensure adb shell is responsive
            _run_adb(["-s", device_id, "shell", "echo", "ok"], timeout=5)
            time.sleep(0.2)
        except Exception as e:
            print(f"   ⚠️  uiautomator2 warmup failed: {e}")
        print("   ✅ Auto-recovery step completed")
    except Exception as e:
        print(f"   ❌ Auto-recovery failed: {e}")


def _screenshot_probe(device_id, samples=3, delay=0.5):
    """Try to take several screenshots via uiautomator2 and validate basic quality."""
    import uiautomator2 as u2
    print("   🔌 Connecting to device…")
    d = u2.connect(device_id)
    print("   ✅ Device connected successfully")

    screenshots = []
    print("   Taking screenshots (this may take a moment)…")
    for i in range(samples):
        print(f"      Screenshot {i+1}/{samples}…")
        img = d.screenshot(format='opencv')
        if img is not None:
            screenshots.append(img)
            print(f"      ✅ Screenshot {i+1}: {img.shape[1]}x{img.shape[0]} pixels")
        else:
            print(f"      ❌ Screenshot {i+1}: FAILED")
        time.sleep(delay)

    if len(screenshots) < samples:
        raise RuntimeError("insufficient_screenshots")

    print("   🔍 Analyzing screenshot quality…")
    if screenshots[0].std() < 5:
        raise RuntimeError("corrupted_static_image")

    print("   🔄 Checking for display pipeline issues…")
    diff1 = cv2.absdiff(screenshots[0], screenshots[1]).mean()
    diff2 = cv2.absdiff(screenshots[1], screenshots[2]).mean()
    if diff1 < 1 and diff2 < 1:
        raise RuntimeError("display_stuck")

    print("✅ Screenshot quality: OK")


def _finalize_services_light(device_id: str, timeout_sec: float = 6.0) -> bool:
    """Warm up uiautomator2 lightly without risking APK installs, with timeout."""
    result = {"ok": False, "err": None}

    def _task():
        try:
            import uiautomator2 as u2
            d = u2.connect(device_id)
            _ = d.window_size()
            time.sleep(0.2)
            result["ok"] = True
        except Exception as e:  # noqa: BLE001
            result["err"] = e

    t = threading.Thread(target=_task, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        print("⚠️  Finalization timed out; continuing without it")
        return False
    if not result["ok"]:
        print(f"⚠️  Could not finalize device services: {result['err']}")
        return False
    print("✅ Device services ready")
    return True


def get_adb_devices():
    """Get list of connected ADB devices"""
    try:
        # Use the adb from deps directory
        adb_path = _get_adb_path()
        
        if not os.path.exists(adb_path):
            print("❌ ADB not found in deps/adb/ directory")
            return []
        
        # First try to get devices
        result = subprocess.run([adb_path, "devices"], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"❌ ADB error: {result.stderr}")
            return []
        
        devices = []
        lines = result.stdout.strip().split('\n')[1:]  # Skip header line
        
        for line in lines:
            if line.strip() and '\t' in line:
                device_id, status = line.split('\t')
                # Accept offline devices so we can try to recover them
                if status == 'device' or status == 'offline':
                    devices.append(device_id)
        
        # If no devices found, try restarting ADB server
        if not devices:
            print("🔄 No devices found, restarting ADB server...")
            subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=5)
            subprocess.run([adb_path, "start-server"], capture_output=True, timeout=10)
            
            # Try again after restart
            result = subprocess.run([adb_path, "devices"], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]
                for line in lines:
                    if line.strip() and '\t' in line:
                        device_id, status = line.split('\t')
                        if status == 'device' or status == 'offline':
                            devices.append(device_id)
        
        return devices
    except Exception as e:
        print(f"❌ Error getting ADB devices: {e}")
        return []


def check_umamusume_running(device_id):
    """Check if Umamusume is running on the device"""
    try:
        adb_path = _get_adb_path()
        cmd = [adb_path, "-s", device_id, "shell", "dumpsys", "activity", "activities"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            # Look for Umamusume package in running activities
            output = result.stdout.lower()
            umamusume_packages = [
                "com.cygames.umamusume",
                "jp.co.cygames.umamusume",
                "umamusume"
            ]
            return any(pkg in output for pkg in umamusume_packages)
    except:
        pass
    return False


def select_device():
    """Let user select an ADB device"""
    print("🔍 Scanning for ADB devices...")
    devices = get_adb_devices()
    
    if not devices:
        print("❌ No ADB devices found!")
        print("Please ensure:")
        print("1. Your emulator is running")
        print("2. ADB is enabled in emulator settings")
        print("3. USB debugging is enabled")
        return None

    
    print(f"\n📱 Found {len(devices)} device(s):")
    
    # Check which devices have Umamusume running
    device_info = []
    for i, device_id in enumerate(devices, 1):
        has_umamusume = check_umamusume_running(device_id)
        status = "🎮 Umamusume Running" if has_umamusume else "📱 Device Connected"
        device_info.append((device_id, has_umamusume))
        print(f"{i}. {device_id} - {status}")
    
    # Prioritize devices with Umamusume running
    umamusume_devices = [d for d, has_uma in device_info if has_uma]
    other_devices = [d for d, has_uma in device_info if not has_uma]
    


    if len(devices) == 1:
        return devices[0] 

    if umamusume_devices:
        print(f"\n🎯 Recommended devices (Umamusume detected):")
        for i, device_id in enumerate(umamusume_devices, 1):
            print(f"  {i}. {device_id}")
    




    while True:
        try:
            choice = input(f"\nSelect device (1-{len(devices)}) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(devices):
                selected_device = devices[choice_num - 1]
                print(f"✅ Selected device: {selected_device}")
                return selected_device
            else:
                print("❌ Invalid choice. Please try again.")
        except ValueError:
            print("❌ Please enter a valid number.")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return None


def update_config(device_name):
    """Update config.yaml with selected device"""
    try:
        with open("config.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        config['bot']['auto']['adb']['device_name'] = device_name
        
        with open("config.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"✅ Updated config.yaml with device: {device_name}")
        return True
    except Exception as e:
        print(f"❌ Error updating config: {e}")
        return False


def run_health_checks(device_id):
    """Run health checks against the chosen device.

    `device_id` is a parameter here, where the parent read it from a module
    global its `__main__` block happened to set. Moving the function out of
    main.py left that reference dangling, which failed as
    `name 'selected_device' is not defined` on the first real run.
    """
    print(" Running connection health checks...")
    
    # Test ADB connection - increased timeout to 20s
    try:
        adb_path = _get_adb_path()
        result = subprocess.run([adb_path, "devices"], 
                              capture_output=True, text=True, timeout=20)
        
        if result.returncode == 0:
            output = result.stdout
            if device_id in output:
                if "offline" in output:
                     print("❌ ADB connection: OK but device is OFFLINE")
                     return False
                print("✅ ADB connection: OK")
            else:
                 print("❌ ADB connection: Device not listed")
                 return False
        else:
            print("❌ ADB connection: FAILED")
            return False
    except Exception as e:
        print(f"❌ ADB health check failed: {e}")
        return False
    
    # Test device responsiveness - increased timeout to 20s with retries
    retry_count = 3
    for attempt in range(retry_count):
        try:
            result = subprocess.run([adb_path, "-s", device_id, "shell", "echo", "test"], 
                                  capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                print("✅ Device responsiveness: OK")
                break
            else:
                if attempt < retry_count - 1:
                    print(f"⚠️  Device responsiveness check failed (attempt {attempt+1}/{retry_count}). Retrying...")
                    time.sleep(2)
                else:
                    print("❌ Device responsiveness: FAILED")
                    return False
        except Exception as e:
            if attempt < retry_count - 1:
                print(f"⚠️  Device responsiveness check error: {e}. Retrying...")
                time.sleep(2)
            else:
                print(f"❌ Device health check failed: {e}")
                return False
    
    # Test Umamusume detection
    if check_umamusume_running(device_id):
        print("✅ Umamusume detection: OK")
    else:
        print("⚠️  Umamusume not running (this is OK)")
    
        
    print("✅ All health checks passed!")
    return True
