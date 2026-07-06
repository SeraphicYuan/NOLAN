"""Taste — /taste page + rule review API (SOTA #9).

The anti-lock-in surface: every learned rule is visible with its evidence,
amendable, and retirable — nothing the distiller mints becomes doctrine
without a human clicking it into place, and nothing stays doctrine when the
human stops believing it.
"""

from fastapi import Body, HTTPException
from fastapi.responses import HTMLResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir

    @app.get("/taste", response_class=HTMLResponse)
    async def taste_page():
        tpl = templates_dir / "taste.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>taste.html not found</h1>"

    @app.get("/api/taste")
    async def api_taste():
        from nolan.taste import load_ledger, load_rules
        ledger = load_ledger()
        projects = sorted({e.get("project", "?") for e in ledger})
        return {"rules": load_rules(),
                "ledger": {"events": len(ledger), "projects": projects,
                           "recent": ledger[-12:]}}

    @app.post("/api/taste/rule")
    async def api_taste_rule(payload: dict = Body(...)):
        """Add or edit a rule (writes profiles/taste.json; consumed by
        guidance_for -> every authoring agent prompt)."""
        from nolan.taste import upsert_rule, validate_rule
        rule = dict(payload)
        # user-authored rules default straight to active (it's their taste)
        rule.setdefault("status", "active")
        rule.setdefault("confidence", 0.8)
        try:
            return upsert_rule(rule)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/taste/rule/status")
    async def api_taste_status(payload: dict = Body(...)):
        """accept (proposed->active) / lock / retire — the rule lifecycle."""
        from nolan.taste import set_rule_status
        try:
            return set_rule_status(payload.get("id", ""),
                                   payload.get("status", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/taste/retro")
    async def api_taste_retro():
        """Run the distiller over the ledger (proposals await acceptance)."""
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        from nolan.taste import distill
        try:
            llm = create_text_llm(load_config())
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"no LLM: {exc}")
        return await distill(llm)
