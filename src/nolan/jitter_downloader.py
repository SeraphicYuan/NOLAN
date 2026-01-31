"""
Jitter.video Lottie downloader using Playwright browser automation.

Downloads Lottie animations from Jitter's template library.
Requires: pip install playwright && playwright install chromium
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from nolan.downloaders.utils import (
    sanitize_filename,
    extract_lottie_metadata,
    save_lottie_json,
    CatalogBuilder,
)

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class JitterTemplate:
    """Metadata for a Jitter template."""
    id: str
    name: str
    category: str
    url: str
    width: int = 800
    height: int = 600
    duration_seconds: float = 0
    fps: int = 60
    file_size_bytes: int = 0
    local_path: str = ""
    downloaded_at: str = ""
    artboard_id: str = ""


# Jitter template categories
JITTER_CATEGORIES = [
    "video-titles",
    "social-media",
    "logos",
    "ui-elements",
    "icons",
    "buttons",
    "text",
    "backgrounds",
    "charts",
    "devices",
    "ads",
    "showreels",
]


class JitterDownloader:
    """
    Download Lottie animations from Jitter.video using browser automation.

    Example:
        async with JitterDownloader() as downloader:
            templates = await downloader.discover_templates("video-titles", limit=5)
            for template in templates:
                await downloader.download_template(template)
    """

    def __init__(
        self,
        output_dir: str = "assets/common/lottie",
        headless: bool = True,
        delay_between_downloads: float = 2.0,
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is required. Install with: "
                "pip install playwright && playwright install chromium"
            )

        self.output_dir = Path(output_dir)
        self.headless = headless
        self.delay = delay_between_downloads
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._playwright = None

    async def __aenter__(self):
        """Async context manager entry - launch browser."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(accept_downloads=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close browser."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def discover_templates(
        self,
        category: str,
        limit: int = 10,
    ) -> list[JitterTemplate]:
        """
        Discover templates from a Jitter category page.

        Args:
            category: Category name (e.g., "video-titles", "logos")
            limit: Maximum number of templates to discover

        Returns:
            List of JitterTemplate objects
        """
        if category not in JITTER_CATEGORIES:
            print(f"Warning: '{category}' not in known categories: {JITTER_CATEGORIES}")

        page = await self.context.new_page()
        templates = []

        try:
            url = f"https://jitter.video/templates/{category}/"
            print(f"Discovering templates from: {url}")

            await page.goto(url, timeout=60000)
            await asyncio.sleep(5)  # Wait for JS to load

            # Scroll to load more templates
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(1)

            # Find template links
            file_links = await page.query_selector_all('a[href*="/file/?id="]')

            for link in file_links[:limit]:
                href = await link.get_attribute("href")
                name = await link.inner_text()

                if href and name:
                    # Extract template ID
                    match = re.search(r'/file/\?id=([a-zA-Z0-9]+)', href)
                    if match:
                        template_id = match.group(1)
                        template = JitterTemplate(
                            id=template_id,
                            name=name.strip(),
                            category=category,
                            url=f"https://jitter.video{href}" if href.startswith("/") else href,
                        )
                        templates.append(template)

            print(f"Found {len(templates)} templates in '{category}'")

        finally:
            await page.close()

        return templates

    async def download_template(
        self,
        template: JitterTemplate,
        local_name: Optional[str] = None,
    ) -> Optional[JitterTemplate]:
        """
        Download a single template as Lottie JSON.

        Args:
            template: JitterTemplate to download
            local_name: Optional custom filename (without extension)

        Returns:
            Updated JitterTemplate with local_path, or None on failure
        """
        page = await self.context.new_page()

        try:
            print(f"  Downloading: {template.name} ({template.id})")

            # Open template in editor
            await page.goto(template.url, timeout=60000)
            await asyncio.sleep(5)

            # Dismiss any modals/popups
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            # Check for "File not found" error
            not_found = await page.query_selector('text="File not found."')
            if not_found:
                print(f"    Template not found (deleted or private)")
                return None

            # Click Export button
            export_btn = await page.query_selector('button:has-text("Export")')
            if not export_btn:
                print(f"    Export button not found (page structure may differ)")
                return None

            # Check if Export button is enabled
            is_disabled = await export_btn.is_disabled()
            if is_disabled:
                # Try to select an artboard by clicking in the canvas area
                print(f"    Export disabled - trying to select artboard...")
                await page.mouse.click(500, 300)
                await asyncio.sleep(1)

                # Check again
                is_disabled = await export_btn.is_disabled()
                if is_disabled:
                    # Try a second position (for different layouts)
                    await page.mouse.click(600, 350)
                    await asyncio.sleep(1)
                    is_disabled = await export_btn.is_disabled()

                if is_disabled:
                    print(f"    Could not enable Export (multiple artboards not selectable)")
                    return None
                else:
                    print(f"    Artboard selected, Export now enabled")

            await export_btn.click()
            await asyncio.sleep(2)

            # Click Lottie option (opens new page)
            # Scroll down in case Lottie option is below the fold
            await page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(0.5)

            lottie_option = await page.query_selector('text=Lottie')
            if not lottie_option:
                print(f"    Lottie option not found")
                return None

            # Check if Lottie option is clickable
            is_visible = await lottie_option.is_visible()
            if not is_visible:
                print(f"    Lottie option not visible")
                return None

            async with self.context.expect_page(timeout=15000) as new_page_info:
                await lottie_option.click(timeout=10000)

            lottie_page = await new_page_info.value
            await lottie_page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)

            # Extract artboard ID from URL
            url_match = re.search(r'artboardId=([a-zA-Z0-9]+)', lottie_page.url)
            if url_match:
                template.artboard_id = url_match.group(1)

            # Find blob download link
            download_link = await lottie_page.query_selector('a[download][href^="blob:"]')
            if not download_link:
                print(f"    Download link not found")
                await lottie_page.close()
                return None

            original_filename = await download_link.get_attribute("download")

            # Fetch blob content
            blob_content = await lottie_page.evaluate('''async () => {
                const link = document.querySelector('a[download][href^="blob:"]');
                if (!link) return null;
                const response = await fetch(link.href);
                return await response.text();
            }''')

            await lottie_page.close()

            if not blob_content:
                print(f"    Failed to fetch blob content")
                return None

            # Parse and validate Lottie JSON
            try:
                lottie_data = json.loads(blob_content)
            except json.JSONDecodeError:
                print(f"    Invalid JSON content")
                return None

            # Extract metadata from Lottie using shared utility
            meta = extract_lottie_metadata(lottie_data)
            template.width = meta["width"] or 800
            template.height = meta["height"] or 600
            template.fps = meta["fps"] or 60
            template.duration_seconds = meta["duration_seconds"]

            # Determine save path
            filename = local_name or self._sanitize_filename(template.name)
            category_dir = self.output_dir / f"jitter-{template.category}"
            save_path = category_dir / f"{filename}.json"

            # Save file using shared utility
            template.file_size_bytes = save_lottie_json(lottie_data, save_path)

            template.local_path = str(save_path.relative_to(self.output_dir))
            template.downloaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(f"    Saved: {template.local_path} ({template.file_size_bytes} bytes)")

            # Rate limiting
            await asyncio.sleep(self.delay)

            return template

        except Exception as e:
            print(f"    Error: {e}")
            return None
        finally:
            await page.close()

    async def download_category(
        self,
        category: str,
        limit: int = 10,
    ) -> list[JitterTemplate]:
        """
        Download templates from a category.

        Args:
            category: Category name
            limit: Maximum templates to download

        Returns:
            List of successfully downloaded templates
        """
        templates = await self.discover_templates(category, limit=limit)
        results = []

        for i, template in enumerate(templates):
            print(f"\n[{i+1}/{len(templates)}] {template.name}")
            result = await self.download_template(template)
            if result:
                results.append(result)

        return results

    def _sanitize_filename(self, name: str) -> str:
        """Convert template name to safe filename."""
        return sanitize_filename(name)

    def create_catalog(self, templates: list[JitterTemplate]) -> dict:
        """
        Create a catalog JSON from downloaded templates.

        Args:
            templates: List of downloaded templates

        Returns:
            Catalog dictionary
        """
        catalog = {
            "source": "jitter.video",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(templates),
            "categories": {},
        }

        for template in templates:
            cat = template.category
            if cat not in catalog["categories"]:
                catalog["categories"][cat] = []

            catalog["categories"][cat].append({
                "id": template.id,
                "name": template.name,
                "url": template.url,
                "local_path": template.local_path,
                "width": template.width,
                "height": template.height,
                "fps": template.fps,
                "duration_seconds": template.duration_seconds,
                "file_size_bytes": template.file_size_bytes,
                "downloaded_at": template.downloaded_at,
            })

        # Save catalog
        catalog_path = self.output_dir / "jitter-catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)

        print(f"\nCatalog saved: {catalog_path}")
        return catalog


