"""Scene clustering for grouping continuous segments into story moments."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from nolan.indexer import VideoSegment, InferredContext


@dataclass
class SceneCluster:
    """A cluster of continuous video segments representing a story moment."""

    id: int
    segments: List[VideoSegment]
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
                locations.add(seg.inferred_context.location)
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


def _normalize_person(name: str) -> str:
    """Normalize person name for comparison."""
    # Lowercase and strip common prefixes/suffixes
    name = name.lower().strip()
    # Remove common descriptors
    for prefix in ["male ", "female ", "man ", "woman ", "the "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _people_overlap(people1: List[str], people2: List[str]) -> float:
    """Calculate overlap ratio between two people lists."""
    if not people1 or not people2:
        return 0.0

    normalized1 = {_normalize_person(p) for p in people1}
    normalized2 = {_normalize_person(p) for p in people2}

    intersection = normalized1 & normalized2
    union = normalized1 | normalized2

    if not union:
        return 0.0

    return len(intersection) / len(union)


def _location_similar(loc1: Optional[str], loc2: Optional[str]) -> bool:
    """Check if two locations are similar."""
    if not loc1 or not loc2:
        return False

    loc1 = loc1.lower().strip()
    loc2 = loc2.lower().strip()

    # Exact match
    if loc1 == loc2:
        return True

    # One contains the other
    if loc1 in loc2 or loc2 in loc1:
        return True

    # Share significant words
    words1 = set(loc1.split())
    words2 = set(loc2.split())
    # Remove common words
    stopwords = {"the", "a", "an", "in", "at", "on", "of", "with"}
    words1 -= stopwords
    words2 -= stopwords

    if words1 and words2:
        overlap = len(words1 & words2) / min(len(words1), len(words2))
        return overlap >= 0.5

    return False


def should_cluster_together(seg1: VideoSegment, seg2: VideoSegment,
                           max_gap: float = 2.0,
                           min_people_overlap: float = 0.3) -> bool:
    """Determine if two adjacent segments should be in the same cluster.

    Args:
        seg1: First segment (earlier in time).
        seg2: Second segment (later in time).
        max_gap: Maximum time gap between segments to consider clustering.
        min_people_overlap: Minimum Jaccard overlap for people to cluster.

    Returns:
        True if segments should be clustered together.
    """
    # Check time continuity - segments must be adjacent
    gap = seg2.timestamp_start - seg1.timestamp_end
    if gap > max_gap:
        return False

    # If no context available, cluster by time only
    ctx1 = seg1.inferred_context
    ctx2 = seg2.inferred_context

    if not ctx1 or not ctx2:
        # Cluster if continuous (small gap)
        return gap <= max_gap

    # Check people overlap
    if ctx1.people and ctx2.people:
        overlap = _people_overlap(ctx1.people, ctx2.people)
        if overlap >= min_people_overlap:
            return True

    # Check location similarity
    if _location_similar(ctx1.location, ctx2.location):
        return True

    # Check story context similarity (basic keyword overlap)
    if ctx1.story_context and ctx2.story_context:
        words1 = set(ctx1.story_context.lower().split())
        words2 = set(ctx2.story_context.lower().split())
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "at", "on", "of", "to", "and"}
        words1 -= stopwords
        words2 -= stopwords
        if words1 and words2:
            overlap = len(words1 & words2) / min(len(words1), len(words2))
            if overlap >= 0.3:
                return True

    # Default: don't cluster if no strong signal
    return False


def cluster_segments(segments: List[VideoSegment],
                    max_gap: float = 2.0,
                    min_people_overlap: float = 0.3) -> List[SceneCluster]:
    """Cluster continuous segments into story moments.

    Args:
        segments: List of segments sorted by timestamp.
        max_gap: Maximum time gap to consider segments adjacent.
        min_people_overlap: Minimum people overlap for clustering.

    Returns:
        List of SceneCluster objects.
    """
    if not segments:
        return []

    # Sort by timestamp
    sorted_segments = sorted(segments, key=lambda s: s.timestamp_start)

    clusters = []
    current_cluster_segments = [sorted_segments[0]]
    cluster_id = 0

    for i in range(1, len(sorted_segments)):
        prev_seg = sorted_segments[i - 1]
        curr_seg = sorted_segments[i]

        if should_cluster_together(prev_seg, curr_seg, max_gap, min_people_overlap):
            current_cluster_segments.append(curr_seg)
        else:
            # Start new cluster
            clusters.append(SceneCluster(
                id=cluster_id,
                segments=current_cluster_segments
            ))
            cluster_id += 1
            current_cluster_segments = [curr_seg]

    # Don't forget the last cluster
    if current_cluster_segments:
        clusters.append(SceneCluster(
            id=cluster_id,
            segments=current_cluster_segments
        ))

    return clusters


class ClusterAnalyzer:
    """Generates summaries for scene clusters using LLM."""

    def __init__(self, llm_client, concurrency: int = 10):
        """Initialize cluster analyzer.

        Args:
            llm_client: LLM client for text generation.
            concurrency: Max concurrent API calls for batch processing.
        """
        self.llm = llm_client
        self.concurrency = concurrency

    async def generate_cluster_summary(self, cluster: SceneCluster) -> str:
        """Generate a summary for a scene cluster.

        Args:
            cluster: The cluster to summarize.

        Returns:
            Summary string.
        """
        # Build context from segments
        segment_summaries = []
        for seg in cluster.segments:
            summary = seg.combined_summary or seg.frame_description
            segment_summaries.append(f"- {summary}")

        prompt = f"""Analyze this sequence of continuous video segments and provide a cohesive summary of the story moment they represent.

