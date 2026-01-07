"""Asset matching for NOLAN."""

from typing import List
from pathlib import Path
import shutil

from nolan.indexer import VideoIndex, VideoSegment
from nolan.scenes import Scene, ScenePlan


class AssetMatcher:
    """Matches scenes to video library segments."""

    def __init__(self, index: VideoIndex):
        """Initialize the matcher.

        Args:
            index: The video index to search.
        """
        self.index = index

    def find_matches(self, scene: Scene, limit: int = 5) -> List[VideoSegment]:
        """Find matching video segments for a scene.

        Args:
            scene: The scene to match.
            limit: Maximum matches to return.

        Returns:
            List of matching VideoSegment objects.
        """
        if not scene.library_match:
            return []

        # Combine visual description and search query for better matching
        query = f"{scene.visual_description} {scene.search_query}"

        return self.index.search(query, limit=limit)

    def match_all_scenes(self, plan: ScenePlan, limit_per_scene: int = 3) -> dict:
        """Match all scenes in a plan to library assets.

        Args:
            plan: The scene plan to process.
            limit_per_scene: Max matches per scene.

        Returns:
            Dict mapping scene IDs to lists of matches.
        """
        results = {}

        for section_scenes in plan.sections.values():
            for scene in section_scenes:
                matches = self.find_matches(scene, limit=limit_per_scene)
                results[scene.id] = matches

        return results

    def copy_matched_assets(
        self,
        plan: ScenePlan,
        output_dir: Path,
        limit_per_scene: int = 1
    ) -> dict:
        """Copy top matched assets to output directory.

        Args:
            plan: The scene plan.
            output_dir: Directory to copy assets to.
            limit_per_scene: How many matches to copy per scene.

        Returns:
            Dict mapping scene IDs to copied file paths.
        """
        matched_dir = output_dir / "matched"
        matched_dir.mkdir(parents=True, exist_ok=True)

        copied = {}

        for section_scenes in plan.sections.values():
            for scene in section_scenes:
                matches = self.find_matches(scene, limit=limit_per_scene)

                if matches:
                    # For now, just record the first match
                    # In future, could symlink or copy the video segment
                    scene.matched_asset = matches[0].video_path
                    copied[scene.id] = {
                        'video': matches[0].video_path,
                        'timestamp': matches[0].timestamp,
                        'description': matches[0].description
                    }

        return copied
