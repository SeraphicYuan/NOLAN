"""Smart frame sampling strategies for video indexing."""

import cv2
import numpy as np
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator, Optional
from enum import Enum


class SamplingStrategy(str, Enum):
    """Available sampling strategies."""
    FIXED = "fixed"
    SCENE_CHANGE = "scene_change"
    KEYFRAME = "keyframe"
    PERCEPTUAL_HASH = "perceptual_hash"
    HYBRID = "hybrid"
    FFMPEG_SCENE = "ffmpeg_scene"  # Fast FFmpeg-based scene detection


@dataclass
class SampledFrame:
    """A sampled frame from a video."""
    timestamp: float  # seconds
    frame: np.ndarray  # BGR image
    reason: str  # why this frame was sampled


@dataclass
class SamplerConfig:
    """Configuration for frame sampling."""
    strategy: SamplingStrategy = SamplingStrategy.FFMPEG_SCENE
    # Fixed interval settings
    fixed_interval: float = 5.0  # seconds
    # Scene change settings (for hybrid/scene_change samplers)
    scene_threshold: float = 30.0  # mean pixel difference
    # Hybrid settings
    min_interval: float = 1.0  # minimum seconds between samples
    max_interval: float = 30.0  # maximum seconds between samples
    # Perceptual hash settings
    hash_threshold: int = 5  # hamming distance threshold
    # FFmpeg scene detection settings
    ffmpeg_scene_threshold: float = None  # None = adaptive (5 sigma), or fixed value 0-1
    ffmpeg_adaptive_sigma: float = 5.0  # Sigma multiplier for adaptive threshold


class FrameSampler(ABC):
    """Abstract base class for frame samplers."""

    @abstractmethod
    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample frames from a video.

        Args:
            video_path: Path to video file.

        Yields:
            SampledFrame objects.
        """
        pass

    def _open_video(self, video_path: Path) -> cv2.VideoCapture:
        """Open video file and return capture object."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        return cap

    def _get_video_info(self, cap: cv2.VideoCapture) -> dict:
        """Get video metadata."""
        return {
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }


class FixedIntervalSampler(FrameSampler):
    """Sample frames at fixed time intervals."""

    def __init__(self, interval: float = 5.0):
        """Initialize fixed interval sampler.

        Args:
            interval: Seconds between samples.
        """
        self.interval = interval

    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample frames at fixed intervals."""
        cap = self._open_video(video_path)
        info = self._get_video_info(cap)
        fps = info["fps"]

        if fps <= 0:
            cap.release()
            return

        frame_skip = int(fps * self.interval)
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % frame_skip == 0:
                timestamp = frame_num / fps
                yield SampledFrame(
                    timestamp=timestamp,
                    frame=frame,
                    reason="fixed_interval"
                )

            frame_num += 1

        cap.release()


class SceneChangeSampler(FrameSampler):
    """Sample frames when scene content changes significantly."""

    def __init__(self, threshold: float = 30.0, min_interval: float = 0.5):
        """Initialize scene change sampler.

        Args:
            threshold: Mean pixel difference threshold.
            min_interval: Minimum seconds between samples.
        """
        self.threshold = threshold
        self.min_interval = min_interval

    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample frames on scene changes."""
        cap = self._open_video(video_path)
        info = self._get_video_info(cap)
        fps = info["fps"]

        if fps <= 0:
            cap.release()
            return

        prev_gray = None
        last_sample_time = -self.min_interval
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_num / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            should_sample = False
            reason = ""

            if prev_gray is None:
                # First frame
                should_sample = True
                reason = "first_frame"
            elif current_time - last_sample_time >= self.min_interval:
                # Check for scene change
                diff = cv2.absdiff(prev_gray, gray)
                change_score = diff.mean()

                if change_score > self.threshold:
                    should_sample = True
                    reason = f"scene_change (score={change_score:.1f})"

            if should_sample:
                yield SampledFrame(
                    timestamp=current_time,
                    frame=frame,
                    reason=reason
                )
                last_sample_time = current_time

            prev_gray = gray
            frame_num += 1

        cap.release()


