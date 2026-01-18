"""Clip matcher for matching scenes to video library clips."""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from nolan.config import ClipMatchingConfig
from nolan.scenes import Scene, ScenePlan
from nolan.vector_search import VectorSearch, SemanticSearchResult


@dataclass
class ClipCandidate:
    """A candidate clip from the video library."""
    video_path: str
    timestamp_start: float
    timestamp_end: float
    description: str
    transcript: Optional[str]
    similarity_score: float
    people: List[str]
    location: Optional[str]

    @property
    def duration(self) -> float:
        return self.timestamp_end - self.timestamp_start


@dataclass
class MatchResult:
    """Result of LLM clip selection."""
    selected_index: int           # Which candidate was selected (0-based)
    reasoning: str                # Why this clip was selected
    confidence: float             # 0.0-1.0 confidence
    tailored_start: float         # Adjusted start time
    tailored_end: float           # Adjusted end time


class ClipMatcher:
    """Matches scenes to video library clips using semantic search and LLM selection."""

    def __init__(
        self,
        vector_search: VectorSearch,
        llm_client,
        config: ClipMatchingConfig
    ):
        """Initialize clip matcher.

        Args:
            vector_search: VectorSearch instance for semantic search.
            llm_client: LLM client for candidate selection.
            config: ClipMatchingConfig with matching parameters.
        """
        self.vector_search = vector_search
        self.llm = llm_client
        self.config = config
        self._selection_cache: Dict[str, Optional[MatchResult]] = {}

    def build_search_query(self, scene: Scene) -> str:
        """Build enriched search query from scene fields.

        Combines narration_excerpt + visual_description + search_query
        for richer semantic matching.
        """
        parts = []

        if scene.narration_excerpt:
            parts.append(scene.narration_excerpt)
        if scene.visual_description:
            parts.append(scene.visual_description)
        if scene.search_query:
            parts.append(scene.search_query)

        return " | ".join(parts) if parts else ""

    @staticmethod
    def _candidate_cache_key(scene: Scene, candidates: List[ClipCandidate], scene_duration: float) -> str:
        parts = []
        for c in candidates:
            parts.append({
                "video_path": c.video_path,
                "timestamp_start": round(c.timestamp_start, 3),
                "timestamp_end": round(c.timestamp_end, 3),
                "similarity": round(c.similarity_score, 4),
            })
        payload = {
            "scene_id": scene.id,
            "duration": round(scene_duration, 3),
            "candidates": parts,
        }
        return hashlib.md5(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _dedupe_candidates(candidates: List[ClipCandidate]) -> List[ClipCandidate]:
        deduped: Dict[Tuple[str, float, float], ClipCandidate] = {}
        for candidate in candidates:
            key = (candidate.video_path, candidate.timestamp_start, candidate.timestamp_end)
            existing = deduped.get(key)
            if existing is None or candidate.similarity_score > existing.similarity_score:
                deduped[key] = candidate
        return list(deduped.values())

    @staticmethod
    def _filter_segments_by_clusters(
        segments: List[SemanticSearchResult],
        clusters: List[SemanticSearchResult]
    ) -> List[SemanticSearchResult]:
        if not clusters:
            return segments

        ranges_by_video: Dict[str, List[Tuple[float, float]]] = {}
        for cluster in clusters:
            ranges_by_video.setdefault(cluster.video_path, []).append(
                (cluster.timestamp_start, cluster.timestamp_end)
            )

        filtered = []
        for segment in segments:
            ranges = ranges_by_video.get(segment.video_path)
            if not ranges:
                continue
            for start, end in ranges:
                if segment.timestamp_end > start and segment.timestamp_start < end:
                    filtered.append(segment)
                    break
        return filtered

    def _rank_candidates(self, candidates: List[ClipCandidate], scene_duration: float) -> List[ClipCandidate]:
        def sort_key(c: ClipCandidate):
            duration_fit = abs(c.duration - scene_duration)
            transcript_bonus = 1 if c.transcript else 0
            return (-c.similarity_score, -transcript_bonus, duration_fit, c.video_path)

        return sorted(candidates, key=sort_key)

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        message = str(error).lower()
        return any(token in message for token in ("429", "rate limit", "resource_exhausted"))

    async def _call_with_backoff(self, func, *args, **kwargs):
        """Retry on rate limits with short backoff."""
        base_delay = 0.5
        max_retries = 3

        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if not self._is_rate_limit_error(e) or attempt >= max_retries:
                    raise
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

    async def find_candidates(
        self,
        scene: Scene,
        project_id: Optional[str] = None
    ) -> tuple[List[ClipCandidate], int, Optional[float]]:
        """Find candidate clips for a scene using vector search.

        Args:
            scene: Scene to match.
            project_id: Optional project filter.

        Returns:
            List of ClipCandidate objects sorted by similarity.
        """
        query = self.build_search_query(scene)
        if not query:
            return []

        results: List[SemanticSearchResult] = []
        raw_results_count = 0

        if self.config.search_level == "both":
            cluster_results = self.vector_search.search(
                query=query,
                limit=self.config.candidates_per_scene,
                search_level="clusters",
                project_id=project_id
            )
            segment_results = self.vector_search.search(
                query=query,
                limit=self.config.candidates_per_scene * 5,
                search_level="segments",
                project_id=project_id
            )
            filtered_segments = self._filter_segments_by_clusters(segment_results, cluster_results)
            if not filtered_segments:
                filtered_segments = segment_results
            results = filtered_segments
            raw_results_count = len(segment_results)
        else:
            results = self.vector_search.search(
                query=query,
                limit=self.config.candidates_per_scene,
                search_level=self.config.search_level,
                project_id=project_id
            )
            raw_results_count = len(results)

        # Filter by minimum similarity
        filtered = [r for r in results if r.score >= self.config.min_similarity]
        max_score = max((r.score for r in results), default=None)

        candidates = []
        for r in filtered:
            candidates.append(ClipCandidate(
                video_path=r.video_path,
                timestamp_start=r.timestamp_start,
                timestamp_end=r.timestamp_end,
                description=r.description,
                transcript=r.transcript,
                similarity_score=r.score,
                people=r.people or [],
                location=r.location
            ))

        candidates = self._dedupe_candidates(candidates)
        candidates.sort(key=lambda c: c.similarity_score, reverse=True)
        return candidates, raw_results_count, max_score

    async def select_best_candidate(
        self,
        scene: Scene,
        candidates: List[ClipCandidate]
    ) -> Optional[MatchResult]:
        """Use LLM to select the best candidate clip.

        Args:
            scene: Scene being matched.
            candidates: List of candidate clips.

        Returns:
            MatchResult with selection and tailoring, or None if no good match.
        """
        if not candidates:
            return None

        # Calculate scene duration (estimate from duration field if timing not set)
        scene_duration = self._estimate_scene_duration(scene)

        prompt = self._build_selection_prompt(scene, candidates, scene_duration)

        cache_key = self._candidate_cache_key(scene, candidates, scene_duration)
        if cache_key in self._selection_cache:
            return self._selection_cache[cache_key]

        try:
            response = await self._call_with_backoff(self.llm.generate, prompt)
            result = self._parse_selection_response(response, candidates, scene_duration)
            self._selection_cache[cache_key] = result
            return result
        except Exception as e:
            # Fallback: select highest similarity candidate with basic tailoring
            best = max(candidates, key=lambda c: c.similarity_score)
            tailored_start, tailored_end = self._compute_smart_clip(
                best.timestamp_start,
                best.timestamp_end,
                scene_duration
            )
            result = MatchResult(
                selected_index=0,
                reasoning=f"Auto-selected highest similarity match (LLM error: {e})",
                confidence=0.5,
                tailored_start=tailored_start,
                tailored_end=tailored_end
            )
            self._selection_cache[cache_key] = result
            return result

    def _estimate_scene_duration(self, scene: Scene) -> float:
        """Estimate scene duration from available fields."""
        # Prefer precise timing if available
        if scene.start_seconds is not None and scene.end_seconds is not None:
            return scene.end_seconds - scene.start_seconds

        # Parse duration string (e.g., "5s", "3.5s")
        if scene.duration:
            match = re.match(r"(\d+\.?\d*)s?", scene.duration)
            if match:
                return float(match.group(1))

        return 5.0  # Default 5 seconds

    def _compute_smart_clip(
        self,
        segment_start: float,
        segment_end: float,
        scene_duration: float
    ) -> tuple:
        """Compute smart clip boundaries using the tailoring algorithm.

        Algorithm:
        1. Skip first ~7% of clip (avoid transition effects)
        2. Shift towards start based on ratio of scene_duration/clip_duration
        3. When ratio is small: start early in clip
        4. When ratio is close to 1: nearly centered

        Args:
            segment_start: Original segment start time.
            segment_end: Original segment end time.
            scene_duration: Desired clip duration for the scene.

        Returns:
            Tuple of (clip_start, clip_end).
        """
        clip_duration = segment_end - segment_start

        # If scene is longer than clip, use full clip with edge skip
        if scene_duration >= clip_duration:
            edge_skip = clip_duration * self.config.skip_edge_percent
            return (segment_start + edge_skip, segment_end)

        # Available footage after skipping edge
        edge_skip = clip_duration * self.config.skip_edge_percent
        usable_start = segment_start + edge_skip
        usable_duration = segment_end - usable_start

        # If scene duration exceeds usable duration, use all usable
        if scene_duration >= usable_duration:
            return (usable_start, segment_end)

        # Calculate ratio-based offset
        # ratio = scene_duration / usable_duration (0 to 1)
        # When ratio is small, offset_factor is small (start early)
        # When ratio approaches 1, offset_factor approaches 0.5 (centered)
        ratio = scene_duration / usable_duration
        offset_factor = ratio * 0.5  # Linear interpolation from 0 to 0.5

        # Available slack
        slack = usable_duration - scene_duration
        offset = slack * offset_factor

        clip_start = usable_start + offset
        clip_end = clip_start + scene_duration

        return (clip_start, clip_end)

    def _build_selection_prompt(
        self,
        scene: Scene,
        candidates: List[ClipCandidate],
        scene_duration: float
    ) -> str:
        """Build the LLM prompt for candidate selection."""
        candidates_text = []
        for i, c in enumerate(candidates):
            duration = c.timestamp_end - c.timestamp_start
            transcript_preview = (c.transcript[:100] + "...") if c.transcript and len(c.transcript) > 100 else (c.transcript or "N/A")
            candidates_text.append(f"""
Candidate {i + 1}:
  - Video: {Path(c.video_path).name}
  - Time: {c.timestamp_start:.1f}s - {c.timestamp_end:.1f}s (duration: {duration:.1f}s)
  - Description: {c.description}
  - Transcript: {transcript_preview}
  - People: {', '.join(c.people) if c.people else 'N/A'}
  - Location: {c.location or 'N/A'}
  - Similarity: {c.similarity_score:.2f}
""")

        return f"""You are selecting the best video clip for a video essay scene.

SCENE REQUIREMENTS:
- Visual Type: {scene.visual_type}
- Narration: "{scene.narration_excerpt}"
- Visual Description: {scene.visual_description}
- Search Query: "{self.build_search_query(scene)}"
- Duration Needed: ~{scene_duration:.1f} seconds

CANDIDATE CLIPS:
{"".join(candidates_text)}

Select the BEST candidate considering:
1. Visual relevance: Does the clip visually match what the scene needs?
2. Narrative fit: Does the content align with the narration?
3. Duration: Does the clip have enough footage? (at least {scene_duration:.1f}s needed)
4. Quality signals: People, location, and transcript coherence.

If NO candidate is good enough (all are off-topic or too short), set selected_index to -1.

Respond with JSON only:
{{
  "selected_index": 0,
  "reasoning": "Brief explanation of why this clip is best (or why none work)",
  "confidence": 0.8
}}

IMPORTANT: Return ONLY valid JSON, no other text. Use 0-based index (0 = first candidate)."""

    def _parse_selection_response(
        self,
        response: str,
        candidates: List[ClipCandidate],
        scene_duration: float
    ) -> Optional[MatchResult]:
        """Parse LLM selection response."""
        # Try to extract JSON
        try:
            # Handle markdown code blocks
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r"\{[\s\S]*\}", response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response

            data = json.loads(json_str)

            selected_index = data.get("selected_index", 0)

            # Check for "no good match"
            if selected_index < 0 or selected_index >= len(candidates):
                return None

            selected = candidates[selected_index]

            # Compute tailored clip boundaries
            tailored_start, tailored_end = self._compute_smart_clip(
                selected.timestamp_start,
                selected.timestamp_end,
                scene_duration
            )

            return MatchResult(
                selected_index=selected_index,
                reasoning=data.get("reasoning", "Selected by LLM"),
                confidence=float(data.get("confidence", 0.7)),
                tailored_start=tailored_start,
                tailored_end=tailored_end
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Fallback to first candidate
            if candidates:
                tailored_start, tailored_end = self._compute_smart_clip(
                    candidates[0].timestamp_start,
                    candidates[0].timestamp_end,
                    scene_duration
                )
                return MatchResult(
                    selected_index=0,
                    reasoning="Fallback selection (could not parse LLM response)",
                    confidence=0.5,
                    tailored_start=tailored_start,
                    tailored_end=tailored_end
                )
            return None

    async def match_scene(
        self,
        scene: Scene,
        project_id: Optional[str] = None,
        progress_callback=None
    ) -> Optional[Dict[str, Any]]:
        """Match a single scene to a library clip.

        Args:
            scene: Scene to match.
            project_id: Optional project filter.

        Returns:
            matched_clip dict or None if no good match.
        """
        # Find candidates
        candidates, raw_count, max_score = await self.find_candidates(scene, project_id)

        if not candidates:
            if progress_callback:
                if raw_count == 0:
                    progress_callback(0, 0, f"No candidates for {scene.id} (empty search results)")
                else:
                    score_text = f"{max_score:.2f}" if max_score is not None else "n/a"
                    progress_callback(0, 0, f"No candidates for {scene.id} (max similarity {score_text} below {self.config.min_similarity})")
            return None

        scene_duration = self._estimate_scene_duration(scene)
        candidates = self._rank_candidates(candidates, scene_duration)

        # Fast path: dominant similarity avoids LLM
        if len(candidates) >= 2:
            top = candidates[0]
            runner_up = candidates[1]
            if (top.similarity_score >= self.config.fast_path_min_similarity and
                    (top.similarity_score - runner_up.similarity_score) >= self.config.fast_path_margin):
                tailored_start, tailored_end = self._compute_smart_clip(
                    top.timestamp_start,
                    top.timestamp_end,
                    scene_duration
                )
                return {
                    "video_path": top.video_path,
                    "clip_start": tailored_start,
                    "clip_end": tailored_end,
                    "original_segment_start": top.timestamp_start,
                    "original_segment_end": top.timestamp_end,
                    "match_reasoning": "Auto-selected dominant similarity match",
                    "confidence": top.similarity_score,
                    "similarity_score": top.similarity_score
                }

        # If only one candidate, use it directly with smart tailoring
        if len(candidates) == 1:
            c = candidates[0]
            tailored_start, tailored_end = self._compute_smart_clip(
                c.timestamp_start, c.timestamp_end, scene_duration
            )
            return {
                "video_path": c.video_path,
                "clip_start": tailored_start,
                "clip_end": tailored_end,
                "original_segment_start": c.timestamp_start,
                "original_segment_end": c.timestamp_end,
                "match_reasoning": f"Single candidate with similarity {c.similarity_score:.2f}",
                "confidence": c.similarity_score,
                "similarity_score": c.similarity_score
            }

        # Multiple candidates: use LLM selection
        result = await self.select_best_candidate(scene, candidates)

        if result is None:
            return None

        selected = candidates[result.selected_index]

        return {
            "video_path": selected.video_path,
            "clip_start": result.tailored_start,
            "clip_end": result.tailored_end,
            "original_segment_start": selected.timestamp_start,
            "original_segment_end": selected.timestamp_end,
            "match_reasoning": result.reasoning,
            "confidence": result.confidence,
            "similarity_score": selected.similarity_score
        }

    async def match_plan(
        self,
        plan: ScenePlan,
        project_id: Optional[str] = None,
        skip_existing: bool = True,
        progress_callback=None
    ) -> Dict[str, int]:
        """Match all scenes in a plan to library clips.

        Args:
            plan: ScenePlan to process.
            project_id: Optional project filter.
            skip_existing: Skip scenes with existing matched_clip.
            progress_callback: Optional callback(current, total, message).

        Returns:
            Dict with counts: {"matched": n, "skipped": m, "no_match": k}
        """
        # Gather all scenes to process
        scenes_to_match = []
        skipped_existing = 0
        for section_name, scenes in plan.sections.items():
            for scene in scenes:
                if skip_existing and scene.matched_clip:
                    skipped_existing += 1
                    continue
                scenes_to_match.append((section_name, scene))

        total = len(scenes_to_match)
        matched = 0
        no_match = 0
        completed = 0
        progress_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(max(1, self.config.concurrency))

        async def worker(section_name: str, scene: Scene):
            nonlocal completed
            async with semaphore:
                if progress_callback:
                    async with progress_lock:
                        progress_callback(completed + 1, total, f"Matching: {scene.id}")
                result = await self.match_scene(scene, project_id, progress_callback=progress_callback)
                async with progress_lock:
                    completed += 1
                return scene, result

        tasks = [worker(section_name, scene) for section_name, scene in scenes_to_match]
        results = await asyncio.gather(*tasks)

        for scene, result in results:
            if result:
                scene.matched_clip = result
                matched += 1
            else:
                no_match += 1

        return {"matched": matched, "skipped": skipped_existing, "no_match": no_match}
