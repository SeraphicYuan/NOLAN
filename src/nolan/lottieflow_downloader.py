"""
Lottieflow (Finsweet) Lottie downloader using Playwright browser automation.

Downloads free Lottie animations from Finsweet's Lottieflow library.
Requires: pip install playwright && playwright install chromium

Usage:
    python -m nolan.lottieflow_downloader --list-categories
    python -m nolan.lottieflow_downloader --category menu-nav --limit 5
    python -m nolan.lottieflow_downloader --essential
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from nolan.downloaders.utils import (
    sanitize_filename,
    extract_lottie_metadata,
    save_lottie_json,
)

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class LottieflowTemplate:
    """Metadata for a Lottieflow template."""
    id: str
    name: str
    category: str
    page_url: str
    cdn_url: str = ""
    width: int = 0
    height: int = 0
    duration_seconds: float = 0
    fps: int = 0
    file_size_bytes: int = 0
    local_path: str = ""
    downloaded_at: str = ""


# All Lottieflow categories
LOTTIEFLOW_CATEGORIES = [
    "404",
    "arrow",
    "attention",
    "background",
    "checkbox",
    "communication",
    "countdown",
    "cta",
    "dropdown",
    "ecommerce",
    "loading",
    "media",
    "menu-nav",
    "play",
    "radio",
    "scroll-down",
    "scroll-top",
    "scrolling",
    "search",
    "social-media",
    "success",
]


class LottieflowDownloader:
    """
    Download Lottie animations from Finsweet's Lottieflow using Playwright.

    Example:
        async with LottieflowDownloader() as downloader:
            templates = await downloader.discover_templates("menu-nav", limit=5)
            for template in templates:
                await downloader.download_template(template)
    """

    BASE_URL = "https://finsweet.com/lottieflow"

    def __init__(
        self,
        output_dir: str = "assets/common/lottie",
        headless: bool = True,
        delay_between_downloads: float = 1.0,
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
        self._http_client = httpx.Client(timeout=30.0, follow_redirects=True)

    async def __aenter__(self):
        """Async context manager entry - launch browser."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close browser."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._http_client.close()

    async def discover_templates(
        self,
        category: str,
        limit: int = 50,
    ) -> list[LottieflowTemplate]:
        """
        Discover templates from a Lottieflow category page.

        Args:
            category: Category name (e.g., "menu-nav", "arrow")
            limit: Maximum number of templates to discover

        Returns:
            List of LottieflowTemplate objects
        """
        if category not in LOTTIEFLOW_CATEGORIES:
            print(f"Warning: '{category}' not in known categories: {LOTTIEFLOW_CATEGORIES}")

        page = await self.context.new_page()
        templates = []

        try:
            url = f"{self.BASE_URL}/category/{category}"
            print(f"Discovering templates from: {url}")

            await page.goto(url, timeout=60000)
            await asyncio.sleep(3)  # Wait for JS to load

            # Scroll to load more templates
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(0.5)

            # Find download links
            links = await page.query_selector_all('a[href*="/download/"]')

            seen = set()
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    # Extract template ID from URL
                    match = re.search(r'/download/([a-zA-Z0-9-]+)', href)
                    if match:
                        template_id = match.group(1)
                        if template_id not in seen:
                            seen.add(template_id)
                            name = template_id.replace("-", " ").title()
                            template = LottieflowTemplate(
                                id=template_id,
                                name=name,
                                category=category,
                                page_url=f"{self.BASE_URL}/download/{template_id}",
                            )
                            templates.append(template)
                            if len(templates) >= limit:
                                break

            print(f"Found {len(templates)} templates in '{category}'")

        finally:
            await page.close()

        return templates

    async def download_category_bulk(
        self,
        category: str,
        limit: int = 50,
    ) -> list[LottieflowTemplate]:
        """
        Download all templates from a category by intercepting network requests.

        This approach captures all Lottie JSON files loaded during page navigation,
        which is more reliable than trying to extract individual URLs.

        Args:
            category: Category name
            limit: Maximum templates to download

        Returns:
            List of successfully downloaded templates
        """
        if category not in LOTTIEFLOW_CATEGORIES:
            print(f"Warning: '{category}' not in known categories")

        page = await self.context.new_page()
        captured_lotties = {}  # url -> json_data

        async def capture_response(response):
            """Capture Lottie JSON files from network responses."""
            url = response.url
            if (url.endswith('.json') and
                'website-files.com' in url and
                url not in captured_lotties):
                try:
                    data = await response.json()
                    # Only capture actual Lottie files (have animation data)
                    if 'layers' in data and 'fr' in data:
                        captured_lotties[url] = data
                except:
                    pass

        page.on('response', capture_response)
        templates = []

        try:
            # Load category page - this loads all animations in the slider
            url = f"{self.BASE_URL}/category/{category}"
            print(f"Loading category page: {url}")

            await page.goto(url, timeout=60000)
            await asyncio.sleep(5)  # Wait for animations to load

            # Scroll to trigger lazy loading
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(0.5)

            # Also scroll the horizontal slider if present
            slider = await page.query_selector('.horizontal-slide-wrapper, [class*="slider"]')
            if slider:
                for _ in range(10):
                    await page.evaluate('''(el) => {
                        el.scrollLeft += 300;
                    }''', slider)
                    await asyncio.sleep(0.3)

            print(f"Captured {len(captured_lotties)} unique Lottie files")

            # Filter out UI elements and keep only category-relevant content
            content_lotties = {}

            # UI element patterns that appear on every page (site chrome)
            ui_patterns = [
                'lightbulb', 'download.json', 'heart.json', 'biceps',
                'pacman', 'rocket', 'success-01', 'account-radio',
                'lottieflow-53786',  # Arrow animation used in navigation
                '96900',  # Another nav element
                'menu-nav-01-ff5151',  # Password check animation (appears everywhere)
            ]

            # Category keywords to help identify relevant files
            category_keywords = {
                'menu-nav': ['menu', 'nav', 'hamburger'],
                'loading': ['load', 'spinner', 'refresh', 'progress'],
                'checkbox': ['check', 'tick', 'toggle'],
                'arrow': ['arrow'],
                'play': ['play', 'pause', 'video'],
                'scroll-down': ['scroll', 'down'],
                'scroll-top': ['scroll', 'top', 'up'],
                'success': ['success', 'check', 'done', 'complete'],
                'attention': ['attention', 'alert', 'bell', 'notification'],
                'dropdown': ['dropdown', 'accordion', 'expand'],
                'search': ['search', 'magnif'],
                'radio': ['radio'],
                'cta': ['cta', 'button'],
                'social-media': ['social', 'facebook', 'twitter', 'instagram', 'linkedin'],
                'communication': ['message', 'chat', 'email', 'mail'],
                'countdown': ['countdown', 'timer', 'clock'],
                'ecommerce': ['cart', 'shop', 'bag', 'commerce'],
                'background': ['background', 'bg'],
                '404': ['404', 'error', 'not-found'],
                'media': ['media', 'volume', 'audio', 'music'],
            }

            keywords = category_keywords.get(category, [category.replace('-', '')])

            for url, data in captured_lotties.items():
                filename = url.split('/')[-1].lower()

                # Skip UI patterns
                is_ui = any(p in filename for p in ui_patterns)
                if is_ui:
                    continue

                # Prioritize files with category keywords
                has_keyword = any(kw in filename for kw in keywords)
                # Also include generic lottieflow files that might be category content
                is_lottieflow_content = 'lottieflow-' in filename and not is_ui

                if has_keyword or is_lottieflow_content:
                    content_lotties[url] = data

            # If we didn't find enough with keywords, include all non-UI files
            if len(content_lotties) < limit:
                for url, data in captured_lotties.items():
                    if url not in content_lotties:
                        filename = url.split('/')[-1].lower()
                        is_ui = any(p in filename for p in ui_patterns)
                        if not is_ui:
                            content_lotties[url] = data

            print(f"Filtered to {len(content_lotties)} content animations")

            # Save each captured Lottie
            category_dir = self.output_dir / f"lottieflow-{category}"
            category_dir.mkdir(parents=True, exist_ok=True)

            for i, (cdn_url, lottie_data) in enumerate(list(content_lotties.items())[:limit]):
                # Generate filename from CDN URL
                original_name = cdn_url.split('/')[-1]
                # Remove the hash prefix if present (e.g., "5e0df4d7c46d65cae16011ae_Menu5...")
                if '_' in original_name:
                    original_name = original_name.split('_', 1)[1]
                original_name = original_name.replace('.json', '')

                filename = self._sanitize_filename(original_name)
                save_path = category_dir / f"{filename}.json"

                # Extract metadata using shared utility
                meta = extract_lottie_metadata(lottie_data)

                # Save file using shared utility
                file_size = save_lottie_json(lottie_data, save_path)

                template = LottieflowTemplate(
                    id=filename,
                    name=original_name.replace('-', ' ').replace('_', ' ').title(),
                    category=category,
                    page_url=f"{self.BASE_URL}/category/{category}",
                    cdn_url=cdn_url,
                    width=meta["width"],
                    height=meta["height"],
                    fps=meta["fps"],
                    duration_seconds=meta["duration_seconds"],
                    file_size_bytes=file_size,
                    local_path=str(save_path.relative_to(self.output_dir)),
                    downloaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                templates.append(template)
                print(f"  [{i+1}/{min(len(content_lotties), limit)}] {template.name} ({file_size} bytes, {meta['duration_seconds']}s)")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await page.close()

        return templates

    async def download_category(
        self,
        category: str,
        limit: int = 50,
    ) -> list[LottieflowTemplate]:
        """
        Download templates from a category.

        Uses bulk download by intercepting network requests on the category page.

        Args:
            category: Category name
            limit: Maximum templates to download

        Returns:
            List of successfully downloaded templates
        """
        return await self.download_category_bulk(category, limit=limit)

    def _sanitize_filename(self, name: str) -> str:
        """Convert template name to safe filename."""
        return sanitize_filename(name)

    def create_catalog(self, templates: list[LottieflowTemplate]) -> dict:
        """
        Create a catalog JSON from downloaded templates.

        Args:
            templates: List of downloaded templates

        Returns:
            Catalog dictionary
        """
        catalog = {
            "source": "finsweet.com/lottieflow",
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
                "page_url": template.page_url,
                "cdn_url": template.cdn_url,
                "local_path": template.local_path,
                "width": template.width,
                "height": template.height,
                "fps": template.fps,
                "duration_seconds": template.duration_seconds,
                "file_size_bytes": template.file_size_bytes,
                "downloaded_at": template.downloaded_at,
            })

        # Save catalog
        catalog_path = self.output_dir / "lottieflow-catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)

        print(f"\nCatalog saved: {catalog_path}")
        return catalog


