"""Shared HTTP client utilities for NOLAN.

Provides pre-configured httpx clients with sensible defaults,
connection pooling, and common patterns for making HTTP requests.

Usage:
    # Async usage (recommended for concurrent requests)
    from nolan.http_client import get_async_client

    async with get_async_client() as client:
        response = await client.get("https://api.example.com/data")

    # Sync usage (for simple scripts)
    from nolan.http_client import get_sync_client

    with get_sync_client() as client:
        response = client.get("https://api.example.com/data")

    # Custom timeouts
    async with get_async_client(timeout=60.0) as client:
        response = await client.get("https://slow-api.example.com/data")
"""

from contextlib import contextmanager, asynccontextmanager
from typing import Optional, Dict, Any

import httpx


# Default configuration
DEFAULT_TIMEOUT = 30.0
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "NOLAN/1.0 (Video Essay Tool)"

# Common headers
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
}


def create_timeout(
    timeout: float = DEFAULT_TIMEOUT,
    connect: float = DEFAULT_CONNECT_TIMEOUT,
) -> httpx.Timeout:
    """Create an httpx Timeout object with sensible defaults.

    Args:
        timeout: Total request timeout in seconds.
        connect: Connection timeout in seconds.

    Returns:
        httpx.Timeout configured with the specified values.
    """
    return httpx.Timeout(timeout, connect=connect)


@asynccontextmanager
async def get_async_client(
    timeout: Optional[float] = None,
    connect_timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    **kwargs: Any,
):
    """Get a configured async HTTP client.

    Args:
        timeout: Request timeout in seconds (default: 30.0).
        connect_timeout: Connection timeout in seconds (default: 10.0).
        headers: Additional headers to include.
        follow_redirects: Whether to follow redirects (default: True).
        **kwargs: Additional arguments passed to httpx.AsyncClient.

    Yields:
        Configured httpx.AsyncClient.

    Example:
        async with get_async_client(timeout=60.0) as client:
            response = await client.get("https://api.example.com")
    """
    # Merge headers
    merged_headers = {**DEFAULT_HEADERS}
    if headers:
        merged_headers.update(headers)

    # Create timeout
    timeout_obj = create_timeout(
        timeout=timeout or DEFAULT_TIMEOUT,
        connect=connect_timeout or DEFAULT_CONNECT_TIMEOUT,
    )

    async with httpx.AsyncClient(
        timeout=timeout_obj,
        headers=merged_headers,
        follow_redirects=follow_redirects,
        **kwargs,
    ) as client:
        yield client


@contextmanager
def get_sync_client(
    timeout: Optional[float] = None,
    connect_timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    **kwargs: Any,
):
    """Get a configured sync HTTP client.

    Args:
        timeout: Request timeout in seconds (default: 30.0).
        connect_timeout: Connection timeout in seconds (default: 10.0).
        headers: Additional headers to include.
        follow_redirects: Whether to follow redirects (default: True).
        **kwargs: Additional arguments passed to httpx.Client.

    Yields:
        Configured httpx.Client.

    Example:
        with get_sync_client(timeout=60.0) as client:
            response = client.get("https://api.example.com")
    """
    # Merge headers
    merged_headers = {**DEFAULT_HEADERS}
    if headers:
        merged_headers.update(headers)

    # Create timeout
    timeout_obj = create_timeout(
        timeout=timeout or DEFAULT_TIMEOUT,
        connect=connect_timeout or DEFAULT_CONNECT_TIMEOUT,
    )

    with httpx.Client(
        timeout=timeout_obj,
        headers=merged_headers,
        follow_redirects=follow_redirects,
        **kwargs,
    ) as client:
        yield client


