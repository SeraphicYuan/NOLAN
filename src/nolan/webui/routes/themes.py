"""Theme gallery — a visual showcase of every theme + its axes (palette, type, composition archetype,
mood). Fixes the "I'm blind to what the themes look like" gap and is the QA surface for the composition
module. Page: /themes · data: /api/themes/gallery."""
import json
import re
from pathlib import Path

from fastapi.responses import HTMLResponse

# the tokens.css vars worth surfacing on a specimen card (palette + fonts + a couple of character knobs)
_WANT_VARS = ("--shell", "--surface", "--surface-2", "--surface-3", "--text", "--text-2", "--text-mute",
              "--accent", "--accent-2", "--accent-ink", "--rule",
              "--font-display-en", "--font-body", "--font-mono")


def _parse_tokens(css: str) -> dict:
    out = {}
    for name, val in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", css):
        n = name.strip()
        if n in _WANT_VARS and n not in out:
            out[n] = val.strip()
    return out


def register(app, ctx):
    templates_dir = ctx.templates_dir
    repo = ctx.repo_root
    themes_dir = repo / "themes"
    gallery_template = templates_dir / "theme_gallery.html"

    def _archetypes() -> dict:
        try:
            return json.loads((themes_dir / "composition" / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]
        except Exception:
            return {}

    @app.get("/themes", response_class=HTMLResponse)
    async def theme_gallery_page():
        if gallery_template.exists():
            return gallery_template.read_text(encoding="utf-8")
        return HTMLResponse("<h1>theme_gallery.html missing</h1>", status_code=500)

    @app.get("/api/themes/gallery")
    async def theme_gallery_data():
        """Every theme's axes for the specimen cards: palette + fonts + composition archetype + mood."""
        arch = _archetypes()
        themes = []
        for d in sorted(p for p in themes_dir.iterdir() if p.is_dir() and (p / "theme.json").exists()):
            try:
                meta = json.loads((d / "theme.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            tokens = {}
            tf = d / "tokens.css"
            if tf.exists():
                try:
                    tokens = _parse_tokens(tf.read_text(encoding="utf-8"))
                except Exception:
                    tokens = {}
            mood = meta.get("mood", [])
            tone = "dark" if "dark" in mood else "light"
            themes.append({
                "id": meta.get("id", d.name),
                "name": meta.get("name", d.name),
                "nameZh": meta.get("nameZh", ""),
                "description": meta.get("description", ""),
                "mood": mood,
                "tone": tone,
                "preview": meta.get("preview", {}),
                "fonts": meta.get("fonts", {}),
                "composition": meta.get("composition", {}),
                "tokens": tokens,
            })
        # the archetype vocabulary (id -> intent) so the UI can label + explain the composition chips
        archetypes = {aid: {"intent": a.get("intent", ""), "anchor": a.get("anchor", "")}
                      for aid, a in arch.items()}
        return {"themes": themes, "count": len(themes), "archetypes": archetypes}

    @app.get("/api/themes/samples")
    async def theme_samples():
        """The generated theme × archetype sample matrix (themes/scripts/gen_samples.py): the real
        composed renders that power the Samples tab. Reports which cells have a rendered PNG on disk."""
        sdir = repo / "themes" / "_samples"
        man = sdir / "manifest.json"
        cells = []
        if man.exists():
            try:
                for c in json.loads(man.read_text(encoding="utf-8")):
                    cells.append({"archetype": c.get("archetype"), "theme": c.get("theme"),
                                  "variant": c.get("variant"),   # P3: set on per-variant specimens
                                  "png": c.get("png"), "ready": (sdir / c.get("png", "")).exists()})
            except Exception:
                pass
        return {"cells": cells,
                "archetypes": sorted({c["archetype"] for c in cells}),
                "themes": sorted({c["theme"] for c in cells}),
                "ready": sum(1 for c in cells if c["ready"]), "total": len(cells)}

    @app.get("/api/themes/books")
    async def theme_books():
        """The per-theme theme books (themes/scripts/gen_theme_books.py): the authoring-facing identity +
        capability poster per theme, served at /theme-books/<theme>.png with a JSON companion."""
        bdir = repo / "themes" / "_books"
        books = []
        if bdir.exists():
            for p in sorted(bdir.glob("*.png")):
                meta = {}
                j = bdir / (p.stem + ".json")
                if j.exists():
                    try:
                        meta = json.loads(j.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                books.append({"theme": p.stem, "png": p.name, "name": meta.get("name", p.stem),
                              "personality": meta.get("personality"), "mood": meta.get("mood", []),
                              "specimens": meta.get("specimens", []),
                              "description": meta.get("description", "")})
        return {"books": books, "total": len(books)}