class PerceptualHashSampler(FrameSampler):
    """Sample frames using perceptual hashing to skip duplicates."""

    def __init__(self, interval: float = 2.0, hash_threshold: int = 5):
        """Initialize perceptual hash sampler.

        Args:
            interval: Base interval for sampling candidates.
            hash_threshold: Hamming distance threshold for similarity.
        """
        self.interval = interval
        self.hash_threshold = hash_threshold

    def _compute_phash(self, frame: np.ndarray, hash_size: int = 8) -> int:
        """Compute perceptual hash of a frame.

        Args:
            frame: BGR image.
            hash_size: Size of hash (hash_size^2 bits).

        Returns:
            Integer hash value.
        """
        # Resize to hash_size+1 x hash_size (for gradient)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (hash_size + 1, hash_size))

        # Compute gradient (difference between adjacent pixels)
        diff = resized[:, 1:] > resized[:, :-1]

        # Convert to integer
        return sum(2**i for i, v in enumerate(diff.flatten()) if v)

    def _hamming_distance(self, hash1: int, hash2: int) -> int:
        """Compute Hamming distance between two hashes."""
        return bin(hash1 ^ hash2).count('1')

    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample frames, skipping perceptually similar ones."""
        cap = self._open_video(video_path)
        info = self._get_video_info(cap)
        fps = info["fps"]

        if fps <= 0:
            cap.release()
            return

        frame_skip = int(fps * self.interval)
        frame_num = 0
        last_hash = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % frame_skip == 0:
                current_hash = self._compute_phash(frame)
                timestamp = frame_num / fps

                should_sample = False
                reason = ""

                if last_hash is None:
                    should_sample = True
                    reason = "first_frame"
                else:
                    distance = self._hamming_distance(current_hash, last_hash)
                    if distance >= self.hash_threshold:
                        should_sample = True
                        reason = f"content_changed (distance={distance})"

                if should_sample:
                    yield SampledFrame(
                        timestamp=timestamp,
                        frame=frame,
                        reason=reason
                    )
                    last_hash = current_hash

            frame_num += 1

        cap.release()


class HybridSampler(FrameSampler):
    """Combines time bounds with scene detection for optimal sampling."""

    def __init__(
        self,
        min_interval: float = 1.0,
        max_interval: float = 30.0,
        scene_threshold: float = 25.0
    ):
        """Initialize hybrid sampler.

        Args:
            min_interval: Minimum seconds between samples.
            max_interval: Maximum seconds between samples.
            scene_threshold: Scene change threshold.
        """
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.scene_threshold = scene_threshold

    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample using hybrid strategy.

        - Never sample more than once per min_interval
        - Always sample at least once per max_interval
        - Sample on scene changes (within bounds)
        """
        cap = self._open_video(video_path)
        info = self._get_video_info(cap)
        fps = info["fps"]

        if fps <= 0:
            cap.release()
            return

        prev_gray = None
        last_sample_time = -self.max_interval
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_num / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            should_sample = False
            reason = ""
            time_since_last = current_time - last_sample_time

            # Always sample if max_interval exceeded
            if time_since_last >= self.max_interval:
                should_sample = True
                reason = "max_interval"
            # Check for scene change if min_interval passed
            elif time_since_last >= self.min_interval and prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                change_score = diff.mean()
                if change_score > self.scene_threshold:
                    should_sample = True
                    reason = f"scene_change (score={change_score:.1f})"
            # First frame
            elif prev_gray is None:
                should_sample = True
                reason = "first_frame"

            if should_sample:
                yield SampledFrame(
                    timestamp=current_time,
                    frame=frame,
                    reason=reason
                )
                last_sample_time = current_time

            prev_gray = gray
            frame_num += 1

        cap.release()