async def fetch_json_async(
    url: str,
    method: str = "GET",
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Fetch JSON from a URL asynchronously.

    Args:
        url: URL to fetch.
        method: HTTP method (default: GET).
        timeout: Request timeout in seconds.
        headers: Additional headers.
        **kwargs: Additional arguments for the request.

    Returns:
        Parsed JSON response as dict.

    Raises:
        httpx.HTTPStatusError: If response status is not 2xx.
        ValueError: If response is not valid JSON.
    """
    async with get_async_client(timeout=timeout, headers=headers) as client:
        if method.upper() == "GET":
            response = await client.get(url, **kwargs)
        elif method.upper() == "POST":
            response = await client.post(url, **kwargs)
        else:
            response = await client.request(method, url, **kwargs)

        response.raise_for_status()
        return response.json()


def fetch_json_sync(
    url: str,
    method: str = "GET",
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Fetch JSON from a URL synchronously.

    Args:
        url: URL to fetch.
        method: HTTP method (default: GET).
        timeout: Request timeout in seconds.
        headers: Additional headers.
        **kwargs: Additional arguments for the request.

    Returns:
        Parsed JSON response as dict.

    Raises:
        httpx.HTTPStatusError: If response status is not 2xx.
        ValueError: If response is not valid JSON.
    """
    with get_sync_client(timeout=timeout, headers=headers) as client:
        if method.upper() == "GET":
            response = client.get(url, **kwargs)
        elif method.upper() == "POST":
            response = client.post(url, **kwargs)
        else:
            response = client.request(method, url, **kwargs)

        response.raise_for_status()
        return response.json()


async def download_file_async(
    url: str,
    output_path: str,
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    chunk_size: int = 8192,
) -> int:
    """Download a file asynchronously.

    Args:
        url: URL to download from.
        output_path: Path to save the file.
        timeout: Request timeout in seconds.
        headers: Additional headers.
        chunk_size: Size of chunks to read.

    Returns:
        Number of bytes downloaded.

    Raises:
        httpx.HTTPStatusError: If response status is not 2xx.
    """
    from pathlib import Path

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    async with get_async_client(timeout=timeout or 120.0, headers=headers) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(output, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    f.write(chunk)
                    total_bytes += len(chunk)

    return total_bytes


def download_file_sync(
    url: str,
    output_path: str,
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    chunk_size: int = 8192,
) -> int:
    """Download a file synchronously.

    Args:
        url: URL to download from.
        output_path: Path to save the file.
        timeout: Request timeout in seconds.
        headers: Additional headers.
        chunk_size: Size of chunks to read.

    Returns:
        Number of bytes downloaded.

    Raises:
        httpx.HTTPStatusError: If response status is not 2xx.
    """
    from pathlib import Path

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    with get_sync_client(timeout=timeout or 120.0, headers=headers) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(output, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    f.write(chunk)
                    total_bytes += len(chunk)

    return total_bytes


# Convenience aliases for common patterns
class ServiceClient:
    """Base class for service-specific HTTP clients.

    Provides a reusable async client with connection pooling for
    services that make multiple requests.

    Example:
        class MyAPIClient(ServiceClient):
            def __init__(self):
                super().__init__("https://api.myservice.com", timeout=30.0)

            async def get_data(self, item_id: str):
                async with self.client() as c:
                    return await c.get(f"{self.base_url}/items/{item_id}")
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize service client.

        Args:
            base_url: Base URL for the service.
            timeout: Default timeout for requests.
            headers: Additional headers to include in all requests.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}

    @asynccontextmanager
    async def client(self):
        """Get an async client for this service."""
        async with get_async_client(
            timeout=self.timeout,
            headers=self.headers,
        ) as c:
            yield c

    async def get(self, path: str, **kwargs) -> httpx.Response:
        """Make a GET request to the service."""
        async with self.client() as c:
            return await c.get(f"{self.base_url}/{path.lstrip('/')}", **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        """Make a POST request to the service."""
        async with self.client() as c:
            return await c.post(f"{self.base_url}/{path.lstrip('/')}", **kwargs)

    async def get_json(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request and return JSON."""
        response = await self.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def post_json(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a POST request and return JSON."""
        response = await self.post(path, **kwargs)
        response.raise_for_status()
        return response.json()
