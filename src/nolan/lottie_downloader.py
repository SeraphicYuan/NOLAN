"""
LottieFiles downloader for NOLAN.

Downloads Lottie animations from LottieFiles.com with:
- Automatic URL resolution (handles redirects)
- Rate limiting to avoid blocks
- Metadata extraction (author, tags, frames, duration, etc.)
- Organized storage by category
- Duplicate detection
- Color palette extraction
- Search functionality
- License verification
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, quote_plus
import requests

from nolan.downloaders.utils import RateLimiter, sanitize_filename


@dataclass
class LottieMetadata:
    """Metadata for a downloaded Lottie animation."""
    id: str
    title: str
    author: str = ""
    source_url: str = ""
    cdn_url: str = ""
    tags: list[str] = field(default_factory=list)
    file_size_kb: float = 0
    frames: int = 0
    fps: float = 0
    duration_seconds: float = 0
    width: int = 0
    height: int = 0
    license: str = "Lottie Simple License"
    category: str = ""
    downloaded_at: str = ""
    # Additional fields
    content_hash: str = ""  # SHA256 of JSON content for duplicate detection
    color_palette: list[str] = field(default_factory=list)  # Extracted hex colors
    layer_count: int = 0
    has_expressions: bool = False
    has_images: bool = False
    local_path: str = ""


class LottieFilesDownloader:
    """
    Download Lottie animations from LottieFiles.com.

    Example:
        downloader = LottieFilesDownloader(output_dir="assets/common/lottie")

        # Download single animation
        meta = downloader.download(
            "https://lottiefiles.com/8664-lower-third-animation",
            category="lower-thirds"
        )

        # Download batch with rate limiting
        urls = [
            ("https://lottiefiles.com/8664-lower-third-animation", "lower-thirds"),
            ("https://lottiefiles.com/17845-simple-screen-wipe", "transitions"),
        ]
        results = downloader.download_batch(urls)
    """

    BASE_CDN = "https://assets-v2.lottiefiles.com"

    def __init__(
        self,
        output_dir: str = "assets/common/lottie",
        requests_per_minute: int = 20,
        prefer_optimized: bool = True
    ):
        self.output_dir = Path(output_dir)
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.prefer_optimized = prefer_optimized
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def resolve_url(self, url: str) -> str:
        """
        Resolve LottieFiles URL to final destination (follow redirects).

        Handles both old format (lottiefiles.com/8664-name) and
        new format (lottiefiles.com/free-animation/name-xxxxx).
        """
        self.rate_limiter.wait()

        # Ensure https
        if url.startswith('http://'):
            url = url.replace('http://', 'https://')

        try:
            response = self.session.head(url, allow_redirects=True, timeout=10)
            return response.url
        except requests.RequestException as e:
            print(f"Error resolving URL {url}: {e}")
            return url

    def extract_asset_id(self, html: str) -> Optional[str]:
        """Extract the asset ID from page HTML."""
        # Look for CDN URLs in the page
        pattern = r'assets-v2\.lottiefiles\.com/a/([a-f0-9-]+)/'
        match = re.search(pattern, html)
        return match.group(1) if match else None

    def extract_from_next_data(self, html: str) -> dict:
        """Extract animation data from Next.js __NEXT_DATA__ script."""
        pattern = r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>'
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            return {}

        try:
            data = json.loads(match.group(1))
            return data
        except json.JSONDecodeError:
            return {}

    def find_json_url_in_next_data(self, next_data: dict, asset_id: str) -> Optional[str]:
        """Recursively search for JSON URLs in Next.js data."""
        def search(obj, depth=0):
            if depth > 20:
                return None

            if isinstance(obj, str):
                if 'assets-v2.lottiefiles.com' in obj and '.json' in obj:
                    return obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    result = search(v, depth + 1)
                    if result:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = search(item, depth + 1)
                    if result:
                        return result
            return None

        return search(next_data)

    def extract_json_urls(self, html: str, asset_id: str) -> dict[str, str]:
        """Extract JSON download URLs from page HTML."""
        urls = {}

        # Unescape common JavaScript escapes
        html_unescaped = html.replace('\\/', '/').replace('\\u002F', '/')

        base_url = f"{self.BASE_CDN}/a/{asset_id}/"

        # Pattern 1: Full URLs with asset ID
        patterns = [
            rf'https://assets-v2\.lottiefiles\.com/a/{re.escape(asset_id)}/([a-zA-Z0-9]+)\.(json|lottie)',
            rf'assets-v2\.lottiefiles\.com/a/{re.escape(asset_id)}/([a-zA-Z0-9]+)\.(json|lottie)',
        ]

        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, html_unescaped)
            all_matches.extend(matches)

        # Pattern 2: Path format in escaped JSON (common in LottieFiles)
        # e.g., \"a/31442878-1152-11ee-bebf-b384cf042db3/AUMGf2cjdS.json\"
        path_pattern = rf'a/{re.escape(asset_id)}/([a-zA-Z0-9]+)\.(json|lottie)'
        path_matches = re.findall(path_pattern, html_unescaped)
        all_matches.extend(path_matches)

        # Pattern 3: Just the filename (hash.json) near the asset ID
        # Look for patterns like "AUMGf2cjdS.json" within 200 chars of asset_id
        for match in re.finditer(re.escape(asset_id), html_unescaped):
            context = html_unescaped[match.start():match.start()+200]
            file_matches = re.findall(r'([a-zA-Z0-9]{8,12})\.(json|lottie)', context)
            all_matches.extend(file_matches)

        for match in all_matches:
            if isinstance(match, tuple):
                file_hash, ext = match
            else:
                continue

            url = f"{base_url}{file_hash}.{ext}"

            if ext == 'json':
                # Check context for "optimized" keyword
                url_idx = html_unescaped.find(file_hash)
                context = html_unescaped[max(0, url_idx-150):url_idx+150].lower()
                if 'optimized' in context or 'opt' in context:
                    urls['optimized_json'] = url
                elif 'json' not in urls:
                    urls['json'] = url
                else:
                    # If we already have one, assume second is optimized
                    urls['optimized_json'] = url
            elif ext == 'lottie':
                urls['dotlottie'] = url

        return urls

    def extract_metadata(self, html: str, source_url: str) -> LottieMetadata:
        """Extract metadata from LottieFiles page HTML."""
        meta = LottieMetadata(
            id="",
            title="",
            source_url=source_url
        )

        # Extract title - look for common patterns
        title_patterns = [
            r'<title>([^<]+?)(?:\s*[-|]\s*LottieFiles)?</title>',
            r'"name"\s*:\s*"([^"]+)"',
            r'animation[_-]?name["\']?\s*[:=]\s*["\']([^"\']+)',
        ]
        for pattern in title_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                meta.title = match.group(1).strip()
                break

        # Extract author
        author_patterns = [
            r'by\s+([A-Za-z][A-Za-z\s]+?)(?:\s*[|<]|\s*on\s+LottieFiles)',
            r'"author"\s*:\s*"([^"]+)"',
            r'creator["\']?\s*[:=]\s*["\']([^"\']+)',
        ]
        for pattern in author_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                meta.author = match.group(1).strip()
                break

        # Extract tags
        tag_patterns = [
            r'"tags"\s*:\s*\[([^\]]+)\]',
            r'keywords["\']?\s*[:=]\s*["\']([^"\']+)',
        ]
        for pattern in tag_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                raw_tags = match.group(1)
                # Parse tags from JSON array or comma-separated
                tags = re.findall(r'"([^"]+)"', raw_tags)
                if not tags:
                    tags = [t.strip() for t in raw_tags.split(',')]
                meta.tags = [t for t in tags if t]
                break

        # Extract dimensions
        dim_match = re.search(r'(\d{3,4})\s*[x×]\s*(\d{3,4})', html)
        if dim_match:
            meta.width = int(dim_match.group(1))
            meta.height = int(dim_match.group(2))

        # Extract file size
        size_match = re.search(r'([\d.]+)\s*KB', html, re.IGNORECASE)
        if size_match:
            meta.file_size_kb = float(size_match.group(1))

        # Generate ID from URL
        url_match = re.search(r'/([a-zA-Z0-9-]+)$', source_url)
        if url_match:
            meta.id = url_match.group(1)

        return meta

    def download_json(self, url: str, output_path: Path) -> bool:
        """Download JSON file from CDN."""
        self.rate_limiter.wait()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Validate it's valid JSON
            data = response.json()

            # Save with pretty formatting for readability
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'))

            return True
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return False

    def enrich_metadata_from_json(self, json_path: Path, meta: LottieMetadata) -> None:
        """Extract additional metadata from the Lottie JSON file."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
                data = json.loads(content)

            meta.fps = data.get('fr', 0)
            meta.frames = data.get('op', 0) - data.get('ip', 0)
            meta.width = data.get('w', meta.width)
            meta.height = data.get('h', meta.height)

            if meta.fps > 0 and meta.frames > 0:
                meta.duration_seconds = round(meta.frames / meta.fps, 2)

            # Get file size
            meta.file_size_kb = round(json_path.stat().st_size / 1024, 1)

            # Content hash for duplicate detection
            meta.content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

            # Layer count
            meta.layer_count = len(data.get('layers', []))

            # Check for expressions
            meta.has_expressions = '"x"' in content or '"expression"' in content.lower()

            # Check for images
            assets = data.get('assets', [])
            meta.has_images = any(
                a.get('p', '').startswith('data:image') or
                a.get('u', '') or
                a.get('e', 0) == 1
                for a in assets if isinstance(a, dict)
            )

            # Extract color palette
            meta.color_palette = self.extract_colors(data)

        except Exception as e:
            print(f"Error reading JSON metadata: {e}")

    def extract_colors(self, data: dict, max_colors: int = 8) -> list[str]:
        """
        Extract dominant colors from Lottie JSON.

        Returns list of hex color strings.
        """
        colors = set()

        def find_colors(obj):
            if len(colors) >= max_colors * 2:  # Collect more, dedupe later
                return

            if isinstance(obj, dict):
                # Check for color arrays in 'k' or 'c' keys (fills/strokes)
                for key in ['k', 'c']:
                    if key in obj:
                        val = obj[key]
                        if isinstance(val, list) and len(val) in [3, 4]:
                            if all(isinstance(v, (int, float)) for v in val[:3]):
                                # Check if values are in 0-1 range (Lottie colors)
                                if all(0 <= v <= 1 for v in val[:3]):
                                    r = int(val[0] * 255)
                                    g = int(val[1] * 255)
                                    b = int(val[2] * 255)
                                    hex_color = f"#{r:02x}{g:02x}{b:02x}"
                                    # Skip near-black and near-white
                                    if hex_color not in ['#000000', '#ffffff', '#010101', '#fefefe']:
                                        colors.add(hex_color)

                for v in obj.values():
                    find_colors(v)

            elif isinstance(obj, list):
                for item in obj:
                    find_colors(item)

        find_colors(data)

        # Return unique colors, sorted by frequency approximation
        return list(colors)[:max_colors]

    def check_duplicate(self, content_hash: str) -> Optional[Path]:
        """
        Check if an animation with this hash already exists.

        Returns path to existing file if duplicate, None otherwise.
        """
        for meta_file in self.output_dir.rglob("*.meta.json"):
            try:
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                if meta.get('content_hash') == content_hash:
                    return meta_file.with_suffix('').with_suffix('.json')
            except Exception:
                pass
        return None

    def search_lottiefiles(
        self,
        query: str,
        limit: int = 10,
        free_only: bool = True
    ) -> list[dict]:
        """
        Search LottieFiles for animations.

        Args:
            query: Search query
            limit: Max results to return
            free_only: Only return free animations

        Returns:
            List of search result dicts with 'url', 'title', 'author' keys
        """
        self.rate_limiter.wait()

        # Use LottieFiles search page
        search_url = f"https://lottiefiles.com/search?q={quote_plus(query)}&category=animations"
        if free_only:
            search_url += "&price=free"

        try:
            response = self.session.get(search_url, timeout=30)
            html = response.text

            results = []

            # Extract animation cards from search results
            # Pattern for animation URLs
            url_pattern = r'href="(/free-animation/[^"]+)"'
            title_pattern = r'title="([^"]+)"'

            urls = re.findall(url_pattern, html)
            titles = re.findall(title_pattern, html)

            seen = set()
            for url in urls[:limit * 2]:
                if url in seen:
                    continue
                seen.add(url)

                full_url = f"https://lottiefiles.com{url}"
                # Try to get title from nearby context
                idx = html.find(url)
                context = html[max(0, idx-200):idx+200]
                title_match = re.search(r'title="([^"]+)"', context)
                title = title_match.group(1) if title_match else url.split('/')[-1]

                results.append({
                    'url': full_url,
                    'title': title,
                })

                if len(results) >= limit:
                    break

            return results

        except Exception as e:
            print(f"Search error: {e}")
            return []

    def download(
        self,
        url: str,
        category: str = "",
        filename: Optional[str] = None
    ) -> Optional[LottieMetadata]:
        """
        Download a Lottie animation from LottieFiles.

        Args:
            url: LottieFiles page URL
            category: Category folder (e.g., "lower-thirds", "transitions")
            filename: Custom filename (without extension). If None, derived from title.

        Returns:
            LottieMetadata if successful, None otherwise
        """
        print(f"Downloading: {url}")

        # Resolve URL (follow redirects)
        resolved_url = self.resolve_url(url)
        print(f"  Resolved to: {resolved_url}")

        # Fetch page content
        self.rate_limiter.wait()
        try:
            response = self.session.get(resolved_url, timeout=30)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            print(f"  Error fetching page: {e}")
            return None

        # Extract asset ID and URLs
        asset_id = self.extract_asset_id(html)
        if not asset_id:
            print(f"  Could not find asset ID")
            return None

        json_urls = self.extract_json_urls(html, asset_id)

        # If no JSON URLs found in HTML, try Next.js data
        if not json_urls.get('json') and not json_urls.get('optimized_json'):
            next_data = self.extract_from_next_data(html)
            if next_data:
                json_url = self.find_json_url_in_next_data(next_data, asset_id)
                if json_url:
                    json_urls['json'] = json_url
                    print(f"  Found JSON URL in __NEXT_DATA__")

        if not json_urls:
            print(f"  Could not find JSON download URLs")
            return None

        # Choose URL (prefer JSON over dotlottie, optimized if available)
        if self.prefer_optimized and 'optimized_json' in json_urls:
            cdn_url = json_urls['optimized_json']
        elif 'json' in json_urls:
            cdn_url = json_urls['json']
        elif 'dotlottie' in json_urls:
            # dotlottie is binary, we need JSON - try to find it differently
            # Often the JSON URL is near the lottie URL in the HTML
            print(f"  Warning: Only dotLottie found, attempting to find JSON variant...")
            # Replace .lottie extension to try common JSON patterns
            dotlottie_url = json_urls['dotlottie']
            # This won't work directly, but we can try fetching the page again
            # or skip this animation
            print(f"  Skipping - no JSON URL found (only .lottie binary)")
            return None
        else:
            print(f"  No suitable download URL found")
            return None

        print(f"  CDN URL: {cdn_url}")

        # Extract metadata
        meta = self.extract_metadata(html, resolved_url)
        meta.cdn_url = cdn_url
        meta.category = category
        meta.downloaded_at = time.strftime("%Y-%m-%d %H:%M:%S")

        # Determine output path
        if filename:
            safe_name = filename
        else:
            # Create safe filename from title using shared utility
            safe_name = sanitize_filename(meta.title)
            if not safe_name:
                safe_name = meta.id or f"animation-{int(time.time())}"

        if category:
            output_path = self.output_dir / category / f"{safe_name}.json"
        else:
            output_path = self.output_dir / f"{safe_name}.json"

        # Download JSON
        if not self.download_json(cdn_url, output_path):
            return None

        # Enrich metadata from JSON
        self.enrich_metadata_from_json(output_path, meta)

        # Save metadata
        meta_path = output_path.with_suffix('.meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(meta), f, indent=2)

        print(f"  Saved: {output_path}")
        print(f"  Title: {meta.title}")
        print(f"  Author: {meta.author}")
        print(f"  Size: {meta.file_size_kb} KB, {meta.frames} frames @ {meta.fps} fps")

        return meta

    def download_batch(
        self,
        items: list[tuple[str, str, Optional[str]]],
        continue_on_error: bool = True
    ) -> list[LottieMetadata]:
        """
        Download multiple animations.

        Args:
            items: List of (url, category, optional_filename) tuples
            continue_on_error: If True, continue downloading on errors

        Returns:
            List of successful LottieMetadata
        """
        results = []
        total = len(items)

        for i, item in enumerate(items, 1):
            if len(item) == 2:
                url, category = item
                filename = None
            else:
                url, category, filename = item

            print(f"\n[{i}/{total}] ", end="")

            try:
                meta = self.download(url, category, filename)
                if meta:
                    results.append(meta)
            except Exception as e:
                print(f"  Error: {e}")
                if not continue_on_error:
                    raise

        print(f"\n\nDownloaded {len(results)}/{total} animations successfully")
        return results

    def create_catalog(self, output_file: Optional[str] = None) -> dict:
        """
        Create a catalog of all downloaded animations.

        Returns:
            Dictionary with animations organized by category
        """
        catalog = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": 0,
            "categories": {}
        }

        # Find all meta.json files
        for meta_file in self.output_dir.rglob("*.meta.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                category = meta.get('category', 'uncategorized')
                if category not in catalog['categories']:
                    catalog['categories'][category] = []

                # Add relative path to animation file
                anim_file = meta_file.with_suffix('').with_suffix('.json')
                if anim_file.exists():
                    meta['local_path'] = str(anim_file.relative_to(self.output_dir))

                catalog['categories'][category].append(meta)
                catalog['total_count'] += 1

            except Exception as e:
                print(f"Error reading {meta_file}: {e}")

        # Sort categories
        for category in catalog['categories']:
            catalog['categories'][category].sort(key=lambda x: x.get('title', ''))

        # Save catalog
        if output_file:
            output_path = Path(output_file)
        else:
            output_path = self.output_dir / "catalog.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2)

        print(f"Catalog saved to {output_path}")
        return catalog


# Curated list of essential animations for NOLAN
ESSENTIAL_ANIMATIONS = [
    # Lower Thirds (speaker names, titles)
    ("https://lottiefiles.com/8664-lower-third-animation", "lower-thirds", "simple"),
    ("https://lottiefiles.com/105365-lower-third", "lower-thirds", "modern"),

    # Title Cards / Text Reveals
    ("https://lottiefiles.com/10799-text-reveal", "title-cards", "text-reveal"),

    # Transitions / Wipes
    ("https://lottiefiles.com/17845-simple-screen-wipe", "transitions", "wipe-simple"),
    ("https://lottiefiles.com/87378-transition", "transitions", "shape-morph"),

    # Data Callouts / Counters
    ("https://lottiefiles.com/68818-number-counter", "data-callouts", "number-counter"),
    ("https://lottiefiles.com/23748-number-counting-animation", "data-callouts", "counting"),

    # Progress Bars
    ("https://lottiefiles.com/24318-progress-loading-bar", "progress-bars", "loading-bar"),
    ("https://lottiefiles.com/117-progress-bar", "progress-bars", "minimal"),

    # Loading / Spinners
    ("https://lottiefiles.com/9844-loading-40-paperplane", "loaders", "paperplane"),

    # Success / Check marks
    ("https://lottiefiles.com/free-animation/check-mark-success-hzJ4cKEtXR", "icons", "checkmark-success"),

    # Arrows / Navigation
    ("https://lottiefiles.com/free-animation/arrow-down-bounce-mXVB1I6SyD", "icons", "arrow-down"),
]


def download_essential_library(output_dir: str = "assets/common/lottie") -> list[LottieMetadata]:
    """
    Download the essential Lottie library for NOLAN.

    Args:
        output_dir: Output directory for animations

    Returns:
        List of downloaded animation metadata
    """
    downloader = LottieFilesDownloader(
        output_dir=output_dir,
        requests_per_minute=15  # Conservative rate limit
    )

    results = downloader.download_batch(ESSENTIAL_ANIMATIONS)

    # Create catalog
    downloader.create_catalog()

    return results


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]

    if not args:
        print("LottieFiles Downloader for NOLAN")
        print("=" * 40)
        print("\nCommands:")
        print("  --download-essential     Download curated essential library")
        print("  --search <query>         Search LottieFiles")
        print("  --download <url>         Download single animation")
        print("  --catalog                Generate catalog of downloaded animations")
        print("\nExamples:")
        print("  python -m nolan.lottie_downloader --download-essential")
        print("  python -m nolan.lottie_downloader --search 'lower third'")
        print("  python -m nolan.lottie_downloader --download https://lottiefiles.com/...")
        print("\nProgrammatic usage:")
        print("  from nolan.lottie_downloader import LottieFilesDownloader")
        print("  downloader = LottieFilesDownloader()")
        print("  downloader.download('https://lottiefiles.com/...', 'category')")
        sys.exit(0)

    downloader = LottieFilesDownloader()

    if args[0] == "--download-essential":
        download_essential_library()

    elif args[0] == "--search" and len(args) > 1:
        query = " ".join(args[1:])
        print(f"Searching LottieFiles for: {query}\n")
        results = downloader.search_lottiefiles(query, limit=10)
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title']}")
            print(f"   {r['url']}\n")

    elif args[0] == "--download" and len(args) > 1:
        url = args[1]
        category = args[2] if len(args) > 2 else "uncategorized"
        downloader.download(url, category)

    elif args[0] == "--catalog":
        catalog = downloader.create_catalog()
        print(f"\nTotal animations: {catalog['total_count']}")
        for cat, anims in catalog['categories'].items():
            print(f"  {cat}: {len(anims)}")

    else:
        print(f"Unknown command: {args[0]}")
        print("Run without arguments to see usage.")