SEGMENTS ({len(cluster.segments)} total, {cluster.duration:.1f}s duration):
{chr(10).join(segment_summaries)}

TRANSCRIPT:
{cluster.combined_transcript or "(no transcript available)"}

PEOPLE APPEARING: {", ".join(cluster.people) if cluster.people else "(none identified)"}
LOCATIONS: {", ".join(cluster.locations) if cluster.locations else "(none identified)"}

Provide a 2-3 sentence summary that captures:
1. What's happening in this story moment
2. The key characters/elements involved
3. The emotional or narrative significance

Respond with ONLY the summary, no additional formatting."""

        try:
            response = await self.llm.generate(prompt)
            return response.strip()
        except Exception as e:
            # Fallback to simple concatenation
            summaries = [s.combined_summary or s.frame_description for s in cluster.segments]
            return " ".join(summaries[:3]) + "..."

    async def analyze_clusters(
        self,
        clusters: List[SceneCluster],
        progress_callback=None
    ) -> List[SceneCluster]:
        """Generate summaries for all clusters using async batch processing.

        Args:
            clusters: List of clusters to analyze.
            progress_callback: Optional callback(current, total, message).

        Returns:
            Same clusters with summaries populated.
        """
        if not clusters:
            return clusters

        semaphore = asyncio.Semaphore(self.concurrency)
        completed = 0
        completed_lock = asyncio.Lock()

        async def process_cluster(cluster: SceneCluster) -> tuple:
            nonlocal completed
            async with semaphore:
                summary = await self.generate_cluster_summary(cluster)
                async with completed_lock:
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(clusters), f"Cluster {cluster.id}")
                return (cluster.id, summary)

        # Process all clusters concurrently
        tasks = [process_cluster(c) for c in clusters]
        results = await asyncio.gather(*tasks)

        # Apply summaries (results may be out of order)
        summary_map = {cid: summary for cid, summary in results}
        for cluster in clusters:
            cluster.cluster_summary = summary_map.get(cluster.id, "")

        return clusters


class StoryBoundaryDetector:
    """Detects story boundaries using LLM with smart batch processing."""

    def __init__(self, llm_client, chunk_size: int = 30):
        """Initialize detector.

        Args:
            llm_client: LLM client for analysis.
            chunk_size: Number of segments to process per LLM call.
        """
        self.llm = llm_client
        self.chunk_size = chunk_size

    async def detect_boundaries_batch(self, segments: List[VideoSegment]) -> List[int]:
        """Detect all story boundaries within a batch of segments.

        Args:
            segments: List of consecutive segments to analyze.

        Returns:
            List of indices where boundaries occur (boundary AFTER that index).
            E.g., [5, 12] means boundaries after segments 5 and 12.
        """
        if len(segments) <= 1:
            return []

        # Build segment summaries for prompt
        segment_lines = []
        for i, seg in enumerate(segments):
            summary = seg.combined_summary or seg.frame_description
            transcript_preview = (seg.transcript or "")[:100]
            segment_lines.append(
                f"{i}. [{seg.timestamp_formatted}] {summary[:150]}"
                + (f" | \"{transcript_preview}...\"" if transcript_preview else "")
            )

        prompt = f"""Analyze these consecutive video segments and identify where STORY BOUNDARIES occur.

