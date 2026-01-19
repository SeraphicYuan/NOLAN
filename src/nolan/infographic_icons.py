"""Icon resolver for AntV infographic templates."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import httpx


class IconResolver:
    """Resolve icon keywords to AntV icon names."""

    def __init__(self, base_url: str = "https://infographic.antv.vision/icon") -> None:
        self.base_url = base_url
        self._icons: Optional[List[str]] = None

    async def fetch_icons(self) -> List[str]:
        """Fetch icon names from the AntV icon API."""
        if self._icons is not None:
            return self._icons

        icons: List[str] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url)
                response.raise_for_status()
                icons = self._parse_icon_response(response.text)
        except Exception:
            icons = []

        self._icons = icons
        return icons

    async def resolve(self, keyword: str) -> Optional[str]:
        """Resolve a keyword to a matching icon name."""
        keyword_norm = keyword.strip().lower()
        if not keyword_norm:
            return None

        icons = await self.fetch_icons()
        if not icons:
            return None

        exact = next((name for name in icons if name.lower() == keyword_norm), None)
        if exact:
            return exact

        contains = next((name for name in icons if keyword_norm in name.lower()), None)
        if contains:
            return contains

        starts = next((name for name in icons if name.lower().startswith(keyword_norm)), None)
        return starts

    async def apply_to_items(self, items: Iterable[Dict]) -> bool:
        """Apply icon resolution to items with icon_keyword."""
        changed = False
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("icon"):
                continue
            keyword = item.get("icon_keyword")
            if not isinstance(keyword, str):
                continue
            icon = await self.resolve(keyword)
            if icon:
                item["icon"] = icon
                changed = True
        return changed

    def _parse_icon_response(self, text: str) -> List[str]:
        """Parse icon response into a flat list of names."""
        try:
            data = httpx.Response(200, text=text).json()
        except Exception:
            return []

        if isinstance(data, list):
            return self._extract_names(data)

        if isinstance(data, dict):
            for key in ("data", "icons", "items", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    return self._extract_names(value)
            return self._extract_names(list(data.values()))

        return []

    def _extract_names(self, values: Iterable) -> List[str]:
        names: List[str] = []
        for value in values:
            if isinstance(value, str):
                names.append(value)
            elif isinstance(value, dict):
                name = value.get("name") or value.get("id") or value.get("key")
                if isinstance(name, str):
                    names.append(name)
        return names
