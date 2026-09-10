"""The dashboard, and the three ways it could quietly stop working.

There is no build step and no framework, so most of what a test suite would
normally catch is not applicable. What is worth pinning is the seam between the
page and the rest of the project, because nothing else checks it:

* **Every path the page calls must be a route the server serves.** A renamed
  endpoint shows up as a dead button, not an error.
* **Every setting the page sends must be one `build_task` reads.** A renamed
  field is silently ignored and falls back to its default - so the task would
  look saved and run with the wrong settings.
* **Nothing may be loaded from the network.** The parent project pulls
  Bootstrap and jQuery from a CDN, so its dashboard needs internet to render -
  for a bot driving an emulator on the same machine.
"""
import ast, io, os, re, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

PAGE = 'public/index.html'
failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


html = io.open(PAGE, encoding='utf-8').read()
server_src = io.open('bot/server/handler.py', encoding='utf-8').read()

print("no network dependency")
external = re.findall(r'''(?:src|href)\s*=\s*["'](https?:)?//[^"']+''', html)
check("nothing is loaded from another origin", not external, str(external))
check("the page is one file", os.path.isdir('public')
      and os.listdir('public') == ['index.html'], str(os.listdir('public')))

print("\nevery path the page calls is a route the server serves")
# Routes, as the server declares them, with their path parameters generalised.
routes = set()
for m in re.finditer(r'@server\.(get|post|delete|put)\("([^"]+)"\)', server_src):
    routes.add(re.sub(r'\{[^}]+\}', '*', m.group(2)))

# Calls the page makes. api() takes a literal path, sometimes concatenated with
# an id - the concatenation is normalised the same way the routes are.
concatenated = {m.group(1) for m in re.finditer(r'api\(\s*"([^"]+)"\s*\+', html)}
called = {p + '*' for p in concatenated}
called |= {m.group(1) for m in re.finditer(r'api\(\s*"([^"]+)"', html)
           if m.group(1) not in concatenated}

for path in sorted(called):
    check(f"{path}", path in routes or path.rstrip('*') + '*' in routes,
          f"not among {sorted(routes)}")

print("\nevery setting the page sends is one build_task reads")
# The payload the page POSTs, read out of its own source.
payload_block = re.search(r'const payload = \{(.*?)\n  \};', html, re.S)
check("the payload could be read out of the page", payload_block is not None)
sent = set(re.findall(r'^\s*(\w+):', payload_block.group(1), re.M)) if payload_block else set()

task_src = io.open('uma_it/task.py', encoding='utf-8').read()
read_by_builder = set(re.findall(r"data\.get\(\s*'([^']+)'", task_src))
unknown = sorted(sent - read_by_builder)
check(f"all {len(sent)} settings are read by build_task", not unknown, str(unknown))

# And the reverse, as information rather than a failure: settings the task
# supports that the page does not expose.
print("\n  settings build_task accepts that the page does not offer:")
for name in sorted(read_by_builder - sent):
    print(f"    {name}")

print("\nthe scenario values the page offers are real")
from uma_it.define import ScenarioType
offered = {int(v) for v in re.findall(r'<option value="(\d+)"', html)}
valid = {s.value for s in ScenarioType if s is not ScenarioType.UNKNOWN}
check("every scenario option maps to a ScenarioType", offered <= valid,
      f"{sorted(offered - valid)} unknown")
check("  and none of the real scenarios is missing", valid <= offered,
      f"{sorted(valid - offered)} not offered")

print("\nthe app name the page posts matches the app")
from uma_it.task import APP_NAME
posted = re.search(r'app_name:\s*"([^"]+)"', html)
check("the page posts this app's name", posted and posted.group(1) == APP_NAME,
      posted.group(1) if posted else "not found")

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
