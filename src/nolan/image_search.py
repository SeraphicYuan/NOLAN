"""Image search providers for NOLAN."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx


@dataclass
class ImageSearchResult:
    """Unified image search result."""
    url: str
    thumbnail_url: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None  # Provider name
    source_url: Optional[str] = None  # Original page URL
    width: Optional[int] = None
    height: Optional[int] = None
    photographer: Optional[str] = None
    license: Optional[str] = None
    score: Optional[float] = None  # Vision model relevance score (0-10)
    score_reason: Optional[str] = None  # Explanation for the score
    scored_by: Optional[str] = None  # Which vision model scored this
    quality_score: Optional[float] = None  # Image quality score (0-10)
    quality_reason: Optional[str] = None  # Explanation for quality score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def combined_score(self) -> float:
        """Get combined score (relevance + quality tiebreaker).

        Returns relevance score + (quality_score * 0.01) for tiebreaking.
        """
        relevance = self.score or 0.0
        quality = (self.quality_score or 0.0) * 0.01  # Quality as tiebreaker
        return relevance + quality


class ImageProvider(ABC):
    """Base class for image search providers."""

    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of ImageSearchResult objects.
        """
        pass

    def is_available(self) -> bool:
        """Check if provider is available (has required credentials)."""
        return True


class DDGSProvider(ImageProvider):
    """DuckDuckGo image search provider using ddgs."""

    name = "ddgs"

    def __init__(self):
        """Initialize DDGS provider."""
        try:
            from ddgs import DDGS
            self._ddgs_class = DDGS
            self._available = True
        except ImportError:
            # Fallback to old package name
            try:
                from duckduckgo_search import DDGS
                self._ddgs_class = DDGS
                self._available = True
            except ImportError:
                self._available = False

    def is_available(self) -> bool:
        """Check if duckduckgo-search is installed."""
        return self._available

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search DuckDuckGo for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self._available:
            raise RuntimeError("duckduckgo-search package not installed")

        results = []
        with self._ddgs_class() as ddgs:
            for r in ddgs.images(query, max_results=max_results):
                results.append(ImageSearchResult(
                    url=r.get("image", ""),
                    thumbnail_url=r.get("thumbnail", ""),
                    title=r.get("title", ""),
                    source=self.name,
                    source_url=r.get("url", ""),
                    width=r.get("width"),
                    height=r.get("height"),
                ))
        return results