async def download_essential_lottieflow_templates():
    """Download a curated set of essential Lottieflow templates."""

    # Categories most useful for video production
    essential_categories = [
        ("menu-nav", 5),      # Hamburger menus, nav toggles
        ("arrow", 5),         # Directional arrows
        ("checkbox", 3),      # Check animations
        ("loading", 5),       # Loading spinners
        ("play", 3),          # Play/pause buttons
        ("scroll-down", 3),   # Scroll indicators
        ("success", 3),       # Success checkmarks
        ("attention", 3),     # Attention grabbers
    ]

    all_templates = []

    async with LottieflowDownloader(headless=True, delay_between_downloads=1.5) as downloader:
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

    parser = argparse.ArgumentParser(description="Download Lottie animations from Lottieflow")
    parser.add_argument("--category", type=str, help="Category to download from")
    parser.add_argument("--limit", type=int, default=10, help="Max templates per category")
    parser.add_argument("--essential", action="store_true", help="Download essential templates")
    parser.add_argument("--list-categories", action="store_true", help="List available categories")
    parser.add_argument("--output", type=str, default="assets/common/lottie", help="Output directory")
    parser.add_argument("--visible", action="store_true", help="Show browser window")

    args = parser.parse_args()

    if args.list_categories:
        print("Available Lottieflow categories:")
        for cat in LOTTIEFLOW_CATEGORIES:
            print(f"  - {cat}")
    elif args.essential:
        asyncio.run(download_essential_lottieflow_templates())
    elif args.category:
        async def run():
            async with LottieflowDownloader(
                output_dir=args.output,
                headless=not args.visible,
            ) as downloader:
                results = await downloader.download_category(args.category, limit=args.limit)
                if results:
                    downloader.create_catalog(results)
        asyncio.run(run())
    else:
        parser.print_help()
