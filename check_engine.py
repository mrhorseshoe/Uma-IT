"""Every vendored engine module must import, and none may reach back.

The engine was written for the parent project and referenced its game module in
seven places. Three were top-level imports that broke on arrival; this pins
them fixed, and pins that importing the engine pulls in nothing from the parent
project.
"""
import os, sys, pkgutil, importlib
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import bot
failed = []
mods = sorted(m.name for m in pkgutil.walk_packages(bot.__path__, 'bot.'))
for name in mods:
    try:
        importlib.import_module(name)
    except Exception as e:
        failed.append((name, f"{type(e).__name__}: {e}"))

print(f"engine modules imported : {len(mods) - len(failed)}/{len(mods)}")
for n, e in failed:
    print(f"    {n}\n        {e}")

# Nothing from the parent project may be loaded as a side effect of importing
# the engine. `module` is the parent's package name.
strays = sorted(m for m in sys.modules
                if m == 'module' or m.startswith('module.'))
print(f"parent-project modules loaded at import time: {len(strays)}")
for s in strays:
    print("    ", s)

sys.exit(1 if (failed or strays) else 0)
