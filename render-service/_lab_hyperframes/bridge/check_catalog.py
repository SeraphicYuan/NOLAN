"""Honesty test for catalog.json — the catalog claims a set of scene templates; this proves
they exactly match what compose.py actually stamps. Run in CI / before authoring. Exits 1 on
any drift (a template with no catalog entry, or a catalog entry with no template)."""
import json, sys
from pathlib import Path
import compose

HERE = Path(__file__).parent
cat = json.load(open(HERE / "catalog.json", encoding="utf-8"))

catalog_types = set(cat["scene_templates"])
block_types = set(compose.BLOCKS)

errs = []
missing = block_types - catalog_types
extra = catalog_types - block_types
if missing:
    errs.append(f"compose.BLOCKS has types the catalog does not document: {sorted(missing)}")
if extra:
    errs.append(f"catalog documents types that are not in compose.BLOCKS: {sorted(extra)}")

# every catalog entry names the real compose function
for t, entry in cat["scene_templates"].items():
    fn = entry.get("fn")
    if t in compose.BLOCKS and compose.BLOCKS[t].__name__ != fn:
        errs.append(f"catalog['{t}'].fn={fn!r} != compose.BLOCKS['{t}'].__name__={compose.BLOCKS[t].__name__!r}")

# components must name real functions too
for name in cat["components"]:
    if not hasattr(compose, name):
        errs.append(f"catalog component {name!r} has no compose.{name} function")

# reveal styles: the catalog's `reveals` keys must exactly match compose.REVEALS (minus _doc)
cat_reveals = set(cat.get("reveals", {})) - {"_doc"}
code_reveals = set(getattr(compose, "REVEALS", {}))
r_missing = code_reveals - cat_reveals
r_extra = cat_reveals - code_reveals
if r_missing:
    errs.append(f"compose.REVEALS has styles the catalog does not document: {sorted(r_missing)}")
if r_extra:
    errs.append(f"catalog['reveals'] documents styles not in compose.REVEALS: {sorted(r_extra)}")

# scene transitions: the catalog's `transitions` keys must exactly match compose.TRANSITIONS (minus _doc)
cat_trans = set(cat.get("transitions", {})) - {"_doc"}
code_trans = set(getattr(compose, "TRANSITIONS", {}))
t_missing = code_trans - cat_trans
t_extra = cat_trans - code_trans
if t_missing:
    errs.append(f"compose.TRANSITIONS has kinds the catalog does not document: {sorted(t_missing)}")
if t_extra:
    errs.append(f"catalog['transitions'] documents kinds not in compose.TRANSITIONS: {sorted(t_extra)}")

if errs:
    print("CATALOG DRIFT:")
    for e in errs:
        print("  ✗", e)
    sys.exit(1)
print(f"OK — catalog matches compose.py: scene templates {sorted(catalog_types)}, "
      f"components {sorted(cat['components'])}, reveals {sorted(code_reveals)}, "
      f"transitions {sorted(code_trans)}")
