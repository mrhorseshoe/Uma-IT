"""Check that the extracted asset layer loads and every template file exists."""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import uma_it.asset.ui as ui
import uma_it.asset.point as point
import uma_it.asset.template as template
from bot.base.resource import Template, UI
from bot.base.point import ClickPoint

tpls = {k: v for k, v in vars(template).items() if isinstance(v, Template)}
uis = {k: v for k, v in vars(ui).items() if isinstance(v, UI)}
pts = {k: v for k, v in vars(point).items() if isinstance(v, ClickPoint)}

missing = [f"{k} -> {v.template_path}" for k, v in tpls.items()
           if not os.path.isfile(v.template_path)]
unloadable = [k for k, v in tpls.items() if v.template_image is None]

print(f"templates declared : {len(tpls)}")
print(f"screens declared   : {len(uis)}")
print(f"click points       : {len(pts)}")
print(f"missing PNG files  : {len(missing)}")
for m in missing:
    print("   ", m)
print(f"failed to decode   : {len(unloadable)}")
for u in unloadable:
    print("   ", u)

# every screen's templates must be reachable from this package
orphans = []
for name, u in uis.items():
    for t in (u.check_exist_template_list or []) + (u.check_non_exist_template_list or []):
        if t not in tpls.values():
            orphans.append(f"{name} -> {t.template_name}")
print(f"screens referencing a template outside this package: {len(orphans)}")
for o in orphans:
    print("   ", o)

sys.exit(1 if (missing or unloadable or orphans) else 0)
