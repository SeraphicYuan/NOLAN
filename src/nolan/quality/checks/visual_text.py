"""
Visual Text Verification Check

Renders expected text using a known-good method and compares against
the video frame to detect text rendering issues without requiring OCR.
"""

from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional
import subprocess
import tempfile
import os

from ..types import QAIssue, IssueType, IssueSeverity


def create_reference_text_image(
    text: str,
    width: int = 1920,
    height: int = 1080,
    font_path: str = "C:/Windows/Fonts/arialbd.ttf",
    font_size: int = 80,
    bg_color: Tuple[int, int, int] = (26, 26, 26),
    text_color: str = "white",
) -> Optional[bytes]:
    """
    Create a reference image with properly rendered text using PIL.
    Returns PNG bytes.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Load font
        try:
            font = ImageFont.truetype(font_path, font_size)
        except OSError:
            # Fallback to default font
            font = ImageFont.load_default()

        # Get text size and center it
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Draw text
        draw.text((x, y), text, fill=text_color, font=font)

        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()

    except ImportError:
        return None
    except Exception:
        return None


def extract_text_region(
    frame_data: bytes,
    center_crop: float = 0.5,
) -> Optional[bytes]:
    """
    Extract the center region of a frame where text is expected.
    Returns cropped PNG bytes.
    """
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(frame_data))
        width, height = img.size

        # Crop center region
        crop_w = int(width * center_crop)
        crop_h = int(height * center_crop)
        left = (width - crop_w) // 2
        top = (height - crop_h) // 2

        cropped = img.crop((left, top, left + crop_w, top + crop_h))

        buffer = io.BytesIO()
        cropped.save(buffer, format='PNG')
        return buffer.getvalue()

    except Exception:
        return None


def calculate_structural_similarity(
    img1_bytes: bytes,
    img2_bytes: bytes,
) -> float:
    """
    Calculate structural similarity between two images.
    Returns value between 0 (different) and 1 (identical).
    """
    try:
        from PIL import Image
        import io

        img1 = Image.open(io.BytesIO(img1_bytes)).convert('L')  # Grayscale
        img2 = Image.open(io.BytesIO(img2_bytes)).convert('L')

        # Resize to same size for comparison
        size = (200, 100)  # Small size for fast comparison
        img1 = img1.resize(size)
        img2 = img2.resize(size)

        # Get pixel data
        pixels1 = list(img1.getdata())
        pixels2 = list(img2.getdata())

        if len(pixels1) != len(pixels2):
            return 0.0

        # Calculate normalized cross-correlation
        mean1 = sum(pixels1) / len(pixels1)
        mean2 = sum(pixels2) / len(pixels2)

        numerator = sum((p1 - mean1) * (p2 - mean2) for p1, p2 in zip(pixels1, pixels2))
        denom1 = sum((p1 - mean1) ** 2 for p1 in pixels1) ** 0.5
        denom2 = sum((p2 - mean2) ** 2 for p2 in pixels2) ** 0.5

        if denom1 == 0 or denom2 == 0:
            return 0.0

        correlation = numerator / (denom1 * denom2)

        # Normalize to 0-1 range
        return (correlation + 1) / 2

    except Exception:
        return 0.0


def check_text_rendering(
    video_path: Path,
    expected_text: str,
    timestamp: float = None,
    similarity_threshold: float = 0.7,
    ffmpeg_path: str = "ffmpeg",
) -> Tuple[List[QAIssue], Dict[str, Any]]:
    """
    Check if text in video matches expected text visually.

    This uses a reference-comparison approach:
    1. Render expected text with PIL (known-good)
    2. Extract frame from video
    3. Compare using structural similarity

    Returns (issues, metadata).
    """
    issues = []
    metadata = {"visual_text_check": {}}

    try:
        # Get video duration if timestamp not specified
        if timestamp is None:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "csv=p=0",
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            duration = float(result.stdout.strip())
            timestamp = duration * 0.5  # Middle frame

        # Extract frame from video
        cmd = [
            ffmpeg_path,
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-"
        ]
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0 or not result.stdout:
            metadata["visual_text_check"]["error"] = "Failed to extract frame"
            return issues, metadata

        video_frame = result.stdout
        metadata["visual_text_check"]["frame_extracted"] = True

        # Create reference image with expected text
        reference = create_reference_text_image(expected_text)
        if not reference:
            metadata["visual_text_check"]["error"] = "Failed to create reference"
            return issues, metadata

        metadata["visual_text_check"]["reference_created"] = True

        # Compare frames
        similarity = calculate_structural_similarity(video_frame, reference)
        metadata["visual_text_check"]["similarity"] = similarity
        metadata["visual_text_check"]["threshold"] = similarity_threshold

        if similarity < similarity_threshold:
            issues.append(QAIssue(
                type=IssueType.FONT_RENDERING,
                severity=IssueSeverity.ERROR,
                message=f"Text rendering quality low: similarity {similarity:.2f} < {similarity_threshold}",
                details={
                    "expected_text": expected_text,
                    "similarity": similarity,
                    "threshold": similarity_threshold
                },
                auto_fixable=True,
                fix_strategy="rerender_with_pil_text"
            ))

    except Exception as e:
        metadata["visual_text_check"]["error"] = str(e)

    return issues, metadata