class PexelsProvider(ImageProvider):
    """Pexels API image search provider."""

    name = "pexels"
    BASE_URL = "https://api.pexels.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Pexels provider.

        Args:
            api_key: Pexels API key. Get one at https://www.pexels.com/api/
        """
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Pexels for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self.api_key:
            raise RuntimeError("Pexels API key not configured")

        headers = {"Authorization": self.api_key}
        params = {"query": query, "per_page": min(max_results, 80)}

        with httpx.Client() as client:
            response = client.get(
                f"{self.BASE_URL}/search",
                headers=headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for photo in data.get("photos", []):
            results.append(ImageSearchResult(
                url=photo.get("src", {}).get("original", ""),
                thumbnail_url=photo.get("src", {}).get("medium", ""),
                title=photo.get("alt", ""),
                source=self.name,
                source_url=photo.get("url", ""),
                width=photo.get("width"),
                height=photo.get("height"),
                photographer=photo.get("photographer", ""),
                license="Pexels License (free for commercial use)",
            ))
        return results


class PixabayProvider(ImageProvider):
    """Pixabay API image search provider."""

    name = "pixabay"
    BASE_URL = "https://pixabay.com/api/"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Pixabay provider.

        Args:
            api_key: Pixabay API key. Get one at https://pixabay.com/api/docs/
        """
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Pixabay for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self.api_key:
            raise RuntimeError("Pixabay API key not configured")

        params = {
            "key": self.api_key,
            "q": query,
            "per_page": min(max_results, 200),
            "image_type": "photo",
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for hit in data.get("hits", []):
            results.append(ImageSearchResult(
                url=hit.get("largeImageURL", ""),
                thumbnail_url=hit.get("previewURL", ""),
                title=hit.get("tags", ""),
                source=self.name,
                source_url=hit.get("pageURL", ""),
                width=hit.get("imageWidth"),
                height=hit.get("imageHeight"),
                photographer=hit.get("user", ""),
                license="Pixabay License (free for commercial use)",
            ))
        return results


class WikimediaCommonsProvider(ImageProvider):
    """Wikimedia Commons image search provider."""

    name = "wikimedia"
    BASE_URL = "https://commons.wikimedia.org/w/api.php"

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Wikimedia Commons for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        # Search for files matching query
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",  # File namespace
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": min(max_results, 50),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 800,  # Get thumbnail
        }

        headers = {
            "User-Agent": "NOLAN-VideoEssayTool/1.0 (https://github.com/nolan; contact@example.com)"
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            if page_id == "-1":
                continue

            imageinfo = page.get("imageinfo", [{}])[0]
            extmeta = imageinfo.get("extmetadata", {})

            # Get artist/photographer
            artist = extmeta.get("Artist", {}).get("value", "")
            # Strip HTML tags from artist
            if "<" in artist:
                import re
                artist = re.sub(r'<[^>]+>', '', artist).strip()

            # Get license
            license_info = extmeta.get("LicenseShortName", {}).get("value", "")

            results.append(ImageSearchResult(
                url=imageinfo.get("url", ""),
                thumbnail_url=imageinfo.get("thumburl", ""),
                title=page.get("title", "").replace("File:", ""),
                source=self.name,
                source_url=imageinfo.get("descriptionurl", ""),
                width=imageinfo.get("width"),
                height=imageinfo.get("height"),
                photographer=artist,
                license=license_info or "Wikimedia Commons",
            ))

        return results


class SmithsonianProvider(ImageProvider):
    """Smithsonian Open Access image search provider."""

    name = "smithsonian"
    BASE_URL = "https://api.si.edu/openaccess/api/v1.0/search"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Smithsonian provider.

        Args:
            api_key: Smithsonian API key from api.data.gov
        """
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Smithsonian Open Access for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self.api_key:
            raise RuntimeError("Smithsonian API key not configured")

        params = {
            "api_key": self.api_key,
            "q": query,
            "rows": min(max_results, 100),
            "online_media_type": "Images",
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        rows = data.get("response", {}).get("rows", [])

        for row in rows:
            content = row.get("content", {})
            desc = content.get("descriptiveNonRepeating", {})
            indexed = content.get("indexedStructured", {})

            # Get image URL from online_media
            online_media = desc.get("online_media", {}).get("media", [])
            if not online_media:
                continue

            media = online_media[0]
            image_url = media.get("content", "")
            thumbnail_url = media.get("thumbnail", "")

            # Get dimensions if available
            width = None
            height = None
            resources = media.get("resources", [])
            if resources:
                # Get largest image
                for res in resources:
                    if res.get("width"):
                        width = res.get("width")
                        height = res.get("height")

            results.append(ImageSearchResult(
                url=image_url,
                thumbnail_url=thumbnail_url,
                title=desc.get("title", {}).get("content", ""),
                source=self.name,
                source_url=desc.get("record_link", ""),
                width=width,
                height=height,
                photographer=indexed.get("name", [""])[0] if indexed.get("name") else "",
                license="CC0 (Public Domain)",
            ))

        return results


class LibraryOfCongressProvider(ImageProvider):
    """Library of Congress image search provider."""

    name = "loc"
    BASE_URL = "https://www.loc.gov/pictures/search/"

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Library of Congress Prints & Photographs for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        params = {
            "q": query,
            "fo": "json",
            "c": min(max_results, 100),
            "sp": 1,
        }

        headers = {
            "User-Agent": "NOLAN-VideoEssayTool/1.0"
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        items = data.get("results", [])

        for item in items:
            # Get image URLs
            image_info = item.get("image", {})
            # LoC provides multiple sizes: thumb, small, medium, large, full
            image_url = image_info.get("full", "") or image_info.get("large", "") or image_info.get("medium", "")
            thumbnail_url = image_info.get("thumb", "") or image_info.get("small", "")

            # Parse dimensions from image URL if available
            width = None
            height = None

            results.append(ImageSearchResult(
                url=image_url,
                thumbnail_url=thumbnail_url,
                title=item.get("title", ""),
                source=self.name,
                source_url=item.get("links", {}).get("item", ""),
                width=width,
                height=height,
                photographer=item.get("creator", ""),
                license="Public Domain (Library of Congress)",
            ))

        return results


class ImageSearchClient:
    """Client for searching images across multiple providers."""

    def __init__(
        self,
        pexels_api_key: Optional[str] = None,
        pixabay_api_key: Optional[str] = None,
        smithsonian_api_key: Optional[str] = None,
    ):
        """Initialize image search client.

        Args:
            pexels_api_key: Pexels API key.
            pixabay_api_key: Pixabay API key.
            smithsonian_api_key: Smithsonian API key from api.data.gov.
        """
        self.providers: Dict[str, ImageProvider] = {
            "ddgs": DDGSProvider(),
            "pexels": PexelsProvider(api_key=pexels_api_key),
            "pixabay": PixabayProvider(api_key=pixabay_api_key),
            "wikimedia": WikimediaCommonsProvider(),
            "smithsonian": SmithsonianProvider(api_key=smithsonian_api_key),
            "loc": LibraryOfCongressProvider(),
        }

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return [name for name, p in self.providers.items() if p.is_available()]

    def search(
        self,
        query: str,
        source: str = "ddgs",
        max_results: int = 10
    ) -> List[ImageSearchResult]:
        """Search for images using specified provider.

        Args:
            query: Search query string.
            source: Provider name ('ddgs', 'pexels', 'pixabay', 'all').
            max_results: Maximum results per provider.

        Returns:
            List of ImageSearchResult objects.
        """
        if source == "all":
            results = []
            for name, provider in self.providers.items():
                if provider.is_available():
                    try:
                        results.extend(provider.search(query, max_results))
                    except Exception as e:
                        print(f"Warning: {name} search failed: {e}")
            return results

        if source not in self.providers:
            raise ValueError(f"Unknown provider: {source}. Available: {list(self.providers.keys())}")

        provider = self.providers[source]
        if not provider.is_available():
            raise RuntimeError(f"Provider '{source}' is not available (missing API key or package)")

        return provider.search(query, max_results)

    def search_to_json(
        self,
        query: str,
        output_path: Path,
        source: str = "ddgs",
        max_results: int = 10
    ) -> List[ImageSearchResult]:
        """Search and save results to JSON file.

        Args:
            query: Search query string.
            output_path: Path to save JSON results.
            source: Provider name.
            max_results: Maximum results per provider.

        Returns:
            List of ImageSearchResult objects.
        """
        results = self.search(query, source, max_results)

        output_data = {
            "query": query,
            "source": source,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        return results

    def download_image(
        self,
        result: ImageSearchResult,
        output_path: Path,
        prefer_large: bool = True,
        timeout: float = 30.0
    ) -> Optional[Path]:
        """Download an image to disk.

        Args:
            result: ImageSearchResult to download.
            output_path: Path to save the image (with extension).
            prefer_large: If True, download full-size image; else thumbnail.
            timeout: Request timeout in seconds.

        Returns:
            Path to downloaded file, or None if failed.
        """
        url = result.url if prefer_large else (result.thumbnail_url or result.url)

        # Browser-like headers to avoid blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }

        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                response = client.get(url)
                response.raise_for_status()

                # Determine file extension from content-type or URL
                content_type = response.headers.get("content-type", "")
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                elif "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "gif" in content_type:
                    ext = ".gif"
                else:
                    # Try to get from URL
                    url_lower = url.lower()
                    if ".png" in url_lower:
                        ext = ".png"
                    elif ".webp" in url_lower:
                        ext = ".webp"
                    elif ".gif" in url_lower:
                        ext = ".gif"
                    else:
                        ext = ".jpg"  # Default

                # Ensure output path has correct extension
                if not output_path.suffix:
                    output_path = output_path.with_suffix(ext)

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)

                return output_path

        except Exception as e:
            # Try fallback URL if main fails
            if prefer_large and result.thumbnail_url and result.thumbnail_url != url:
                try:
                    with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                        response = client.get(result.thumbnail_url)
                        response.raise_for_status()

                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        if not output_path.suffix:
                            output_path = output_path.with_suffix(".jpg")
                        output_path.write_bytes(response.content)
                        return output_path
                except Exception:
                    pass
            return None


class ImageScorer:
    """Score images using vision models for relevance to query."""

    def __init__(self, vision_provider: str = "gemini", vision_config: Optional[Dict] = None):
        """Initialize image scorer.

        Args:
            vision_provider: Vision provider to use ('gemini' or 'ollama').
            vision_config: Configuration for vision provider.
        """
        self.vision_provider = vision_provider
        self.vision_config = vision_config or {}

    def _download_image(self, url: str, timeout: float = 10.0) -> Optional[bytes]:
        """Download image from URL.

        Args:
            url: Image URL.
            timeout: Request timeout.

        Returns:
            Image bytes or None if failed.
        """
        # Use browser-like headers to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }
        try:
            with httpx.Client(follow_redirects=True, headers=headers) as client:
                response = client.get(url, timeout=timeout)
                response.raise_for_status()
                return response.content
        except Exception:
            return None

    def _score_with_gemini(
        self,
        image_data: bytes,
        query: str,
        context: Optional[str] = None
    ) -> tuple[float, str]:
        """Score image using Gemini vision model.

        Args:
            image_data: Image bytes.
            query: Search query.
            context: Additional context for scoring.

        Returns:
            Tuple of (score, reason).
        """
        import google.generativeai as genai
        from PIL import Image
        import io

        api_key = self.vision_config.get("api_key")
        if not api_key:
            raise RuntimeError("Gemini API key not configured")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Load image
        image = Image.open(io.BytesIO(image_data))

        context_text = f"\nContext: {context}" if context else ""
        prompt = f"""Score this image for relevance to the search query.

Search query: "{query}"{context_text}

Rate the image from 0-10 where:
- 10 = Perfect match, exactly what was searched for
- 7-9 = Good match, clearly related to the query
- 4-6 = Partial match, somewhat related
- 1-3 = Poor match, barely related
- 0 = Not relevant at all

Respond in this exact format:
SCORE: [number]
REASON: [brief explanation in one sentence]"""

        response = model.generate_content([prompt, image])
        text = response.text.strip()

        # Parse response
        score = 5.0
        reason = "Unable to parse response"

        for line in text.split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                    score = max(0, min(10, score))  # Clamp to 0-10
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return score, reason

    def _score_with_ollama(
        self,
        image_data: bytes,
        query: str,
        context: Optional[str] = None
    ) -> tuple[float, str]:
        """Score image using Ollama vision model.

        Args:
            image_data: Image bytes.
            query: Search query.
            context: Additional context for scoring.

        Returns:
            Tuple of (score, reason).
        """
        import base64

        host = self.vision_config.get("host", "127.0.0.1")
        port = self.vision_config.get("port", 11434)
        model = self.vision_config.get("model", "qwen2.5-vl:7b")

        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        context_text = f"\nContext: {context}" if context else ""
        prompt = f"""Score this image for relevance to the search query.

Search query: "{query}"{context_text}

Rate the image from 0-10 where:
- 10 = Perfect match, exactly what was searched for
- 7-9 = Good match, clearly related to the query
- 4-6 = Partial match, somewhat related
- 1-3 = Poor match, barely related
- 0 = Not relevant at all

Respond in this exact format:
SCORE: [number]
REASON: [brief explanation in one sentence]"""

        # Use chat API for vision models (not generate)
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64]
                }
            ],
            "stream": False
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"http://{host}:{port}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            # Extract content from chat response
            message = result.get("message", {})
            text = message.get("content", "").strip()

        # Parse response
        score = 5.0
        reason = "Unable to parse response"

        for line in text.split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                    score = max(0, min(10, score))  # Clamp to 0-10
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return score, reason

    def calculate_quality_score(self, result: ImageSearchResult) -> tuple[float, str]:
        """Calculate image quality score based on resolution and aspect ratio.

        Args:
            result: Image search result with width/height.

        Returns:
            Tuple of (quality_score, reason).
        """
        width = result.width or 0
        height = result.height or 0

        if width == 0 or height == 0:
            return 0.0, "Unknown dimensions"

        # Calculate total pixels
        pixels = width * height

        # Calculate aspect ratio (always >= 1)
        aspect = max(width, height) / min(width, height)

        # Resolution score (0-6 points)
        # < 100K pixels = 0, 100K-500K = 2, 500K-1M = 4, 1M-2M = 5, > 2M = 6
        if pixels < 100_000:
            res_score = 0
            res_reason = "very low resolution"
        elif pixels < 500_000:
            res_score = 2
            res_reason = "low resolution"
        elif pixels < 1_000_000:
            res_score = 4
            res_reason = "medium resolution"
        elif pixels < 2_000_000:
            res_score = 5
            res_reason = "good resolution"
        else:
            res_score = 6
            res_reason = "high resolution"

        # Aspect ratio score (0-4 points)
        # Standard ratios (16:9=1.78, 4:3=1.33, 3:2=1.5) get bonus
        # Extreme ratios (> 3:1) get penalty
        standard_ratios = [1.0, 1.33, 1.5, 1.78, 1.91]  # 1:1, 4:3, 3:2, 16:9, 2:1

        # Find closest standard ratio
        closest_diff = min(abs(aspect - sr) for sr in standard_ratios)

        if closest_diff < 0.1:
            aspect_score = 4
            aspect_reason = "standard aspect ratio"
        elif closest_diff < 0.3:
            aspect_score = 3
            aspect_reason = "near-standard aspect ratio"
        elif aspect > 3.0:
            aspect_score = 1
            aspect_reason = "extreme aspect ratio"
        else:
            aspect_score = 2
            aspect_reason = "unusual aspect ratio"

        total_score = res_score + aspect_score
        reason = f"{width}x{height} ({res_reason}, {aspect_reason})"

        return total_score, reason

    def score_image(
        self,
        image_url: str,
        query: str,
        context: Optional[str] = None,
        fallback_url: Optional[str] = None
    ) -> tuple[float, str]:
        """Score a single image.

        Args:
            image_url: Primary URL to try (usually thumbnail).
            query: Search query.
            context: Additional context for scoring.
            fallback_url: Fallback URL if primary fails (usually main image).

        Returns:
            Tuple of (score, reason).
        """
        # Try primary URL first
        image_data = self._download_image(image_url)

        # If primary fails and we have a fallback, try that
        if not image_data and fallback_url and fallback_url != image_url:
            image_data = self._download_image(fallback_url)

        if not image_data:
            return 0.0, "Failed to download image"

        if self.vision_provider == "gemini":
            return self._score_with_gemini(image_data, query, context)
        elif self.vision_provider == "ollama":
            return self._score_with_ollama(image_data, query, context)
        else:
            raise ValueError(f"Unknown vision provider: {self.vision_provider}")

    def score_results(
        self,
        results: List[ImageSearchResult],
        query: str,
        context: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        include_quality: bool = True
    ) -> List[ImageSearchResult]:
        """Score all search results and sort by score.

        Args:
            results: List of search results.
            query: Search query.
            context: Additional context for scoring.
            progress_callback: Optional callback(current, total, result) for progress.
            include_quality: Whether to calculate quality scores (default True).

        Returns:
            List of results sorted by combined score (relevance + quality tiebreaker).
        """
        scored_results = []

        for i, result in enumerate(results):
            # Calculate quality score first (doesn't require download)
            if include_quality:
                quality_score, quality_reason = self.calculate_quality_score(result)
                result.quality_score = quality_score
                result.quality_reason = quality_reason

            # Use thumbnail for faster scoring, with main URL as fallback
            primary_url = result.thumbnail_url or result.url
            fallback_url = result.url if result.thumbnail_url else None

            try:
                score, reason = self.score_image(primary_url, query, context, fallback_url)
                result.score = score
                result.score_reason = reason
                result.scored_by = self.vision_provider
            except Exception as e:
                result.score = 0.0
                result.score_reason = f"Scoring failed: {str(e)}"
                result.scored_by = self.vision_provider

            scored_results.append(result)

            if progress_callback:
                progress_callback(i + 1, len(results), result)

        # Sort by combined score (relevance + quality as tiebreaker)
        scored_results.sort(key=lambda r: r.combined_score(), reverse=True)

        return scored_results
