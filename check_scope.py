"""No name may be read that nothing defines.

A dangling global reference does not fail at import. It fails the first time
that line runs - which for device code means on a real machine with a real
emulator, at the worst moment. `run_health_checks` read `selected_device`, a
module global the parent's `__main__` block happened to set; moving the
function into `device.py` left the reference behind, and it surfaced as
`name 'selected_device' is not defined` on the first real launch.

This uses pyflakes rather than a hand-rolled scan. The hand-rolled version
written first treated any assignment anywhere in a file as a definition, so a
name assigned inside one function counted as defined for every other function -
which is precisely how `selected_device` slipped through it too. It also found
three genuinely missing skill templates, so the idea was right and the
implementation was not.

`import *` is refused for the same reason: pyflakes cannot see through one, so
a star import is a hole in this check rather than a matter of style.
"""
import io, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    from pyflakes.api import check as pyflakes_check
    from pyflakes.reporter import Reporter
except ImportError:
    print("  SKIP  pyflakes is not installed; cannot check for undefined names")
    sys.exit(0)

FILES = ['main.py', 'device.py']
for folder in ('uma_it', 'uma_it/asset'):
    FILES += [os.path.join(folder, f) for f in sorted(os.listdir(folder))
              if f.endswith('.py')]

out, err = io.StringIO(), io.StringIO()
reporter = Reporter(out, err)
for path in FILES:
    pyflakes_check(io.open(path, encoding='utf-8').read(), path, reporter)

lines = out.getvalue().splitlines()
undefined = [l for l in lines if 'undefined name' in l]
stars = [l for l in lines if 'import *' in l]

print(f"scanned {len(FILES)} files")
print(f"  {'ok  ' if not undefined else 'FAIL'}  undefined names: {len(undefined)}")
for line in undefined:
    print("      " + line)
print(f"  {'ok  ' if not stars else 'FAIL'}  star imports, which this check "
      f"cannot see through: {len(stars)}")
for line in stars:
    print("      " + line)

# Everything else pyflakes reports - unused imports, f-strings without
# placeholders - is style, and not what this file is for.
sys.exit(1 if (undefined or stars) else 0)
