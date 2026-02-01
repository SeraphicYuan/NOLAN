"""
Quality Protocol - Main validation and fix logic.

This module provides automated quality assurance for rendered video content.
"""

import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import tempfile
import os

from .types import (
    QAConfig, QAResult, QAIssue,
    IssueType, IssueSeverity
)


class QualityProtocol:
    """
    Quality validation and auto-fix for rendered video content.

    Usage:
        qa = QualityProtocol()
        result = qa.validate(
            video_path="output.mp4",
            expected_text="WE ARE TIRED",
            expected_duration=7.0
        )

        if not result.passed and result.auto_fixable:
            fixed_path = qa.fix(result)
    """

    def __init__(self, config: Optional[QAConfig] = None):
        self.config = config or QAConfig()
        self._ffprobe_path = "ffprobe"
        self._ffmpeg_path = "ffmpeg"

    def validate(
        self,
        video_path: str,
        expected_text: Optional[str] = None,
        expected_duration: Optional[float] = None,
        expected_resolution: Optional[Tuple[int, int]] = None,
    ) -> QAResult:
        """
        Run quality validation on a rendered video.

        Args:
            video_path: Path to the video file to validate
            expected_text: Text that should appear in the video
            expected_duration: Expected duration in seconds
            expected_resolution: Expected (width, height)

        Returns:
            QAResult with validation results and any issues found
        """
        video_path = Path(video_path)
        issues: List[QAIssue] = []
        checks_run: List[str] = []
        metadata: Dict[str, Any] = {}

        # Property checks (always run)
        if self.config.check_properties:
            prop_issues, prop_meta = self._check_properties(
                video_path,
                expected_duration,
                expected_resolution
            )
            issues.extend(prop_issues)
            metadata.update(prop_meta)
            checks_run.append("properties")

        # Visual checks
        if self.config.check_visual:
            visual_issues, visual_meta = self._check_visual(video_path)
            issues.extend(visual_issues)
            metadata.update(visual_meta)
            checks_run.append("visual")

        # Text checks (OCR - slow, optional)
        if self.config.check_text and expected_text:
            text_issues, text_meta = self._check_text(video_path, expected_text)
            issues.extend(text_issues)
            metadata.update(text_meta)
            checks_run.append("text_ocr")

        # Determine if passed (no ERROR or CRITICAL issues)
        passed = not any(
            issue.severity in (IssueSeverity.ERROR, IssueSeverity.CRITICAL)
            for issue in issues
        )

        return QAResult(
            passed=passed,
            video_path=video_path,
            issues=issues,
            checks_run=checks_run,
            metadata=metadata
        )

    def _check_properties(
        self,
        video_path: Path,
        expected_duration: Optional[float],
        expected_resolution: Optional[Tuple[int, int]]
    ) -> Tuple[List[QAIssue], Dict[str, Any]]:
        """Check video file properties using ffprobe."""
        issues = []
        metadata = {}

        # Check file exists
        if not video_path.exists():
            issues.append(QAIssue(
                type=IssueType.FILE_MISSING,
                severity=IssueSeverity.CRITICAL,
                message=f"Video file not found: {video_path}",
                auto_fixable=False
            ))
            return issues, metadata

        # Check file not empty
        file_size = video_path.stat().st_size
        metadata["file_size"] = file_size

        if file_size == 0:
            issues.append(QAIssue(
                type=IssueType.FILE_EMPTY,
                severity=IssueSeverity.CRITICAL,
                message="Video file is empty (0 bytes)",
                auto_fixable=False
            ))
            return issues, metadata

        # Get video properties using ffprobe
        try:
            props = self._get_video_properties(video_path)
            metadata.update(props)
        except Exception as e:
            issues.append(QAIssue(
                type=IssueType.FILE_MISSING,
                severity=IssueSeverity.CRITICAL,
                message=f"Failed to read video properties: {e}",
                auto_fixable=False
            ))
            return issues, metadata

        # Check duration
        if expected_duration is not None:
            actual_duration = props.get("duration", 0)
            duration_diff = abs(actual_duration - expected_duration)

            if duration_diff > self.config.duration_tolerance:
                issues.append(QAIssue(
                    type=IssueType.WRONG_DURATION,
                    severity=IssueSeverity.ERROR,
                    message=f"Duration mismatch: expected {expected_duration}s, got {actual_duration}s",
                    details={
                        "expected": expected_duration,
                        "actual": actual_duration,
                        "difference": duration_diff
                    },
                    auto_fixable=True,
                    fix_strategy="rerender_with_correct_duration"
                ))

        # Check resolution
        if expected_resolution is not None:
            actual_width = props.get("width", 0)
            actual_height = props.get("height", 0)

            if (actual_width, actual_height) != expected_resolution:
                issues.append(QAIssue(
                    type=IssueType.WRONG_RESOLUTION,
                    severity=IssueSeverity.ERROR,
                    message=f"Resolution mismatch: expected {expected_resolution}, got ({actual_width}, {actual_height})",
                    details={
                        "expected": expected_resolution,
                        "actual": (actual_width, actual_height)
                    },
                    auto_fixable=True,
                    fix_strategy="rerender_with_correct_resolution"
                ))

        return issues, metadata

    def _check_visual(self, video_path: Path) -> Tuple[List[QAIssue], Dict[str, Any]]:
        """Check visual content of video frames."""
        issues = []
        metadata = {"frames_checked": []}

        try:
            # Get video duration first
            props = self._get_video_properties(video_path)
            duration = props.get("duration", 0)

            if duration == 0:
                return issues, metadata

            # Extract and check frames at sample points
            for sample_point in self.config.frame_sample_points:
                timestamp = duration * sample_point
                frame_data = self._extract_frame(video_path, timestamp)

                if frame_data:
                    is_blank, brightness = self._analyze_frame(frame_data)
                    metadata["frames_checked"].append({
                        "timestamp": timestamp,
                        "is_blank": is_blank,
                        "brightness": brightness
                    })

                    if is_blank:
                        issues.append(QAIssue(
                            type=IssueType.BLANK_FRAME,
                            severity=IssueSeverity.WARNING,
                            message=f"Blank/dark frame detected at {timestamp:.1f}s",
                            details={"timestamp": timestamp, "brightness": brightness},
                            auto_fixable=False
                        ))

        except Exception as e:
            metadata["visual_check_error"] = str(e)

        return issues, metadata

    def _check_text(
        self,
        video_path: Path,
        expected_text: str
    ) -> Tuple[List[QAIssue], Dict[str, Any]]:
        """
        Check text content using OCR.
        Note: Requires pytesseract and tesseract-ocr to be installed.
        """
        issues = []
        metadata = {"ocr_results": []}

        try:
            # Try to import pytesseract
            import pytesseract
            from PIL import Image
        except ImportError:
            metadata["ocr_error"] = "pytesseract not installed"
            return issues, metadata

        try:
            props = self._get_video_properties(video_path)
            duration = props.get("duration", 0)

            # Extract middle frame for OCR
            timestamp = duration * 0.5
            frame_path = self._extract_frame_to_file(video_path, timestamp)

            if frame_path and os.path.exists(frame_path):
                try:
                    image = Image.open(frame_path)
                    ocr_text = pytesseract.image_to_string(image)
                    ocr_text = ocr_text.strip().upper()  # Normalize

                    metadata["ocr_results"].append({
                        "timestamp": timestamp,
                        "detected_text": ocr_text
                    })

                    # Compare with expected text
                    expected_normalized = expected_text.strip().upper()
                    match_ratio = self._text_similarity(expected_normalized, ocr_text)

                    metadata["text_match_ratio"] = match_ratio

                    if match_ratio < self.config.text_match_threshold:
                        # Determine specific issue
                        if expected_normalized not in ocr_text and len(ocr_text) < len(expected_normalized):
                            issues.append(QAIssue(
                                type=IssueType.TEXT_CUTOFF,
                                severity=IssueSeverity.ERROR,
                                message=f"Text appears cut off: expected '{expected_text}', detected '{ocr_text}'",
                                details={
                                    "expected": expected_text,
                                    "detected": ocr_text,
                                    "match_ratio": match_ratio
                                },
                                auto_fixable=True,
                                fix_strategy="rerender_with_fallback_font"
                            ))
                        else:
                            issues.append(QAIssue(
                                type=IssueType.TEXT_MISMATCH,
                                severity=IssueSeverity.ERROR,
                                message=f"Text mismatch: expected '{expected_text}', detected '{ocr_text}'",
                                details={
                                    "expected": expected_text,
                                    "detected": ocr_text,
                                    "match_ratio": match_ratio
                                },
                                auto_fixable=True,
                                fix_strategy="rerender_with_fallback_font"
                            ))
                finally:
                    # Cleanup temp frame
                    if os.path.exists(frame_path):
                        os.unlink(frame_path)

        except Exception as e:
            metadata["ocr_error"] = str(e)

        return issues, metadata

    def _get_video_properties(self, video_path: Path) -> Dict[str, Any]:
        """Get video properties using ffprobe."""
        cmd = [
            self._ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,nb_frames,r_frame_rate",
            "-of", "json",
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        data = json.loads(result.stdout)

        if not data.get("streams"):
            raise RuntimeError("No video streams found")

        stream = data["streams"][0]

        # Parse frame rate (can be "30/1" format)
        fps_str = stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(fps_str)

        return {
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "duration": float(stream.get("duration", 0)),
            "nb_frames": int(stream.get("nb_frames", 0)),
            "fps": fps
        }

    def _extract_frame(self, video_path: Path, timestamp: float) -> Optional[bytes]:
        """Extract a frame as raw bytes."""
        cmd = [
            self._ffmpeg_path,
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-"
        ]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0 and result.stdout:
            return result.stdout
        return None

    def _extract_frame_to_file(self, video_path: Path, timestamp: float) -> Optional[str]:
        """Extract a frame to a temp file and return path."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name

        cmd = [
            self._ffmpeg_path,
            "-y",
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            temp_path
        ]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0 and os.path.exists(temp_path):
            return temp_path
        return None

    def _analyze_frame(self, frame_data: bytes) -> Tuple[bool, float]:
        """
        Analyze a frame to check if it's blank/dark.
        Returns (is_blank, brightness_ratio).
        """
        try:
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(frame_data))
            # Convert to grayscale
            gray = image.convert("L")

            # Calculate average brightness
            pixels = list(gray.getdata())
            avg_brightness = sum(pixels) / len(pixels) if pixels else 0

            # Normalize to 0-1
            brightness_ratio = avg_brightness / 255.0

            # Consider blank if very dark
            is_blank = brightness_ratio < self.config.blank_frame_threshold

            return is_blank, brightness_ratio

        except Exception:
            return False, 0.5  # Default to non-blank if analysis fails

    def _text_similarity(self, expected: str, detected: str) -> float:
        """Calculate similarity ratio between two strings."""
        if not expected:
            return 1.0 if not detected else 0.0

        # Simple character-level matching
        expected_chars = set(expected.replace(" ", ""))
        detected_chars = set(detected.replace(" ", ""))

        if not expected_chars:
            return 1.0

        common = expected_chars & detected_chars
        return len(common) / len(expected_chars)

    def fix(self, result: QAResult, render_func=None, **render_kwargs) -> Optional[Path]:
        """
        Attempt to fix issues found during validation.

        Args:
            result: QAResult from validate()
            render_func: Function to call for re-rendering
            **render_kwargs: Arguments to pass to render_func

        Returns:
            Path to fixed video, or None if fix failed
        """
        if not result.issues or not result.auto_fixable:
            return None

        # Collect fix strategies
        strategies = set(
            issue.fix_strategy
            for issue in result.issues
            if issue.fix_strategy
        )

        # Apply fixes
        for attempt in range(self.config.max_fix_attempts):
            print(f"[QA] Fix attempt {attempt + 1}/{self.config.max_fix_attempts}")

            # Try different fonts if font-related issues
            if "rerender_with_fallback_font" in strategies and render_func:
                for font in self.config.fallback_fonts:
                    if os.path.exists(font):
                        print(f"[QA] Trying font: {font}")
                        render_kwargs["font"] = font

                        try:
                            output_path = render_func(**render_kwargs)

                            # Re-validate
                            new_result = self.validate(
                                output_path,
                                expected_text=render_kwargs.get("expected_text"),
                                expected_duration=render_kwargs.get("expected_duration"),
                                expected_resolution=render_kwargs.get("expected_resolution")
                            )

                            if new_result.passed:
                                print(f"[QA] Fix successful with font: {font}")
                                return Path(output_path)

                        except Exception as e:
                            print(f"[QA] Re-render failed: {e}")
                            continue

        print("[QA] All fix attempts exhausted")
        return None
