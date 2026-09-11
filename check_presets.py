"""Skill presets: saved, listed, loaded, deleted - and nothing escapes the folder.

A preset name becomes a filename, so it is the one piece of user input here
that touches the filesystem. The parent writes `folder + "/" + name + ".json"`
straight from the request.
"""
import io, json, os, shutil, sys, tempfile
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from uma_it import presets

failures = []


def _raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


tmp = tempfile.mkdtemp(prefix="umait-presets-")
presets.FOLDER = os.path.join(tmp, 'skill_presets')

print("a preset survives being written and read back")
presets.write({'name': 'Fan farming',
               'tiers': [['Corner Acceleration ◯', 'Slipstream'], ['Focus'], []],
               'blacklist': ['Lone Wolf'], 'only_user_provided': True})
got = presets.read_all()
check("it comes back", len(got) == 1, str(len(got)))
p = got[0] if got else {}
check("  with its tiers", p.get('tiers') == [['Corner Acceleration ◯', 'Slipstream'],
                                             ['Focus'], []], str(p.get('tiers')))
check("  its blacklist", p.get('blacklist') == ['Lone Wolf'], str(p.get('blacklist')))
check("  and its only-these flag", p.get('only_user_provided') is True)
check("  symbols in skill names survive",
      p.get('tiers', [[]])[0][0] == 'Corner Acceleration ◯')

print("\nnames that touch the filesystem")
for hostile in ('../../escaped', 'a/b/c', 'CON', 'dots...', '  spaced  '):
    name = presets.write({'name': hostile, 'tiers': [[]], 'blacklist': []})
    path = os.path.join(presets.FOLDER, name + '.json')
    inside = os.path.realpath(path).startswith(os.path.realpath(presets.FOLDER))
    check(f"{hostile!r} stays inside the folder", inside, os.path.realpath(path))
check("an empty name is refused",
      _raises(lambda: presets.write({'name': '   '})), "no exception")

print("\ndeleting")
before = len(presets.read_all())
check("delete removes one", presets.delete('Fan farming') and
      len(presets.read_all()) == before - 1)
check("deleting what is not there is not an error", presets.delete('nope') is False)

print("\npresets written before a field existed still load")
os.makedirs(presets.FOLDER, exist_ok=True)
with io.open(os.path.join(presets.FOLDER, 'old.json'), 'w', encoding='utf-8') as f:
    json.dump({'name': 'old'}, f)
old = [x for x in presets.read_all() if x['name'] == 'old']
check("an old preset loads", len(old) == 1)
check("  and is padded to three tiers", old and len(old[0]['tiers']) == 3,
      str(old[0]['tiers']) if old else '')

print("\nunreadable files are skipped, not fatal")
with io.open(os.path.join(presets.FOLDER, 'broken.json'), 'w', encoding='utf-8') as f:
    f.write('{not json')
try:
    presets.read_all()
    check("a corrupt preset does not break the listing", True)
except Exception as e:
    check("a corrupt preset does not break the listing", False, str(e))

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
