"""Whisper-based transcript generation using faster-whisper."""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


@dataclass
class WhisperConfig:
    """Configuration for Whisper transcription."""
    model_size: str = "base"  # tiny, base, small, medium, large-v2, large-v3
    device: str = "auto"  # auto, cpu, cuda
    compute_type: str = "auto"  # auto, int8, float16, float32
    language: Optional[str] = None  # None for auto-detect
    vad_filter: bool = True  # Voice activity detection
    beam_size: int = 5


@dataclass
class TranscriptSegment:
    """A single segment of transcribed text."""
    start: float
    end: float
    text: str


class WhisperTranscriber:
    """Generate transcripts from video/audio using faster-whisper."""

    def __init__(self, config: Optional[WhisperConfig] = None):
        if not WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is not installed. "
                "Install it with: pip install faster-whisper"
            )

        self.config = config or WhisperConfig()
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        """Lazy-load the Whisper model."""
        if self._model is None:
            self._model = WhisperModel(
                self.config.model_size,
                device=self.config.device,
                compute_type=self.config.compute_type,
            )
        return self._model

    def extract_audio(self, video_path: Path, output_path: Path) -> bool:
        """Extract audio from video using ffmpeg.

        Args:
            video_path: Path to input video.
            output_path: Path to output audio file (wav format recommended).

        Returns:
            True if extraction succeeded, False otherwise.
        """
        try:
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # PCM 16-bit
                "-ar", "16000",  # 16kHz sample rate (optimal for Whisper)
                "-ac", "1",  # Mono
                "-y",  # Overwrite output
                str(output_path)
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> List[TranscriptSegment]:
        """Transcribe audio file to text segments.

        Args:
            audio_path: Path to audio file.
            progress_callback: Optional callback for progress updates (0.0-1.0).

        Returns:
            List of transcript segments with timestamps.
        """
        segments, info = self.model.transcribe(
            str(audio_path),
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=self.config.vad_filter,
        )

        result = []
        for segment in segments:
            result.append(TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text.strip(),
            ))

            if progress_callback and info.duration > 0:
                progress = min(1.0, segment.end / info.duration)
                progress_callback(progress)

        return result

    def transcribe_video(
        self,
        video_path: Path,
        output_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Optional[Path]:
        """Transcribe video and save as Whisper JSON format.

        Args:
            video_path: Path to video file.
            output_path: Path for output JSON. If None, uses video path with .json extension.
            progress_callback: Optional callback (phase: str, progress: float).

        Returns:
            Path to saved transcript, or None if failed.
        """
        if output_path is None:
            output_path = video_path.with_suffix(".whisper.json")

        # Skip if transcript already exists
        if output_path.exists():
            return output_path

        # Extract audio to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_audio = Path(tmp.name)

        try:
            if progress_callback:
                progress_callback("Extracting audio", 0.0)

            if not self.extract_audio(video_path, tmp_audio):
                return None

            if progress_callback:
                progress_callback("Extracting audio", 1.0)
                progress_callback("Transcribing", 0.0)

            # Transcribe
            def transcribe_progress(p: float):
                if progress_callback:
                    progress_callback("Transcribing", p)

            segments = self.transcribe(tmp_audio, transcribe_progress)

            if progress_callback:
                progress_callback("Saving", 0.0)

            # Save in Whisper JSON format
            whisper_output = {
                "text": " ".join(s.text for s in segments),
                "segments": [
                    {
                        "id": i,
                        "start": s.start,
                        "end": s.end,
                        "text": s.text,
                    }
                    for i, s in enumerate(segments)
                ],
                "language": self.config.language or "auto",
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(whisper_output, f, indent=2, ensure_ascii=False)

            if progress_callback:
                progress_callback("Saving", 1.0)

            return output_path

        finally:
            # Cleanup temp audio
            if tmp_audio.exists():
                tmp_audio.unlink()


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def create_transcriber(config: Optional[WhisperConfig] = None) -> WhisperTranscriber:
    """Create a WhisperTranscriber instance.

    Args:
        config: Optional configuration.

    Returns:
        WhisperTranscriber instance.

    Raises:
        ImportError: If faster-whisper is not installed.
        RuntimeError: If ffmpeg is not available.
    """
    if not WHISPER_AVAILABLE:
        raise ImportError(
            "faster-whisper is not installed. "
            "Install it with: pip install faster-whisper"
        )

    if not check_ffmpeg():
        raise RuntimeError(
            "ffmpeg is not installed or not in PATH. "
            "Install ffmpeg to enable audio extraction."
        )

    return WhisperTranscriber(config)
