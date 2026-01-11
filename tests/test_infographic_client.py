"""Tests for InfographicClient."""

import pytest
from unittest.mock import AsyncMock, patch, Mock, MagicMock
from pathlib import Path

from nolan.infographic_client import (
    InfographicClient,
    Engine,
    JobStatus,
    RenderJob,
)


@pytest.fixture
def client():
    """Create InfographicClient instance for testing."""
    return InfographicClient(host="127.0.0.1", port=3010)


def create_mock_response(json_data, status_code=200):
    """Create a mock httpx response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = Mock()
    return mock_response


class TestInfographicClient:
    """Test InfographicClient."""

    def test_client_initialization(self):
        """Client initializes with configuration."""
        client = InfographicClient(host="localhost", port=4000)
        assert client.base_url == "http://localhost:4000"

    def test_client_default_initialization(self):
        """Client uses default configuration."""
        client = InfographicClient()
        assert client.base_url == "http://127.0.0.1:3010"

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test health check when service is running."""
        mock_response = create_mock_response({}, status_code=200)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        """Test health check when service is down."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_non_200(self, client):
        """Test health check when service returns non-200."""
        mock_response = create_mock_response({}, status_code=503)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_submit_job(self, client):
        """Test submitting a render job."""
        mock_response = create_mock_response({
            "job_id": "test-123",
            "status": "pending"
        }, status_code=202)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            job = await client.submit(
                engine=Engine.INFOGRAPHIC,
                data={"items": [1, 2, 3]}
            )
            assert job.job_id == "test-123"
            assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_submit_job_with_options(self, client):
        """Test submitting a render job with all options."""
        mock_response = create_mock_response({
            "job_id": "test-456",
            "status": "pending"
        })

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            job = await client.submit(
                engine=Engine.MOTION_CANVAS,
                data={"title": "Test"},
                template="timeline",
                duration=30.0,
                audio="/path/to/audio.mp3",
                style_prompt="Modern and clean"
            )
            assert job.job_id == "test-456"
            assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_status(self, client):
        """Test getting job status."""
        mock_response = create_mock_response({
            "job_id": "test-123",
            "status": "rendering",
            "progress": 0.5
        })

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            job = await client.get_status("test-123")
            assert job.job_id == "test-123"
            assert job.status == JobStatus.RENDERING
            assert job.progress == 0.5

    @pytest.mark.asyncio
    async def test_get_status_with_error(self, client):
        """Test getting job status when job has error."""
        mock_response = create_mock_response({
            "job_id": "test-123",
            "status": "error",
            "error": "Rendering failed"
        })

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            job = await client.get_status("test-123")
            assert job.status == JobStatus.ERROR
            assert job.error == "Rendering failed"

    @pytest.mark.asyncio
    async def test_get_result(self, client):
        """Test getting completed job result."""
        mock_response = create_mock_response({
            "job_id": "test-123",
            "video_path": "/output/video.mp4"
        })

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            job = await client.get_result("test-123")
            assert job.job_id == "test-123"
            assert job.status == JobStatus.DONE
            assert job.video_path == "/output/video.mp4"

    @pytest.mark.asyncio
    async def test_wait_for_completion_success(self, client):
        """Test waiting for job completion."""
        # Simulate pending -> rendering -> done
        status_responses = [
            {"job_id": "test-123", "status": "pending", "progress": 0.0},
            {"job_id": "test-123", "status": "rendering", "progress": 0.5},
            {"job_id": "test-123", "status": "done", "progress": 1.0},
        ]
        result_response = {
            "job_id": "test-123",
            "video_path": "/output/video.mp4"
        }

        call_count = [0]

        async def mock_get_status(job_id):
            resp = status_responses[min(call_count[0], len(status_responses) - 1)]
            call_count[0] += 1
            return RenderJob(
                job_id=resp["job_id"],
                status=JobStatus(resp["status"]),
                progress=resp["progress"]
            )

        async def mock_get_result(job_id):
            return RenderJob(
                job_id=result_response["job_id"],
                status=JobStatus.DONE,
                video_path=result_response["video_path"]
            )

        with patch.object(client, "get_status", side_effect=mock_get_status):
            with patch.object(client, "get_result", side_effect=mock_get_result):
                with patch("asyncio.sleep", return_value=None):
                    job = await client.wait_for_completion("test-123", poll_interval=0.1)
                    assert job.status == JobStatus.DONE
                    assert job.video_path == "/output/video.mp4"

    @pytest.mark.asyncio
    async def test_wait_for_completion_with_callback(self, client):
        """Test progress callback is called during wait."""
        progress_values = []

        def progress_callback(progress):
            progress_values.append(progress)

        status_responses = [
            {"job_id": "test-123", "status": "rendering", "progress": 0.25},
            {"job_id": "test-123", "status": "rendering", "progress": 0.75},
            {"job_id": "test-123", "status": "done", "progress": 1.0},
        ]

        call_count = [0]

        async def mock_get_status(job_id):
            resp = status_responses[min(call_count[0], len(status_responses) - 1)]
            call_count[0] += 1
            return RenderJob(
                job_id=resp["job_id"],
                status=JobStatus(resp["status"]),
                progress=resp["progress"]
            )

        async def mock_get_result(job_id):
            return RenderJob(job_id="test-123", status=JobStatus.DONE, video_path="/out.mp4")

        with patch.object(client, "get_status", side_effect=mock_get_status):
            with patch.object(client, "get_result", side_effect=mock_get_result):
                with patch("asyncio.sleep", return_value=None):
                    await client.wait_for_completion(
                        "test-123",
                        poll_interval=0.1,
                        progress_callback=progress_callback
                    )
                    assert 0.25 in progress_values
                    assert 0.75 in progress_values

    @pytest.mark.asyncio
    async def test_wait_for_completion_timeout(self, client):
        """Test timeout when job takes too long."""
        async def mock_get_status(job_id):
            return RenderJob(
                job_id="test-123",
                status=JobStatus.RENDERING,
                progress=0.1
            )

        with patch.object(client, "get_status", side_effect=mock_get_status):
            with patch("asyncio.sleep", return_value=None):
                with pytest.raises(TimeoutError):
                    await client.wait_for_completion(
                        "test-123",
                        poll_interval=0.5,
                        timeout=1.0
                    )

    @pytest.mark.asyncio
    async def test_wait_for_completion_error(self, client):
        """Test error when job fails."""
        async def mock_get_status(job_id):
            return RenderJob(
                job_id="test-123",
                status=JobStatus.ERROR,
                error="Out of memory"
            )

        with patch.object(client, "get_status", side_effect=mock_get_status):
            with pytest.raises(RuntimeError, match="Out of memory"):
                await client.wait_for_completion("test-123")

    @pytest.mark.asyncio
    async def test_render_convenience_method(self, client):
        """Test render method combines submit and wait."""
        async def mock_submit(*args, **kwargs):
            return RenderJob(job_id="test-789", status=JobStatus.PENDING)

        async def mock_wait(job_id, **kwargs):
            return RenderJob(
                job_id=job_id,
                status=JobStatus.DONE,
                video_path="/output/final.mp4"
            )

        with patch.object(client, "submit", side_effect=mock_submit):
            with patch.object(client, "wait_for_completion", side_effect=mock_wait):
                result = await client.render(
                    engine=Engine.REMOTION,
                    data={"text": "Hello"}
                )
                # Use Path for cross-platform comparison
                assert result == Path("/output/final.mp4")


class TestEnums:
    """Test enum values."""

    def test_engine_values(self):
        """Test Engine enum values."""
        assert Engine.INFOGRAPHIC.value == "infographic"
        assert Engine.MOTION_CANVAS.value == "motion-canvas"
        assert Engine.REMOTION.value == "remotion"

    def test_job_status_values(self):
        """Test JobStatus enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RENDERING.value == "rendering"
        assert JobStatus.DONE.value == "done"
        assert JobStatus.ERROR.value == "error"


class TestRenderJob:
    """Test RenderJob dataclass."""

    def test_render_job_defaults(self):
        """Test RenderJob default values."""
        job = RenderJob(job_id="test", status=JobStatus.PENDING)
        assert job.job_id == "test"
        assert job.status == JobStatus.PENDING
        assert job.progress == 0.0
        assert job.video_path is None
        assert job.error is None

    def test_render_job_full(self):
        """Test RenderJob with all values."""
        job = RenderJob(
            job_id="test-full",
            status=JobStatus.DONE,
            progress=1.0,
            video_path="/path/to/video.mp4",
            error=None
        )
        assert job.video_path == "/path/to/video.mp4"
        assert job.progress == 1.0