async def download_essential_jitter_templates():
    """Download a curated set of essential Jitter templates."""

    # Categories with good free templates for video production
    essential_categories = [
        ("video-titles", 5),
        ("text", 3),
        ("icons", 3),
        ("ui-elements", 2),
    ]

    all_templates = []

    async with JitterDownloader(headless=True, delay_between_downloads=3.0) as downloader:
        for category, limit in essential_categories:
            print(f"\n{'='*50}")
            print(f"Category: {category}")
            print('='*50)

            results = await downloader.download_category(category, limit=limit)
            all_templates.extend(results)

        # Create catalog
        if all_templates:
            downloader.create_catalog(all_templates)

    print(f"\n{'='*50}")
    print(f"Downloaded {len(all_templates)} templates total")
    return all_templates


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Lottie animations from Jitter.video")
    parser.add_argument("--category", type=str, help="Category to download from")
    parser.add_argument("--limit", type=int, default=5, help="Max templates per category")
    parser.add_argument("--essential", action="store_true", help="Download essential templates")
    parser.add_argument("--list-categories", action="store_true", help="List available categories")
    parser.add_argument("--output", type=str, default="assets/common/lottie", help="Output directory")
    parser.add_argument("--visible", action="store_true", help="Show browser window")

    args = parser.parse_args()

    if args.list_categories:
        print("Available Jitter categories:")
        for cat in JITTER_CATEGORIES:
            print(f"  - {cat}")
    elif args.essential:
        asyncio.run(download_essential_jitter_templates())
    elif args.category:
        async def run():
            async with JitterDownloader(
                output_dir=args.output,
                headless=not args.visible,
            ) as downloader:
                results = await downloader.download_category(args.category, limit=args.limit)
                if results:
                    downloader.create_catalog(results)
        asyncio.run(run())
    else:
        parser.print_help()