class FFmpegSceneSampler(FrameSampler):
    """Fast scene detection using FFmpeg's scene filter.

    Uses hardware-accelerated scene detection instead of decoding every frame.
    Typically 10-50x faster than Python-based scene detection.
    """

    def __init__(
        self,
        scene_threshold: float = None,
        min_interval: float = 1.0,
        max_interval: float = 30.0,
        adaptive_sigma: float = 5.0,
        progress_callback=None
    ):
        """Initialize FFmpeg scene sampler.

        Args:
            scene_threshold: FFmpeg scene change threshold (0-1), or None for adaptive.
                            When None, uses adaptive_sigma to calculate threshold.
            min_interval: Minimum seconds between samples.
            max_interval: Maximum seconds between samples (fallback).
            adaptive_sigma: Sigma multiplier for adaptive threshold (default 5.0).
                           Threshold = mean + adaptive_sigma * stdev of all scores.
            progress_callback: Optional callback(message) for status updates.
        """
        self.scene_threshold = scene_threshold  # None = adaptive mode
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.adaptive_sigma = adaptive_sigma
        self.progress_callback = progress_callback
        self._last_detection_result = None  # Store result for reporting

    def _log(self, message: str):
        """Log a message via callback if available."""
        if self.progress_callback:
            self.progress_callback(message)

    def _get_scores_cache_path(self, video_path: Path) -> Path:
        """Get the path to the scores cache file for a video."""
        return video_path.with_suffix(video_path.suffix + ".scores.json")

    def _load_scores_cache(self, video_path: Path) -> Optional[list[tuple[float, float]]]:
        """Load cached frame scores if valid.

        Returns:
            List of (timestamp, score) tuples, or None if cache invalid/missing.
        """
        import json

        cache_path = self._get_scores_cache_path(video_path)
        if not cache_path.exists():
            return None

        try:
            # Check if video has been modified since cache was created
            video_mtime = video_path.stat().st_mtime
            video_size = video_path.stat().st_size

            with open(cache_path, 'r') as f:
                cache = json.load(f)

            # Validate cache
            if cache.get('video_mtime') != video_mtime:
                self._log("Video modified since cache created, re-analyzing...")
                return None
            if cache.get('video_size') != video_size:
                self._log("Video size changed, re-analyzing...")
                return None

            frames = cache.get('frames', [])
            if len(frames) < 10:
                return None

            self._log(f"Loaded {len(frames)} cached frame scores")
            return [(f[0], f[1]) for f in frames]

        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _save_scores_cache(
        self,
        video_path: Path,
        frames: list[tuple[float, float]]
    ) -> None:
        """Save frame scores to cache file.

        Args:
            video_path: Path to video file.
            frames: List of (timestamp, score) tuples.
        """
        import json

        cache_path = self._get_scores_cache_path(video_path)

        try:
            cache = {
                'video_mtime': video_path.stat().st_mtime,
                'video_size': video_path.stat().st_size,
                'frame_count': len(frames),
                'frames': [[ts, score] for ts, score in frames]
            }

            with open(cache_path, 'w') as f:
                json.dump(cache, f)

            self._log(f"Saved {len(frames)} frame scores to cache")

        except Exception as e:
            # Cache save failure is not critical
            self._log(f"Warning: Could not save scores cache: {e}")

    def _detect_video_codec(self, video_path: Path) -> Optional[str]:
        """Detect the video codec using ffprobe."""
        import subprocess
        cmd = [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            str(video_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.stdout.strip().lower()
        except Exception:
            return None

    def _detect_scene_timestamps(
        self,
        video_path: Path,
        duration: float
    ) -> tuple[list[tuple[float, str]], Optional[str]]:
        """Use FFmpeg to detect scene change timestamps.

        Uses adaptive thresholding (mean + N*sigma) to find statistically
        significant scene changes, or a fixed threshold if specified.

        Args:
            video_path: Path to video file.
            duration: Video duration in seconds (for timeout calculation).

        Returns:
            Tuple of (timestamps list, error message or None).
        """
        import subprocess
        import re
        import statistics

        # Calculate dynamic timeout: 15 seconds per minute of video, minimum 60 seconds
        timeout_seconds = max(60, int(duration / 60 * 15))

        # Detect codec to use appropriate decoder
        codec = self._detect_video_codec(video_path)
        decoder_args = []

        # Use libdav1d for AV1 (3-5x faster than libaom)
        if codec in ('av1', 'av01'):
            decoder_args = ["-c:v", "libdav1d"]
            self._log(f"Detected AV1 codec, using libdav1d decoder (faster)")

        # Determine if we need adaptive mode
        use_adaptive = self.scene_threshold is None

        if use_adaptive:
            # Check for cached scores first
            cached_frames = self._load_scores_cache(video_path)
            if cached_frames is not None:
                # Use cached scores - skip FFmpeg entirely
                scores = [f[1] for f in cached_frames]
                mean = statistics.mean(scores)
                stdev = statistics.stdev(scores)
                threshold = mean + self.adaptive_sigma * stdev

                self._log(f"Adaptive threshold: {threshold:.4f} (mean={mean:.4f}, stdev={stdev:.4f}, {self.adaptive_sigma}sigma)")

                # Filter frames above threshold
                timestamps = [
                    (ts, "scene_change (adaptive)")
                    for ts, score in cached_frames
                    if score > threshold
                ]

                self._log(f"Detected {len(timestamps)} scene changes (from cache)")
                return timestamps, None

            # No cache - get ALL scene scores for adaptive threshold calculation
            filter_expr = "scale=320:-1,select='gte(scene,0)',metadata=print:file=-"
            self._log(f"Analyzing scene scores for adaptive threshold...")
        else:
            # Fixed threshold mode
            filter_expr = f"scale=320:-1,select='gt(scene,{self.scene_threshold})',showinfo"

        # Build FFmpeg command
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "info",
        ]
        cmd.extend(decoder_args)
        cmd.extend([
            "-i", str(video_path),
            "-vf", filter_expr,
            "-f", "null",
            "-"
        ])

        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
        self._log(f"Running FFmpeg scene detection (video: {duration_str}, timeout: {timeout_seconds}s)...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            # Check for FFmpeg errors
            if result.returncode != 0 and "Error" in result.stderr:
                for line in result.stderr.split('\n'):
                    if 'Error' in line or 'error' in line:
                        return [], f"FFmpeg error: {line.strip()}"

            output = result.stdout + result.stderr

            if use_adaptive:
                # Parse all frame scores and timestamps for adaptive mode
                frame_pattern = re.compile(r'frame:(\d+)\s+pts:(\d+)\s+pts_time:([\d.]+)')
                score_pattern = re.compile(r'lavfi\.scene_score=([\d.]+)')

                frames = []  # List of (timestamp, score)
                lines = output.split('\n')

                i = 0
                while i < len(lines):
                    frame_match = frame_pattern.search(lines[i])
                    if frame_match and i + 1 < len(lines):
                        score_match = score_pattern.search(lines[i + 1])
                        if score_match:
                            ts = float(frame_match.group(3))
                            score = float(score_match.group(1))
                            frames.append((ts, score))
                            i += 2
                            continue
                    i += 1

                if len(frames) < 10:
                    return [], f"Not enough frames analyzed ({len(frames)})"

                # Save scores to cache for future reindexing
                self._save_scores_cache(video_path, frames)

                # Calculate adaptive threshold
                scores = [f[1] for f in frames]
                mean = statistics.mean(scores)
                stdev = statistics.stdev(scores)
                threshold = mean + self.adaptive_sigma * stdev

                self._log(f"Adaptive threshold: {threshold:.4f} (mean={mean:.4f}, stdev={stdev:.4f}, {self.adaptive_sigma}sigma)")

                # Filter frames above threshold
                timestamps = [
                    (ts, "scene_change (adaptive)")
                    for ts, score in frames
                    if score > threshold
                ]

                self._log(f"Detected {len(timestamps)} scene changes")
                return timestamps, None

            else:
                # Fixed threshold mode - parse pts_time from showinfo output
                timestamps = []
                pattern = re.compile(r'pts_time:([\d.]+)')

                for line in result.stderr.split('\n'):
                    if 'showinfo' in line and 'pts_time' in line:
                        match = pattern.search(line)
                        if match:
                            try:
                                ts = float(match.group(1))
                                timestamps.append((ts, "scene_change (ffmpeg)"))
                            except ValueError:
                                continue

                return timestamps, None

        except subprocess.TimeoutExpired:
            return [], f"FFmpeg timed out after {timeout_seconds}s"
        except FileNotFoundError:
            return [], "FFmpeg not found in PATH"
        except Exception as e:
            return [], f"FFmpeg failed: {str(e)}"

    def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration using ffprobe."""
        import subprocess

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(video_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            # Fallback to cv2
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            return frame_count / fps if fps > 0 else 0

    def _add_interval_samples(
        self,
        scene_timestamps: list[tuple[float, str]],
        duration: float
    ) -> list[tuple[float, str]]:
        """Add samples to ensure max_interval is respected.

        Args:
            scene_timestamps: Scene change timestamps from FFmpeg.
            duration: Video duration in seconds.

        Returns:
            Combined list of timestamps with interval fills.
        """
        all_samples = []

        # Always include first frame
        all_samples.append((0.0, "first_frame"))

        # Add scene changes, respecting min_interval
        last_time = 0.0
        for ts, reason in sorted(scene_timestamps):
            if ts - last_time >= self.min_interval:
                all_samples.append((ts, reason))
                last_time = ts

        # Fill gaps larger than max_interval
        filled = []
        prev_time = 0.0

        for ts, reason in sorted(all_samples):
            # Fill gap if too large
            while ts - prev_time > self.max_interval:
                fill_time = prev_time + self.max_interval
                if fill_time < ts - self.min_interval:
                    filled.append((fill_time, "max_interval"))
                    prev_time = fill_time
                else:
                    break

            filled.append((ts, reason))
            prev_time = ts

        # Fill remaining time until end
        while duration - prev_time > self.max_interval:
            fill_time = prev_time + self.max_interval
            filled.append((fill_time, "max_interval"))
            prev_time = fill_time

        deduped = {}
        for ts, reason in sorted(filled, key=lambda x: x[0]):
            if ts not in deduped:
                deduped[ts] = reason
            elif deduped[ts] == "max_interval" and reason != "max_interval":
                deduped[ts] = reason

        return [(ts, deduped[ts]) for ts in sorted(deduped)]

    def _extract_frame_at_timestamp(
        self,
        video_path: Path,
        timestamp: float,
        codec: Optional[str] = None
    ) -> Optional[np.ndarray]:
        """Extract a single frame at the given timestamp.

        Uses FFmpeg with input seeking for faster extraction, especially
        for AV1 videos where cv2 seeking is slow.

        Args:
            video_path: Path to video file.
            timestamp: Timestamp in seconds.
            codec: Video codec (for decoder selection). If None, auto-detects.

        Returns:
            Frame as numpy array (BGR), or None if extraction failed.
        """
        import subprocess
        import tempfile
        import os

        # Build FFmpeg command with input seeking (-ss before -i)
        decoder_args = []
        if codec in ('av1', 'av01'):
            decoder_args = ['-c:v', 'libdav1d']

        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                out_path = f.name

            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            ]
            cmd.extend(decoder_args)
            cmd.extend([
                '-ss', str(timestamp),
                '-i', str(video_path),
                '-frames:v', '1',
                '-q:v', '2',
                out_path
            ])

            result = subprocess.run(cmd, capture_output=True, timeout=30)

            if result.returncode == 0 and os.path.exists(out_path):
                frame = cv2.imread(out_path)
                os.unlink(out_path)
                return frame
            else:
                if os.path.exists(out_path):
                    os.unlink(out_path)
                return None

        except Exception:
            return None

    def _extract_frames_batch(
        self,
        video_path: Path,
        timestamps: list[float],
        codec: Optional[str] = None,
        epsilon: float = 0.01
    ) -> list[Optional[np.ndarray]]:
        """Extract multiple frames in a single FFmpeg run."""
        import subprocess
        import tempfile
        import os

        if not timestamps:
            return []

        decoder_args = []
        if codec in ('av1', 'av01'):
            decoder_args = ['-c:v', 'libdav1d']

        parts = []
        for ts in timestamps:
            start = max(0.0, ts - epsilon)
            end = ts + epsilon
            parts.append(f"between(t,{start:.3f},{end:.3f})")

        filter_expr = "+".join(parts)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_pattern = os.path.join(tmpdir, "%06d.png")
                cmd = [
                    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                ]
                cmd.extend(decoder_args)
                cmd.extend([
                    '-i', str(video_path),
                    '-vf', f"select='{filter_expr}',setpts=N/FRAME_RATE/TB",
                    '-vsync', '0',
                    output_pattern
                ])

                result = subprocess.run(cmd, capture_output=True, timeout=60)
                if result.returncode != 0:
                    return [None] * len(timestamps)

                files = sorted(
                    f for f in os.listdir(tmpdir)
                    if f.lower().endswith(".png")
                )
                frames = []
                for fname in files:
                    frame = cv2.imread(os.path.join(tmpdir, fname))
                    frames.append(frame)

                if len(frames) < len(timestamps):
                    frames.extend([None] * (len(timestamps) - len(frames)))
                return frames[:len(timestamps)]
        except Exception:
            return [None] * len(timestamps)

    def list_timestamps(self, video_path: Path) -> list[tuple[float, str]]:
        """Return timestamps and reasons without extracting frames."""
        duration = self._get_video_duration(video_path)
        if duration <= 0:
            self._log("Warning: Could not determine video duration")
            return []

        scene_timestamps, error = self._detect_scene_timestamps(video_path, duration)

        if error:
            self._log(f"Scene detection failed: {error}")
            self._log(f"Falling back to {self.max_interval}s interval sampling")
            scene_timestamps = []
        elif len(scene_timestamps) == 0:
            self._log(f"No scene changes detected (threshold={self.scene_threshold})")
            self._log(f"Using {self.max_interval}s interval sampling")
        else:
            self._log(f"Detected {len(scene_timestamps)} scene changes")

        self._last_detection_result = {
            "scene_changes": len(scene_timestamps),
            "error": error,
            "duration": duration
        }

        return self._add_interval_samples(scene_timestamps, duration)

    def extract_frames(self, video_path: Path, timestamps: list[tuple[float, str]]) -> list[Optional[np.ndarray]]:
        """Extract frames for a list of timestamps with reasons."""
        codec = self._detect_video_codec(video_path)
        frames = []
        batch_size = 150

        for start in range(0, len(timestamps), batch_size):
            batch = timestamps[start:start + batch_size]
            batch_times = [ts for ts, _ in batch]
            frames.extend(self._extract_frames_batch(video_path, batch_times, codec=codec))

        return frames

    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample frames using FFmpeg scene detection.

        This is significantly faster than Python-based methods because:
        1. FFmpeg uses hardware-accelerated decoding
        2. Only selected frames are decoded, not every frame
        3. Scene detection runs in native code
        """
        timestamps_with_reasons = self.list_timestamps(video_path)
        if not timestamps_with_reasons:
            return

        self._log(f"Extracting {len(timestamps_with_reasons)} frames...")

        frames = self.extract_frames(video_path, timestamps_with_reasons)
        for (timestamp, reason), frame in zip(timestamps_with_reasons, frames):
            if frame is not None:
                yield SampledFrame(
                    timestamp=timestamp,
                    frame=frame,
                    reason=reason
                )


def create_sampler(config: SamplerConfig) -> FrameSampler:
    """Factory function to create frame sampler.

    Args:
        config: Sampler configuration.

    Returns:
        Configured FrameSampler instance.
    """
    samplers = {
        SamplingStrategy.FIXED: lambda: FixedIntervalSampler(
            interval=config.fixed_interval
        ),
        SamplingStrategy.SCENE_CHANGE: lambda: SceneChangeSampler(
            threshold=config.scene_threshold,
            min_interval=config.min_interval
        ),
        SamplingStrategy.PERCEPTUAL_HASH: lambda: PerceptualHashSampler(
            interval=config.fixed_interval,
            hash_threshold=config.hash_threshold
        ),
        SamplingStrategy.HYBRID: lambda: HybridSampler(
            min_interval=config.min_interval,
            max_interval=config.max_interval,
            scene_threshold=config.scene_threshold
        ),
        SamplingStrategy.FFMPEG_SCENE: lambda: FFmpegSceneSampler(
            scene_threshold=config.ffmpeg_scene_threshold,
            min_interval=config.min_interval,
            max_interval=config.max_interval,
            adaptive_sigma=config.ffmpeg_adaptive_sigma
        ),
    }

    factory = samplers.get(config.strategy)
    if factory is None:
        raise ValueError(f"Unknown sampling strategy: {config.strategy}. "
                        f"Available: {list(samplers.keys())}")

    return factory()
