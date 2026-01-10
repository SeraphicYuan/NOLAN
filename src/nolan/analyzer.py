"""Segment analyzer for LLM fusion and context inference."""

import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any

from nolan.indexer import InferredContext


@dataclass
class AnalysisResult:
    """Result of segment analysis."""
    combined_summary: str
    inferred_context: Optional[InferredContext]


class SegmentAnalyzer:
    """Analyzes video segments by fusing visual and audio information."""

    def __init__(self, llm_client):
        """Initialize segment analyzer.

        Args:
            llm_client: LLM client for text generation.
        """
        self.llm = llm_client

    async def analyze(
        self,
        frame_description: str,
        transcript: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> AnalysisResult:
        """Analyze a segment by fusing visual and audio information.

        Args:
            frame_description: Visual description from vision model.
            transcript: Transcript text for this segment (if available).
            timestamp: Timestamp for context (optional).

        Returns:
            AnalysisResult with combined summary and inferred context.
        """
        # If no transcript, return minimal result
        if not transcript or not transcript.strip():
            return AnalysisResult(
                combined_summary=frame_description,
                inferred_context=None
            )

        prompt = self._build_analysis_prompt(frame_description, transcript, timestamp)

        try:
            response = await self.llm.generate(prompt)
            return self._parse_response(response, frame_description)
        except Exception as e:
            # Fallback on error
            return AnalysisResult(
                combined_summary=f"{frame_description} | Audio: {transcript[:100]}...",
                inferred_context=None
            )

    def _build_analysis_prompt(
        self,
        frame_description: str,
        transcript: str,
        timestamp: Optional[float]
    ) -> str:
        """Build the analysis prompt."""
        time_context = ""
        if timestamp is not None:
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)
            time_context = f" at {minutes}:{seconds:02d}"

        return f"""Analyze this video segment{time_context} based on visual and audio information.

VISUAL: {frame_description}
AUDIO: {transcript}

Respond with a JSON object containing:
1. "combined_summary": A 1-2 sentence description capturing both what's seen and heard.
2. "inferred_context": An object with the following fields (ONLY include fields where you have supporting evidence - omit fields with no evidence):
   - "people": Array of identifiable people (names if mentioned, or descriptions like "male speaker", "interviewer")
   - "location": Specific place if identifiable from visual or audio cues
   - "story_context": Brief narrative context (what's happening in the story/video)
   - "objects": Notable objects relevant to the content
   - "confidence": "high" (explicit mention/clear visual), "medium" (strong implication), or "low" (educated guess)

IMPORTANT:
- Only include inferred_context fields you have actual evidence for
- Don't guess without basis - it's better to omit a field than to hallucinate
- The combined_summary should be useful for searching this video segment

Respond ONLY with valid JSON, no other text."""

    def _parse_response(self, response: str, fallback_description: str) -> AnalysisResult:
        """Parse LLM response into AnalysisResult."""
        # Try to extract JSON from response
        try:
            # Handle potential markdown code blocks
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r"\{[\s\S]*\}", response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response

            data = json.loads(json_str)

            combined_summary = data.get("combined_summary", fallback_description)

            # Parse inferred context
            inferred = None
            if "inferred_context" in data and data["inferred_context"]:
                ctx = data["inferred_context"]
                inferred = InferredContext(
                    people=ctx.get("people", []),
                    location=ctx.get("location"),
                    story_context=ctx.get("story_context"),
                    objects=ctx.get("objects", []),
                    confidence=ctx.get("confidence", "low")
                )

            return AnalysisResult(
                combined_summary=combined_summary,
                inferred_context=inferred
            )

        except (json.JSONDecodeError, KeyError, TypeError):
            # If parsing fails, extract what we can
            return AnalysisResult(
                combined_summary=fallback_description,
                inferred_context=None
            )


class BatchAnalyzer:
    """Batch analyze multiple segments efficiently."""

    def __init__(self, analyzer: SegmentAnalyzer, batch_size: int = 5):
        """Initialize batch analyzer.

        Args:
            analyzer: SegmentAnalyzer instance.
            batch_size: Number of segments to analyze in parallel.
        """
        self.analyzer = analyzer
        self.batch_size = batch_size

    async def analyze_segments(
        self,
        segments: list[Dict[str, Any]]
    ) -> list[AnalysisResult]:
        """Analyze multiple segments.

        Args:
            segments: List of dicts with 'frame_description', 'transcript', 'timestamp'.

        Returns:
            List of AnalysisResult objects.
        """
        import asyncio

        results = []

        # Process in batches
        for i in range(0, len(segments), self.batch_size):
            batch = segments[i:i + self.batch_size]

            # Analyze batch concurrently
            tasks = [
                self.analyzer.analyze(
                    frame_description=seg["frame_description"],
                    transcript=seg.get("transcript"),
                    timestamp=seg.get("timestamp")
                )
                for seg in batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    # Fallback on error
                    results.append(AnalysisResult(
                        combined_summary=batch[j]["frame_description"],
                        inferred_context=None
                    ))
                else:
                    results.append(result)

        return results
