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
    ffmpeg_scene_threshold: float = 0.3  # FFmpeg scene score (0-1), lower = more sensitive


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
        scene_threshold: float = 0.3,
        min_interval: float = 1.0,
        max_interval: float = 30.0
    ):
        """Initialize FFmpeg scene sampler.

        Args:
            scene_threshold: FFmpeg scene change threshold (0-1).
                            Lower = more sensitive. Default 0.3 works well.
            min_interval: Minimum seconds between samples.
            max_interval: Maximum seconds between samples (fallback).
        """
        self.scene_threshold = scene_threshold
        self.min_interval = min_interval
        self.max_interval = max_interval

    def _detect_scene_timestamps(self, video_path: Path) -> list[tuple[float, str]]:
        """Use FFmpeg to detect scene change timestamps.

        Uses ffmpeg -vf with select and showinfo filters, which handles
        paths with special characters better than ffprobe's movie filter.

        Returns:
            List of (timestamp, reason) tuples.
        """
        import subprocess
        import re

        # FFmpeg command using -vf filter (better path handling than movie filter)
        # Scale down to 320px width for faster processing (4-5x speedup)
        # Scene detection only needs to detect overall frame changes, not fine detail
        # showinfo outputs frame details including pts_time
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"scale=320:-1,select='gt(scene,{self.scene_threshold})',showinfo",
            "-f", "null",
            "-"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            # Parse pts_time from showinfo output (in stderr)
            timestamps = []
            # Pattern matches: pts_time:123.456
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

            return timestamps

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # FFmpeg not available, return empty list
            return []

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

        return sorted(set(filled), key=lambda x: x[0])

    def _extract_frame_at_timestamp(
        self,
        video_path: Path,
        timestamp: float
    ) -> Optional[np.ndarray]:
        """Extract a single frame at the given timestamp using cv2.

        Args:
            video_path: Path to video file.
            timestamp: Timestamp in seconds.

        Returns:
            Frame as numpy array, or None if extraction failed.
        """
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ret, frame = cap.read()
        cap.release()
        return frame if ret else None

    def sample(self, video_path: Path) -> Iterator[SampledFrame]:
        """Sample frames using FFmpeg scene detection.

        This is significantly faster than Python-based methods because:
        1. FFmpeg uses hardware-accelerated decoding
        2. Only selected frames are decoded, not every frame
        3. Scene detection runs in native code
        """
        # Get video duration
        duration = self._get_video_duration(video_path)
        if duration <= 0:
            return

        # Detect scene changes using FFmpeg
        scene_timestamps = self._detect_scene_timestamps(video_path)

        # Add interval samples to fill gaps
        all_timestamps = self._add_interval_samples(scene_timestamps, duration)

        # Extract frames at each timestamp
        for timestamp, reason in all_timestamps:
            frame = self._extract_frame_at_timestamp(video_path, timestamp)
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
            max_interval=config.max_interval
        ),
    }

    factory = samplers.get(config.strategy)
    if factory is None:
        raise ValueError(f"Unknown sampling strategy: {config.strategy}. "
                        f"Available: {list(samplers.keys())}")

    return factory()
