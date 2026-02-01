"""Quality Protocol Types and Data Classes."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path


class IssueType(Enum):
    """Types of quality issues that can be detected."""
    # Property issues
    FILE_MISSING = "file_missing"
    FILE_EMPTY = "file_empty"
    WRONG_DURATION = "wrong_duration"
    WRONG_RESOLUTION = "wrong_resolution"

    # Visual issues
    BLANK_FRAME = "blank_frame"
    CONTENT_CUTOFF = "content_cutoff"
    VISUAL_ARTIFACT = "visual_artifact"

    # Text issues
    TEXT_MISMATCH = "text_mismatch"
    TEXT_CUTOFF = "text_cutoff"
    FONT_RENDERING = "font_rendering"
    MISSING_CHARACTERS = "missing_characters"


class IssueSeverity(Enum):
    """Severity levels for quality issues."""
    WARNING = "warning"      # Minor issue, output usable
    ERROR = "error"          # Significant issue, needs fix
    CRITICAL = "critical"    # Output unusable


@dataclass
class QAIssue:
    """Represents a single quality issue found during validation."""
    type: IssueType
    severity: IssueSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    auto_fixable: bool = False
    fix_strategy: Optional[str] = None

    def __str__(self):
        return f"[{self.severity.value.upper()}] {self.type.value}: {self.message}"


@dataclass
class QAResult:
    """Result of quality validation."""
    passed: bool
    video_path: Path
    issues: List[QAIssue] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def auto_fixable(self) -> bool:
        """Returns True if all issues can be auto-fixed."""
        if not self.issues:
            return False
        return all(issue.auto_fixable for issue in self.issues)

    @property
    def has_errors(self) -> bool:
        """Returns True if there are ERROR or CRITICAL issues."""
        return any(
            issue.severity in (IssueSeverity.ERROR, IssueSeverity.CRITICAL)
            for issue in self.issues
        )

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    def summary(self) -> str:
        """Return a human-readable summary."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"Quality Check: {status}",
            f"Video: {self.video_path}",
            f"Checks run: {', '.join(self.checks_run)}",
        ]

        if self.issues:
            lines.append(f"Issues found: {len(self.issues)} ({self.error_count} errors, {self.warning_count} warnings)")
            for issue in self.issues:
                lines.append(f"  - {issue}")

        return "\n".join(lines)


@dataclass
class QAConfig:
    """Configuration for quality validation."""
    # Check toggles
    check_properties: bool = True
    check_visual: bool = True
    check_text: bool = False  # OCR is slow, disabled by default

    # Tolerances
    duration_tolerance: float = 0.5  # seconds
    text_match_threshold: float = 0.90  # 90% match required

    # Fix settings
    auto_fix: bool = True
    max_fix_attempts: int = 3

    # Font fallback chain for text issues
    fallback_fonts: List[str] = field(default_factory=lambda: [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/verdana.ttf",
    ])

    # Frame extraction settings
    frame_sample_points: List[float] = field(default_factory=lambda: [0.1, 0.5, 0.9])

    # Visual thresholds
    blank_frame_threshold: float = 0.05  # 5% non-black pixels to consider non-blank
