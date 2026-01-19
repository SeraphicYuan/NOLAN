"""Semantic vector search for NOLAN video library.

Uses ChromaDB for vector storage and BGE embeddings for semantic similarity.
Supports searching at segment level, cluster level, or both.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings

from nolan.indexer import VideoIndex, VideoSegment


# Embedding model configuration
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass
class SemanticSearchResult:
    """A semantic search result with similarity score."""
    score: float  # Similarity score (higher = more similar)
    content_type: Literal["segment", "cluster"]
    video_path: str
    timestamp_start: float
    timestamp_end: float
    description: str  # combined_summary or cluster_summary
    transcript: Optional[str] = None
    people: List[str] = None
    location: Optional[str] = None
    objects: List[str] = None
    cluster_id: Optional[int] = None
    segment_id: Optional[int] = None

    def __post_init__(self):
        if self.people is None:
            self.people = []
        if self.objects is None:
            self.objects = []


class VectorSearch:
    """Semantic search over video index using ChromaDB."""

    # Collection names
    SEGMENTS_COLLECTION = "nolan_segments"
    CLUSTERS_COLLECTION = "nolan_clusters"

    def __init__(
        self,
        db_path: Path,
        index: Optional[VideoIndex] = None,
        embedding_model: str = EMBEDDING_MODEL
    ):
        """Initialize vector search.

        Args:
            db_path: Path to ChromaDB persistent storage directory.
            index: Optional VideoIndex for syncing. If not provided, search-only mode.
            embedding_model: Sentence-transformers model name for embeddings.
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.index = index
        self.embedding_model = embedding_model

        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )

        # Lazy load embedding function
        self._embedding_fn = None

    def _get_embedding_function(self):
        """Get or create the embedding function."""
        if self._embedding_fn is None:
            from chromadb.utils import embedding_functions
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model
            )
        return self._embedding_fn

    def _get_segments_collection(self):
        """Get or create the segments collection."""
        return self.client.get_or_create_collection(
            name=self.SEGMENTS_COLLECTION,
            embedding_function=self._get_embedding_function(),
            metadata={"description": "Video segments from NOLAN index"}
        )

    def _get_clusters_collection(self):
        """Get or create the clusters collection."""
        return self.client.get_or_create_collection(
            name=self.CLUSTERS_COLLECTION,
            embedding_function=self._get_embedding_function(),
            metadata={"description": "Video clusters from NOLAN index"}
        )

    def _build_segment_text(self, segment: VideoSegment) -> str:
        """Build searchable text from a segment for embedding.

        Combines the most semantically rich fields.
        """
        parts = []

        # Primary: combined summary is the richest text
        if segment.combined_summary:
            parts.append(segment.combined_summary)
        elif segment.frame_description:
            parts.append(segment.frame_description)

        # Add transcript if available (provides context)
        if segment.transcript:
            parts.append(f"Transcript: {segment.transcript}")

        # Add inferred context for richer semantics
        if segment.inferred_context:
            ctx = segment.inferred_context
            if ctx.people:
                parts.append(f"People: {', '.join(ctx.people)}")
            if ctx.location:
                parts.append(f"Location: {ctx.location}")
            if ctx.story_context:
                parts.append(f"Context: {ctx.story_context}")

        return " | ".join(parts) if parts else ""

    def _build_cluster_text(self, cluster: Dict[str, Any]) -> str:
        """Build searchable text from a cluster for embedding."""
        parts = []

        if cluster.get("cluster_summary"):
            parts.append(cluster["cluster_summary"])

        if cluster.get("people"):
            parts.append(f"People: {', '.join(cluster['people'])}")

        if cluster.get("locations"):
            parts.append(f"Locations: {', '.join(cluster['locations'])}")

        return " | ".join(parts) if parts else ""

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure all metadata values are ChromaDB-compatible (str, int, float, bool, or None)."""
        sanitized = {}
        for key, value in metadata.items():
            if value is None:
                sanitized[key] = None
            elif isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, (list, dict)):
                # Serialize complex types to JSON
                sanitized[key] = json.dumps(value)
            else:
                # Convert anything else to string
                sanitized[key] = str(value)
        return sanitized

    def _segment_to_metadata(self, segment: VideoSegment, video_id: int, project_id: Optional[str]) -> Dict[str, Any]:
        """Convert segment to ChromaDB metadata."""
        metadata = {
            "video_path": segment.video_path,
            "video_id": video_id,
            "timestamp_start": segment.timestamp_start,
            "timestamp_end": segment.timestamp_end,
            "has_transcript": segment.transcript is not None,
        }

        if project_id:
            metadata["project_id"] = project_id

        # Add filterable context fields
        if segment.inferred_context:
            ctx = segment.inferred_context
            if ctx.people:
                metadata["people"] = json.dumps(ctx.people)
            if ctx.location:
                metadata["location"] = ctx.location
            if ctx.objects:
                metadata["objects"] = json.dumps(ctx.objects)

        return metadata

    def _cluster_to_metadata(self, cluster: Dict[str, Any], video_id: int, project_id: Optional[str]) -> Dict[str, Any]:
        """Convert cluster to ChromaDB metadata."""
        metadata = {
            "video_path": cluster["video_path"] or "",
            "video_id": video_id,
            "cluster_index": cluster["cluster_index"],
            "timestamp_start": cluster["timestamp_start"],
            "timestamp_end": cluster["timestamp_end"],
        }

        if project_id:
            metadata["project_id"] = project_id

        # ChromaDB metadata must be str, int, float, bool, or None - serialize lists to JSON
        if cluster.get("people"):
            metadata["people"] = json.dumps(cluster["people"])

        if cluster.get("locations"):
            metadata["locations"] = json.dumps(cluster["locations"])

        return metadata

    def get_synced_timestamps(self) -> Dict[int, str]:
        """Get indexed_at timestamps of videos currently in vector DB.

        Returns:
            Dict mapping video_id to indexed_at timestamp.
        """
        try:
            segments_collection = self._get_segments_collection()
            # Get all unique video timestamps from segments
            results = segments_collection.get(include=["metadatas"])

            timestamps = {}
            if results and results["metadatas"]:
                for metadata in results["metadatas"]:
                    vid_id = metadata.get("video_id")
                    ts = metadata.get("indexed_at")
                    if vid_id is not None and ts:
                        timestamps[vid_id] = ts

            return timestamps
        except Exception:
            return {}

    def delete_video_vectors(self, video_id: int):
        """Delete all vectors for a specific video.

        Args:
            video_id: The video ID to delete vectors for.
        """
        segments_collection = self._get_segments_collection()
        clusters_collection = self._get_clusters_collection()

        # Get IDs to delete (ChromaDB requires knowing the IDs)
        try:
            # Delete segments with this video_id
            seg_results = segments_collection.get(
                where={"video_id": {"$eq": video_id}},
                include=[]
            )
            if seg_results and seg_results["ids"]:
                segments_collection.delete(ids=seg_results["ids"])

            # Delete clusters with this video_id
            cluster_results = clusters_collection.get(
                where={"video_id": {"$eq": video_id}},
                include=[]
            )
            if cluster_results and cluster_results["ids"]:
                clusters_collection.delete(ids=cluster_results["ids"])
        except Exception:
            # Collection might be empty or not exist yet
            pass

    def sync_video(
        self,
        video_id: int,
        video_path: str,
        indexed_at: str,
        project_id: Optional[str] = None
    ) -> Dict[str, int]:
        """Sync vectors for a single video.

        Args:
            video_id: Database video ID.
            video_path: Path to video file.
            indexed_at: Video indexed_at timestamp for change detection.
            project_id: Optional project ID.

        Returns:
            Dict with counts: {"segments": n, "clusters": m}
        """
        if self.index is None:
            raise ValueError("No VideoIndex provided. Cannot sync.")

        segments_collection = self._get_segments_collection()
        clusters_collection = self._get_clusters_collection()

        # Delete existing vectors for this video first
        self.delete_video_vectors(video_id)

        segments_added = 0
        clusters_added = 0

        # Sync segments
        segments = self.index.get_segments_by_video_id(video_id)
        for j, segment in enumerate(segments):
            text = self._build_segment_text(segment)
            if not text:
                continue

            doc_id = f"seg_{video_id}_{j}"
            metadata = self._segment_to_metadata(segment, video_id, project_id)
            metadata["indexed_at"] = indexed_at  # Track indexed_at for incremental sync
            metadata["description"] = segment.combined_summary or segment.frame_description
            if segment.transcript:
                metadata["transcript"] = segment.transcript[:1000]

            metadata = self._sanitize_metadata(metadata)
            segments_collection.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
            segments_added += 1

        # Sync clusters
        clusters = self.index.get_clusters_by_video_id(video_id)
        for cluster in clusters:
            text = self._build_cluster_text(cluster)
            if not text:
                continue

            doc_id = f"cluster_{video_id}_{cluster['cluster_index']}"
            metadata = self._cluster_to_metadata(cluster, video_id, project_id)
            metadata["indexed_at"] = indexed_at
            if cluster.get("cluster_summary"):
                metadata["description"] = cluster["cluster_summary"]

            metadata = self._sanitize_metadata(metadata)
            clusters_collection.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
            clusters_added += 1

        return {"segments": segments_added, "clusters": clusters_added}

    def sync_from_index(
        self,
        project_id: Optional[str] = None,
        progress_callback=None,
        incremental: bool = True
    ) -> Dict[str, int]:
        """Sync vectors from SQLite index to ChromaDB.

        Args:
            project_id: If provided, only sync videos from this project.
            progress_callback: Optional callback(current, total, message).
            incremental: If True, only sync videos with changed fingerprints.

        Returns:
            Dict with counts: {"segments": n, "clusters": m, "skipped": k}
        """
        if self.index is None:
            raise ValueError("No VideoIndex provided. Cannot sync.")

        import sqlite3

        # Get currently synced timestamps for incremental sync
        synced_timestamps = self.get_synced_timestamps() if incremental else {}

        segments_collection = self._get_segments_collection()
        clusters_collection = self._get_clusters_collection()

        # Get videos to sync (include indexed_at for change detection)
        with sqlite3.connect(self.index.db_path) as conn:
            if project_id:
                cursor = conn.execute(
                    "SELECT id, path, project_id, indexed_at FROM videos WHERE project_id = ?",
                    (project_id,)
                )
            else:
                cursor = conn.execute("SELECT id, path, project_id, indexed_at FROM videos")

            videos = cursor.fetchall()

        total_videos = len(videos)
        segments_added = 0
        clusters_added = 0
        skipped = 0

        for i, (video_id, video_path, vid_project_id, indexed_at) in enumerate(videos):
            # Check if video needs syncing (indexed_at changed means re-indexed)
            if incremental and indexed_at:
                existing_ts = synced_timestamps.get(video_id)
                if existing_ts == indexed_at:
                    skipped += 1
                    if progress_callback:
                        progress_callback(i + 1, total_videos, f"Skipping (unchanged): {Path(video_path).name}")
                    continue

            if progress_callback:
                progress_callback(i + 1, total_videos, f"Syncing: {Path(video_path).name}")

            # Delete existing vectors for this video (in case of re-index)
            self.delete_video_vectors(video_id)

            # Sync segments for this video
            segments = self.index.get_segments_by_video_id(video_id)

            for j, segment in enumerate(segments):
                text = self._build_segment_text(segment)
                if not text:
                    continue

                doc_id = f"seg_{video_id}_{j}"
                metadata = self._segment_to_metadata(segment, video_id, vid_project_id)

                # Track indexed_at for incremental sync (detects re-indexing)
                if indexed_at:
                    metadata["indexed_at"] = indexed_at

                # Store description for retrieval
                metadata["description"] = segment.combined_summary or segment.frame_description
                if segment.transcript:
                    metadata["transcript"] = segment.transcript[:1000]  # Limit size

                # Sanitize metadata to ensure ChromaDB compatibility
                metadata = self._sanitize_metadata(metadata)

                segments_collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[metadata]
                )
                segments_added += 1

            # Sync clusters for this video
            clusters = self.index.get_clusters_by_video_id(video_id)

            for cluster in clusters:
                text = self._build_cluster_text(cluster)
                if not text:
                    continue

                doc_id = f"cluster_{video_id}_{cluster['cluster_index']}"
                metadata = self._cluster_to_metadata(cluster, video_id, vid_project_id)

                # Track indexed_at for incremental sync (detects re-indexing)
                if indexed_at:
                    metadata["indexed_at"] = indexed_at

                # Store summary for retrieval
                if cluster.get("cluster_summary"):
                    metadata["description"] = cluster["cluster_summary"]

                # Sanitize metadata to ensure ChromaDB compatibility
                metadata = self._sanitize_metadata(metadata)

                clusters_collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[metadata]
                )
                clusters_added += 1

        return {"segments": segments_added, "clusters": clusters_added, "skipped": skipped}

    def search(
        self,
        query: str,
        limit: int = 10,
        search_level: Literal["segments", "clusters", "both"] = "both",
        project_id: Optional[str] = None,
        people_filter: Optional[List[str]] = None,
        location_filter: Optional[str] = None
    ) -> List[SemanticSearchResult]:
        """Semantic search across video index.

        Args:
            query: Natural language search query.
            limit: Maximum results to return.
            search_level: What to search - "segments", "clusters", or "both".
            project_id: Optional project ID to filter by.
            people_filter: Optional list of people names to filter by.
            location_filter: Optional location string to filter by.

        Returns:
            List of SemanticSearchResult sorted by similarity score.
        """
        results = []

        # Build ChromaDB where filter
        where_filter = self._build_where_filter(project_id, people_filter, location_filter)

        # Add query prefix for BGE model (improves retrieval quality)
        query_text = QUERY_PREFIX + query

        # Search segments
        if search_level in ("segments", "both"):
            segment_results = self._search_collection(
                self._get_segments_collection(),
                query_text,
                limit,
                where_filter,
                "segment"
            )
            results.extend(segment_results)

        # Search clusters
        if search_level in ("clusters", "both"):
            cluster_results = self._search_collection(
                self._get_clusters_collection(),
                query_text,
                limit,
                where_filter,
                "cluster"
            )
            results.extend(cluster_results)

        # Sort by score and limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _build_where_filter(
        self,
        project_id: Optional[str],
        people_filter: Optional[List[str]],
        location_filter: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Build ChromaDB where filter from parameters."""
        conditions = []

        if project_id:
            conditions.append({"project_id": {"$eq": project_id}})

        if location_filter:
            conditions.append({"location": {"$eq": location_filter}})

        # Note: people_filter requires checking JSON array, which ChromaDB
        # doesn't support natively. We'll filter in post-processing if needed.

        if not conditions:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}

    def _search_collection(
        self,
        collection,
        query_text: str,
        limit: int,
        where_filter: Optional[Dict],
        content_type: Literal["segment", "cluster"]
    ) -> List[SemanticSearchResult]:
        """Search a single collection and convert results."""
        try:
            query_result = collection.query(
                query_texts=[query_text],
                n_results=limit,
                where=where_filter,
                include=["metadatas", "distances"]
            )
        except Exception as e:
            # Collection might be empty
            if "no documents" in str(e).lower():
                return []
            raise

        results = []

        if not query_result["ids"] or not query_result["ids"][0]:
            return results

        ids = query_result["ids"][0]
        metadatas = query_result["metadatas"][0]
        distances = query_result["distances"][0]

        for doc_id, metadata, distance in zip(ids, metadatas, distances):
            # Convert distance to similarity score (ChromaDB returns L2 distance)
            # Lower distance = higher similarity
            score = 1 / (1 + distance)

            # Parse JSON fields
            people = []
            objects = []
            locations = []

            if metadata.get("people"):
                try:
                    people = json.loads(metadata["people"])
                except (json.JSONDecodeError, TypeError):
                    pass

            if metadata.get("objects"):
                try:
                    objects = json.loads(metadata["objects"])
                except (json.JSONDecodeError, TypeError):
                    pass

            if metadata.get("locations"):
                try:
                    locations = json.loads(metadata["locations"])
                except (json.JSONDecodeError, TypeError):
                    pass

            result = SemanticSearchResult(
                score=score,
                content_type=content_type,
                video_path=metadata.get("video_path", ""),
                timestamp_start=metadata.get("timestamp_start", 0),
                timestamp_end=metadata.get("timestamp_end", 0),
                description=metadata.get("description", ""),
                transcript=metadata.get("transcript"),
                people=people,
                location=metadata.get("location") or (locations[0] if locations else None),
                objects=objects,
                cluster_id=metadata.get("cluster_index") if content_type == "cluster" else None,
            )
            results.append(result)

        return results

    def get_stats(self) -> Dict[str, int]:
        """Get collection statistics."""
        try:
            segments_count = self._get_segments_collection().count()
        except Exception:
            segments_count = 0

        try:
            clusters_count = self._get_clusters_collection().count()
        except Exception:
            clusters_count = 0

        return {
            "segments": segments_count,
            "clusters": clusters_count
        }

    def clear(self, collection: Optional[Literal["segments", "clusters"]] = None):
        """Clear vector collections.

        Args:
            collection: Which collection to clear. If None, clears both.
        """
        if collection is None or collection == "segments":
            try:
                self.client.delete_collection(self.SEGMENTS_COLLECTION)
            except Exception:
                pass

        if collection is None or collection == "clusters":
            try:
                self.client.delete_collection(self.CLUSTERS_COLLECTION)
            except Exception:
                pass
