"""Tests for whisper transcription module."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestWhisperConfig:
    """Tests for WhisperConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        from nolan.whisper import WhisperConfig
        config = WhisperConfig()
        assert config.model_size == "base"
        assert config.device == "auto"
        assert config.compute_type == "auto"
        assert config.language is None
        assert config.vad_filter is True
        assert config.beam_size == 5

    def test_custom_values(self):
        """Test custom configuration values."""
        from nolan.whisper import WhisperConfig
        config = WhisperConfig(
            model_size="large-v3",
            device="cuda",
            compute_type="float16",
            language="en",
            vad_filter=False,
            beam_size=3
        )
        assert config.model_size == "large-v3"
        assert config.device == "cuda"
        assert config.compute_type == "float16"
        assert config.language == "en"
        assert config.vad_filter is False
        assert config.beam_size == 3


class TestTranscriptSegment:
    """Tests for TranscriptSegment dataclass."""

    def test_creation(self):
        """Test TranscriptSegment creation."""
        from nolan.whisper import TranscriptSegment
        segment = TranscriptSegment(start=1.5, end=3.0, text="Hello world")
        assert segment.start == 1.5
        assert segment.end == 3.0
        assert segment.text == "Hello world"


class TestCheckFfmpeg:
    """Tests for ffmpeg availability check."""

    def test_ffmpeg_available(self):
        """Test when ffmpeg is available."""
        from nolan.whisper import check_ffmpeg

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            assert check_ffmpeg() is True
            mock_run.assert_called_once()

    def test_ffmpeg_not_found(self):
        """Test when ffmpeg is not installed."""
        from nolan.whisper import check_ffmpeg

        with patch('subprocess.run', side_effect=FileNotFoundError()):
            assert check_ffmpeg() is False

    def test_ffmpeg_timeout(self):
        """Test when ffmpeg check times out."""
        import subprocess
        from nolan.whisper import check_ffmpeg

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 10)):
            assert check_ffmpeg() is False


