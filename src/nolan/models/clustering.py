"""Clustering-related data models."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from nolan.models.video import VideoSegment


@dataclass
class SceneCluster:
    """A cluster of continuous video segments representing a story moment."""

    id: int
    segments: List["VideoSegment"]
    cluster_summary: Optional[str] = None

    @property
    def timestamp_start(self) -> float:
        """Start timestamp of the cluster."""
        if not self.segments:
            return 0.0
        return self.segments[0].timestamp_start

    @property
    def timestamp_end(self) -> float:
        """End timestamp of the cluster."""
        if not self.segments:
            return 0.0
        return self.segments[-1].timestamp_end

    @property
    def duration(self) -> float:
        """Total duration of the cluster in seconds."""
        return self.timestamp_end - self.timestamp_start

    @property
    def timestamp_formatted(self) -> str:
        """Format timestamp as MM:SS - MM:SS."""
        start_min = int(self.timestamp_start // 60)
        start_sec = int(self.timestamp_start % 60)
        end_min = int(self.timestamp_end // 60)
        end_sec = int(self.timestamp_end % 60)
        return f"{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}"

    @property
    def people(self) -> List[str]:
        """Unique people across all segments."""
        people_set = set()
        for seg in self.segments:
            if seg.inferred_context and seg.inferred_context.people:
                people_set.update(seg.inferred_context.people)
        return sorted(people_set)

    @property
    def locations(self) -> List[str]:
        """Unique locations across all segments."""
        locations = set()
        for seg in self.segments:
            if seg.inferred_context and seg.inferred_context.location:
                loc = seg.inferred_context.location
                # Handle location as list or string
                if isinstance(loc, list):
                    for item in loc:
                        if item:
                            locations.add(str(item))
                elif loc:
                    locations.add(str(loc))
        return sorted(locations)

    @property
    def combined_transcript(self) -> str:
        """Combined transcript from all segments."""
        transcripts = []
        for seg in self.segments:
            if seg.transcript:
                transcripts.append(seg.transcript.strip())
        return " ".join(transcripts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "id": self.id,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "timestamp_formatted": self.timestamp_formatted,
            "duration": self.duration,
            "segment_count": len(self.segments),
            "cluster_summary": self.cluster_summary,
            "people": self.people,
            "locations": self.locations,
            "combined_transcript": self.combined_transcript,
            "segments": [
                {
                    "timestamp_start": s.timestamp_start,
                    "timestamp_end": s.timestamp_end,
                    "frame_description": s.frame_description,
                    "transcript": s.transcript,
                    "combined_summary": s.combined_summary,
                }
                for s in self.segments
            ]
        }
