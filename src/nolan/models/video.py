"""Video-related data models."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class InferredContext:
    """Inferred context from visual + audio analysis."""
    people: List[str] = field(default_factory=list)
    location: Optional[str] = None
    story_context: Optional[str] = None
    objects: List[str] = field(default_factory=list)
    confidence: str = "low"  # high, medium, low

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "people": self.people,
            "location": self.location,
            "story_context": self.story_context,
            "objects": self.objects,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InferredContext":
        """Create from dictionary."""
        if data is None:
            return cls()
        return cls(
            people=data.get("people", []),
            location=data.get("location"),
            story_context=data.get("story_context"),
            objects=data.get("objects", []),
            confidence=data.get("confidence", "low"),
        )


@dataclass
class VideoSegment:
    """A segment of indexed video with hybrid data."""
    video_path: str
    timestamp_start: float
    timestamp_end: float
    frame_description: str
    transcript: Optional[str] = None
    combined_summary: Optional[str] = None
    inferred_context: Optional[InferredContext] = None
    sample_reason: Optional[str] = None

    # Legacy alias for backward compatibility
    @property
    def timestamp(self) -> float:
        """Legacy timestamp property."""
        return self.timestamp_start

    @property
    def description(self) -> str:
        """Legacy description property (returns combined or frame description)."""
        return self.combined_summary or self.frame_description

    @property
    def timestamp_formatted(self) -> str:
        """Format timestamp as MM:SS."""
        minutes = int(self.timestamp_start // 60)
        seconds = int(self.timestamp_start % 60)
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def duration(self) -> float:
        """Duration of this segment in seconds."""
        return self.timestamp_end - self.timestamp_start
