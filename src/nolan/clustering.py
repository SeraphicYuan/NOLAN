"""Scene clustering for grouping continuous segments into story moments."""

import asyncio
import json
from typing import List, Optional, Dict, Any

# Import models from the models package
from nolan.models.video import VideoSegment, InferredContext
from nolan.models.clustering import SceneCluster

# Re-export for backwards compatibility
__all__ = ['SceneCluster', 'ClusterAnalyzer', 'StoryBoundaryDetector', 'cluster_segments']


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


def _normalize_location(loc) -> Optional[str]:
    """Normalize location to string (handles list or string input)."""
    if loc is None:
        return None
    if isinstance(loc, list):
        # Join list items into single string
        loc = " ".join(str(item) for item in loc if item)
    if not isinstance(loc, str):
        loc = str(loc)
    return loc.lower().strip() if loc else None


def _location_similar(loc1, loc2) -> bool:
    """Check if two locations are similar."""
    loc1 = _normalize_location(loc1)
    loc2 = _normalize_location(loc2)

    if not loc1 or not loc2:
        return False

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
    """Detects story boundaries using LLM with parallel batch processing."""

    def __init__(self, llm_client, chunk_size: int = 50, overlap: int = 15, concurrency: int = 10):
        """Initialize detector.

        Args:
            llm_client: LLM client for analysis.
            chunk_size: Number of segments to process per LLM call.
            overlap: Number of overlapping segments between chunks for edge handling.
            concurrency: Max concurrent LLM calls.
        """
        self.llm = llm_client
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.concurrency = concurrency

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

    def _create_overlapping_chunks(self, total_segments: int) -> List[tuple]:
        """Create overlapping chunk ranges for parallel processing.

        Args:
            total_segments: Total number of segments.

        Returns:
            List of (start, end) tuples representing chunk ranges.
        """
        chunks = []
        stride = self.chunk_size - self.overlap
        start = 0

        while start < total_segments:
            end = min(start + self.chunk_size, total_segments)
            chunks.append((start, end))

            if end >= total_segments:
                break
            start += stride

        return chunks

    def _merge_boundaries(self, chunk_results: List[tuple], total_segments: int) -> List[int]:
        """Merge boundaries from overlapping chunks, deduplicating near-duplicates.

        Args:
            chunk_results: List of (chunk_start, boundaries) tuples.
            total_segments: Total number of segments.

        Returns:
            Deduplicated list of global boundary indices.
        """
        # Convert all to global indices
        all_boundaries = []
        for chunk_start, local_boundaries in chunk_results:
            for local_idx in local_boundaries:
                global_idx = chunk_start + local_idx
                if 0 <= global_idx < total_segments - 1:
                    all_boundaries.append(global_idx)

        if not all_boundaries:
            return []

        # Sort and deduplicate nearby boundaries (within 2 segments = same boundary)
        all_boundaries.sort()
        deduped = [all_boundaries[0]]

        for boundary in all_boundaries[1:]:
            # If this boundary is more than 2 segments away from the last, it's new
            if boundary - deduped[-1] > 2:
                deduped.append(boundary)

        return deduped

    async def detect_all_boundaries(
        self,
        segments: List[VideoSegment],
        progress_callback=None
    ) -> List[int]:
        """Detect all story boundaries using parallel processing with overlapping chunks.

        Runs all chunks in parallel for speed, using overlap to handle edge cases.
        Boundaries detected in overlapping regions are deduplicated.

        Args:
            segments: All segments to analyze.
            progress_callback: Optional callback(current, total, message).

        Returns:
            List of global indices where boundaries occur.
        """
        if len(segments) <= 1:
            return []

        # Create overlapping chunks
        chunks = self._create_overlapping_chunks(len(segments))
        total_chunks = len(chunks)

        if progress_callback:
            progress_callback(0, total_chunks, f"Processing {total_chunks} chunks in parallel...")

        # Process all chunks in parallel with concurrency limit
        semaphore = asyncio.Semaphore(self.concurrency)
        completed = 0
        completed_lock = asyncio.Lock()

        async def process_chunk(chunk_start: int, chunk_end: int) -> tuple:
            nonlocal completed
            async with semaphore:
                chunk_segments = segments[chunk_start:chunk_end]
                local_boundaries = await self.detect_boundaries_batch(chunk_segments)

                async with completed_lock:
                    completed += 1
                    if progress_callback:
                        progress_callback(
                            completed, total_chunks,
                            f"Chunk {chunk_start}-{chunk_end-1} done"
                        )

                return (chunk_start, local_boundaries)

        # Run all chunks in parallel
        tasks = [process_chunk(start, end) for start, end in chunks]
        chunk_results = await asyncio.gather(*tasks)

        # Merge and deduplicate boundaries
        return self._merge_boundaries(chunk_results, len(segments))

    async def refine_clusters(
        self,
        clusters: List[SceneCluster],
        progress_callback=None
    ) -> List[SceneCluster]:
        """Refine clusters by detecting story boundaries using parallel processing.

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
