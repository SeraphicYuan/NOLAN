"""Test: scriptwriter project store + task brief generation (no LLM/agent).

Verifies:
  1. create() scaffolds a Director-ready project (project.yaml + placeholder
     script.md with the Total Duration marker) plus the scriptgen/ workspace.
  2. add_source handles pasted text (saved to raw/, status=fetched) and bare URLs
     (status=pending); the sources manifest reflects them.
  3. write_script_task embeds the style-guide path, sources, output contract,
     and the grounded-but-graceful policy.
  4. list/get/remove_source/delete behave.

Usage:
    D:/env/nolan/python.exe scripts/test_scriptwriter.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.scriptwriter import ScriptProjectStore, write_script_task

ROOT = "projects/_swtest_root"


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    store = ScriptProjectStore(ROOT)

    # 1: create scaffolds a Director-ready project.
    slug = store.create("Holbein Dance of Death", subject="Hans Holbein's Dance of Death",
                        style_id="art-stories", angle="death as the great leveler",
                        pivot="the Ploughman cut", target_minutes=8)
    print("slug:", slug)
    assert store.project_yaml_path(slug).exists(), "project.yaml missing"
    py = store.project_yaml_path(slug).read_text(encoding="utf-8")
    assert "slug:" in py and "name:" in py, "project.yaml not Director-shaped"
    script0 = store.read_script(slug)
    assert "# Video Script" in script0 and "**Total Duration:**" in script0, "script.md not Director-shaped"
    assert store.brief_path(slug).exists() and store.scriptgen_dir(slug).exists()
    assert store.get(slug)["has_script"] is False, "placeholder should not count as written"
    print("create OK — project.yaml, placeholder script.md, scriptgen/ all present")

    # 2: sources — paste (fetched) and url (pending).
    p = store.add_source(slug, kind="paste", title="Met essay",
                         text="Holbein designed the woodcuts in Basel around 1526. " * 5)
    u = store.add_source(slug, kind="url", url="https://en.wikipedia.org/wiki/Danse_Macabre_(Holbein)")
    assert p["status"] == "fetched" and "text_path" in p
    assert u["status"] == "pending" and u["id"] != p["id"]
    raw_file = store.scriptgen_dir(slug) / p["text_path"]
    assert raw_file.exists(), "pasted source not written to raw/"
    manifest = store.sources_manifest_path(slug).read_text(encoding="utf-8")
    assert p["id"] in manifest and u["id"] in manifest, "manifest missing source ids"
    assert store.get(slug)["source_count"] == 2
    print(f"sources OK — paste={p['id']} (fetched), url={u['id']} (pending)")

    # 3: task brief content.
    task = write_script_task(slug, store)
    for needle in ["script_styles/art-stories/style_guide.md", f"projects/{slug}/script.md",
                   "**Total Duration:**", "## ", "needs-check", "WebFetch",
                   "facts.md", "factcheck.md", "~1200 words"]:
        assert needle in task, f"task brief missing: {needle!r}"
    assert u["url"] in task, "pending URL not listed for fetching"
    print("task brief OK — style path, output contract, grounding policy, pending URL all present")

    # 3b: artifact + source-text reads (UI viewer endpoints rely on these).
    assert store.read_artifact(slug, "brief"), "brief artifact unreadable"
    assert store.read_artifact(slug, "nope") is None, "unknown artifact should be None"
    assert store.read_source_text(slug, p["id"]).strip().startswith("Holbein"), "source text unreadable"
    assert store.read_source_text(slug, u["id"]) is None, "pending url has no text yet"
    print("artifact/source reads OK")

    # 4: list / remove / delete.
    assert any(x["slug"] == slug for x in store.list())
    assert store.remove_source(slug, u["id"]) and store.get(slug)["source_count"] == 1
    assert store.delete(slug) and not store.exists(slug)
    print("list/remove/delete OK")

    shutil.rmtree(ROOT, ignore_errors=True)
    print("\nOK - scriptwriter store + task brief verified.")


if __name__ == "__main__":
    main()