A story boundary is where there's a significant change in:
- Scene/location change
- Topic or subject shift
- New character introduction
- Narrative beat change
- Time jump

SEGMENTS ({len(segments)} total):
{chr(10).join(segment_lines)}

Return ONLY a JSON array of segment indices where boundaries occur.
The boundary is AFTER that segment index.
Example: [3, 8, 15] means story changes after segments 3, 8, and 15.
If no clear boundaries, return [].

JSON array:"""

        try:
            response = await self.llm.generate(prompt)
            response = response.strip()

            # Extract JSON array from response
            if "[" in response and "]" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                json_str = response[start:end]
                boundaries = json.loads(json_str)

                # Validate indices
                valid = [
                    int(b) for b in boundaries
                    if isinstance(b, (int, float)) and 0 <= int(b) < len(segments) - 1
                ]
                return sorted(set(valid))
            return []
        except Exception:
            return []

    async def detect_all_boundaries(
        self,
        segments: List[VideoSegment],
        progress_callback=None
    ) -> List[int]:
        """Detect all story boundaries using smart adaptive chunking.

        Uses smart chunking: each batch starts right after the last detected
        boundary, ensuring no boundaries are missed at chunk edges.

        Args:
            segments: All segments to analyze.
            progress_callback: Optional callback(current, total, message).

        Returns:
            List of global indices where boundaries occur.
        """
        if len(segments) <= 1:
            return []

        all_boundaries = []
        start = 0
        batch_num = 0
        total_batches_est = (len(segments) // self.chunk_size) + 1

        while start < len(segments) - 1:
            end = min(start + self.chunk_size, len(segments))
            chunk = segments[start:end]

            batch_num += 1
            if progress_callback:
                progress_callback(
                    batch_num, total_batches_est,
                    f"Analyzing segments {start}-{end-1}"
                )

            # Get boundaries in this chunk (relative indices)
            chunk_boundaries = await self.detect_boundaries_batch(chunk)

            # Convert to global indices
            for idx in chunk_boundaries:
                global_idx = start + idx
                all_boundaries.append(global_idx)

            if chunk_boundaries:
                # Smart chunking: start next batch right after last boundary
                last_boundary_global = start + chunk_boundaries[-1]
                start = last_boundary_global + 1
            else:
                # No boundaries found, move to end of chunk
                start = end

        return sorted(set(all_boundaries))

    async def refine_clusters(
        self,
        clusters: List[SceneCluster],
        progress_callback=None
    ) -> List[SceneCluster]:
        """Refine clusters by detecting story boundaries using smart batching.

        Args:
            clusters: Initial clusters (typically 1 big cluster).
            progress_callback: Optional callback for progress updates.

        Returns:
            Refined clusters split at detected story boundaries.
        """
        # Flatten all segments from all clusters
        all_segments = []
        for cluster in clusters:
            all_segments.extend(cluster.segments)

        if len(all_segments) <= 1:
            return clusters

        # Sort by timestamp
        all_segments.sort(key=lambda s: s.timestamp_start)

        # Detect all boundaries using smart chunking
        boundaries = await self.detect_all_boundaries(
            all_segments,
            progress_callback=progress_callback
        )

        # Split segments at boundaries
        refined = []
        cluster_id = 0
        current_segments = []

        for i, seg in enumerate(all_segments):
            current_segments.append(seg)

            # Check if there's a boundary after this segment
            if i in boundaries:
                refined.append(SceneCluster(
                    id=cluster_id,
                    segments=current_segments
                ))
                cluster_id += 1
                current_segments = []

        # Add final cluster
        if current_segments:
            refined.append(SceneCluster(
                id=cluster_id,
                segments=current_segments
            ))

        return refined
