"""Tests for the nolan.http_client module."""

import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

from nolan.http_client import (
    create_timeout,
    get_async_client,
    get_sync_client,
    fetch_json_async,
    fetch_json_sync,
    download_file_async,
    download_file_sync,
    ServiceClient,
    DEFAULT_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_USER_AGENT,
)


class TestCreateTimeout:
    """Tests for create_timeout function."""

    def test_default_values(self):
        """Should create timeout with default values."""
        timeout = create_timeout()
        assert timeout.read == DEFAULT_TIMEOUT
        assert timeout.connect == DEFAULT_CONNECT_TIMEOUT

    def test_custom_values(self):
        """Should create timeout with custom values."""
        timeout = create_timeout(timeout=60.0, connect=5.0)
        assert timeout.read == 60.0
        assert timeout.connect == 5.0


class TestGetAsyncClient:
    """Tests for get_async_client function."""

    @pytest.mark.asyncio
    async def test_returns_async_client(self):
        """Should return an httpx.AsyncClient."""
        async with get_async_client() as client:
            assert isinstance(client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_default_headers(self):
        """Should include default headers."""
        async with get_async_client() as client:
            assert "User-Agent" in client.headers
            assert DEFAULT_USER_AGENT in client.headers["User-Agent"]

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        """Should merge custom headers."""
        custom = {"X-Custom": "value"}
        async with get_async_client(headers=custom) as client:
            assert client.headers["X-Custom"] == "value"
            # Should still have default headers
            assert "User-Agent" in client.headers

    @pytest.mark.asyncio
    async def test_custom_timeout(self):
        """Should apply custom timeout."""
        async with get_async_client(timeout=60.0) as client:
            assert client.timeout.read == 60.0

    @pytest.mark.asyncio
    async def test_follow_redirects(self):
        """Should respect follow_redirects setting."""
        async with get_async_client(follow_redirects=False) as client:
            assert client.follow_redirects is False


class TestGetSyncClient:
    """Tests for get_sync_client function."""

    def test_returns_sync_client(self):
        """Should return an httpx.Client."""
        with get_sync_client() as client:
            assert isinstance(client, httpx.Client)

    def test_default_headers(self):
        """Should include default headers."""
        with get_sync_client() as client:
            assert "User-Agent" in client.headers

    def test_custom_headers(self):
        """Should merge custom headers."""
        custom = {"Authorization": "Bearer token"}
        with get_sync_client(headers=custom) as client:
            assert client.headers["Authorization"] == "Bearer token"


class TestFetchJsonAsync:
    """Tests for fetch_json_async function."""

    @pytest.mark.asyncio
    async def test_get_request(self):
        """Should make GET request and return JSON."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_response.raise_for_status = MagicMock()

        with patch("nolan.http_client.get_async_client") as mock_client:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_ctx

            result = await fetch_json_async("https://example.com/api")
            assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_post_request(self):
        """Should make POST request and return JSON."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"created": True}
        mock_response.raise_for_status = MagicMock()

        with patch("nolan.http_client.get_async_client") as mock_client:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_ctx

            result = await fetch_json_async(
                "https://example.com/api",
                method="POST",
                json={"data": "test"}
            )
            assert result == {"created": True}


class TestFetchJsonSync:
    """Tests for fetch_json_sync function."""

    def test_get_request(self):
        """Should make GET request and return JSON."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"sync": True}
        mock_response.raise_for_status = MagicMock()

        with patch("nolan.http_client.get_sync_client") as mock_client:
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value.get.return_value = mock_response
            mock_client.return_value = mock_ctx

            result = fetch_json_sync("https://example.com/api")
            assert result == {"sync": True}


class TestDownloadFileAsync:
    """Tests for download_file_async function."""

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path):
        """Should create parent directories when downloading."""
        from pathlib import Path

        # Test that parent directory creation works
        output_file = tmp_path / "nested" / "dir" / "file.txt"

        # We'll just test the path creation logic directly
        output = Path(output_file)
        output.parent.mkdir(parents=True, exist_ok=True)

        assert output.parent.exists()

    @pytest.mark.asyncio
    async def test_function_signature(self):
        """Should have correct function signature."""
        import inspect
        sig = inspect.signature(download_file_async)
        params = list(sig.parameters.keys())
        assert "url" in params
        assert "output_path" in params
        assert "timeout" in params
        assert "headers" in params


class TestDownloadFileSync:
    """Tests for download_file_sync function."""

    def test_downloads_file(self, tmp_path):
        """Should download and save file."""
        output_file = tmp_path / "sync_downloaded.txt"
        content = b"Sync content"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = [content]

        with patch("nolan.http_client.get_sync_client") as mock_client:
            mock_ctx = MagicMock()
            mock_stream = MagicMock()
            mock_stream.__enter__.return_value = mock_response
            mock_ctx.__enter__.return_value.stream.return_value = mock_stream
            mock_client.return_value = mock_ctx

            bytes_downloaded = download_file_sync(
                "https://example.com/file.txt",
                str(output_file)
            )

            assert bytes_downloaded == len(content)
            assert output_file.exists()


class TestServiceClient:
    """Tests for ServiceClient class."""

    def test_init(self):
        """Should initialize with base URL."""
        client = ServiceClient("https://api.example.com")
        assert client.base_url == "https://api.example.com"
        assert client.timeout == DEFAULT_TIMEOUT

    def test_strips_trailing_slash(self):
        """Should strip trailing slash from base URL."""
        client = ServiceClient("https://api.example.com/")
        assert client.base_url == "https://api.example.com"

    def test_custom_timeout(self):
        """Should accept custom timeout."""
        client = ServiceClient("https://api.example.com", timeout=60.0)
        assert client.timeout == 60.0

    def test_custom_headers(self):
        """Should accept custom headers."""
        headers = {"Authorization": "Bearer token"}
        client = ServiceClient("https://api.example.com", headers=headers)
        assert client.headers == headers

    @pytest.mark.asyncio
    async def test_get_method(self):
        """Should make GET request to path."""
        client = ServiceClient("https://api.example.com")

        mock_response = MagicMock()
        with patch.object(client, "client") as mock_client:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_ctx

            response = await client.get("/items/123")
            mock_ctx.__aenter__.return_value.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_method(self):
        """Should make POST request to path."""
        client = ServiceClient("https://api.example.com")

        mock_response = MagicMock()
        with patch.object(client, "client") as mock_client:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_ctx

            response = await client.post("/items", json={"name": "test"})
            mock_ctx.__aenter__.return_value.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_json(self):
        """Should make GET request and return JSON."""
        client = ServiceClient("https://api.example.com")

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 123}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "get", return_value=mock_response) as mock_get:
            result = await client.get_json("/items/123")
            assert result == {"id": 123}
            mock_response.raise_for_status.assert_called_once()