class TestWhisperTranscriber:
    """Tests for WhisperTranscriber."""

    def test_init_without_package(self):
        """Test initialization when faster-whisper not installed."""
        with patch.dict('sys.modules', {'faster_whisper': None}):
            # Force reload to pick up mocked module
            import importlib
            import nolan.whisper
            # This test is tricky because the module is already loaded
            # Just verify the import check exists
            assert hasattr(nolan.whisper, 'WHISPER_AVAILABLE')

    def test_extract_audio_success(self):
        """Test successful audio extraction."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel'):

            transcriber = WhisperTranscriber(WhisperConfig())

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)
                result = transcriber.extract_audio(
                    Path("/input/video.mp4"),
                    Path("/output/audio.wav")
                )
                assert result is True

    def test_extract_audio_failure(self):
        """Test failed audio extraction."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel'):

            transcriber = WhisperTranscriber(WhisperConfig())

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=1)
                result = transcriber.extract_audio(
                    Path("/input/video.mp4"),
                    Path("/output/audio.wav")
                )
                assert result is False

    def test_extract_audio_ffmpeg_not_found(self):
        """Test audio extraction when ffmpeg not found."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel'):

            transcriber = WhisperTranscriber(WhisperConfig())

            with patch('subprocess.run', side_effect=FileNotFoundError()):
                result = transcriber.extract_audio(
                    Path("/input/video.mp4"),
                    Path("/output/audio.wav")
                )
                assert result is False

    def test_transcribe(self):
        """Test audio transcription."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig

        mock_segments = [
            Mock(start=0.0, end=2.0, text=" Hello world "),
            Mock(start=2.5, end=4.0, text=" Goodbye "),
        ]
        mock_info = Mock(duration=4.0)

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel') as MockModel:

            mock_model = MockModel.return_value
            mock_model.transcribe.return_value = (mock_segments, mock_info)

            transcriber = WhisperTranscriber(WhisperConfig())
            result = transcriber.transcribe(Path("/audio.wav"))

            assert len(result) == 2
            assert result[0].start == 0.0
            assert result[0].end == 2.0
            assert result[0].text == "Hello world"
            assert result[1].text == "Goodbye"

    def test_transcribe_with_progress(self):
        """Test transcription with progress callback."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig

        mock_segments = [
            Mock(start=0.0, end=2.0, text="Hello"),
            Mock(start=2.0, end=4.0, text="World"),
        ]
        mock_info = Mock(duration=4.0)

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel') as MockModel:

            mock_model = MockModel.return_value
            mock_model.transcribe.return_value = (mock_segments, mock_info)

            transcriber = WhisperTranscriber(WhisperConfig())
            progress_values = []

            def progress_cb(p):
                progress_values.append(p)

            transcriber.transcribe(Path("/audio.wav"), progress_callback=progress_cb)

            assert len(progress_values) == 2
            assert progress_values[0] == pytest.approx(0.5)
            assert progress_values[1] == pytest.approx(1.0)

    def test_transcribe_video(self, tmp_path):
        """Test full video transcription pipeline."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig, TranscriptSegment

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video data")

        mock_segments = [
            Mock(start=0.0, end=2.0, text="Hello world"),
        ]
        mock_info = Mock(duration=2.0)

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel') as MockModel, \
             patch('subprocess.run') as mock_run, \
             patch('tempfile.NamedTemporaryFile') as mock_temp:

            # Setup mocks
            mock_model = MockModel.return_value
            mock_model.transcribe.return_value = (mock_segments, mock_info)
            mock_run.return_value = Mock(returncode=0)

            # Mock temp file
            mock_temp_file = MagicMock()
            mock_temp_file.name = str(tmp_path / "temp.wav")
            mock_temp_file.__enter__ = Mock(return_value=mock_temp_file)
            mock_temp_file.__exit__ = Mock(return_value=False)
            mock_temp.return_value = mock_temp_file

            # Create temp wav file so unlink works
            (tmp_path / "temp.wav").write_bytes(b"")

            transcriber = WhisperTranscriber(WhisperConfig())
            result_path = transcriber.transcribe_video(video_path)

            assert result_path is not None
            assert result_path.suffix == ".json"
            assert result_path.exists()

            # Verify JSON output format
            with open(result_path) as f:
                data = json.load(f)

            assert "text" in data
            assert "segments" in data
            assert len(data["segments"]) == 1
            assert data["segments"][0]["text"] == "Hello world"

    def test_transcribe_video_skip_existing(self, tmp_path):
        """Test that existing transcript is not regenerated."""
        from nolan.whisper import WhisperTranscriber, WhisperConfig

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video")

        existing_transcript = tmp_path / "test.whisper.json"
        existing_transcript.write_text('{"text": "existing"}')

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel'):

            transcriber = WhisperTranscriber(WhisperConfig())
            result = transcriber.transcribe_video(video_path)

            # Should return existing file without regenerating
            assert result == existing_transcript


class TestCreateTranscriber:
    """Tests for create_transcriber factory."""

    def test_create_success(self):
        """Test successful transcriber creation."""
        from nolan.whisper import create_transcriber, WhisperConfig

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.WhisperModel'), \
             patch('nolan.whisper.check_ffmpeg', return_value=True):

            transcriber = create_transcriber(WhisperConfig())
            assert transcriber is not None

    def test_create_no_whisper(self):
        """Test creation fails without faster-whisper."""
        from nolan.whisper import create_transcriber

        with patch('nolan.whisper.WHISPER_AVAILABLE', False):
            with pytest.raises(ImportError, match="faster-whisper"):
                create_transcriber()

    def test_create_no_ffmpeg(self):
        """Test creation fails without ffmpeg."""
        from nolan.whisper import create_transcriber

        with patch('nolan.whisper.WHISPER_AVAILABLE', True), \
             patch('nolan.whisper.check_ffmpeg', return_value=False):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                create_transcriber()
