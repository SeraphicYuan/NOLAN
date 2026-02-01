"""
Unified template catalog for Lottie animations.

Merges templates from multiple sources (LottieFiles, Jitter, Lottieflow)
into a single queryable catalog with semantic search support.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Literal


@dataclass
class TemplateInfo:
    """Unified template metadata."""
    id: str
    name: str
    category: str
    source: str  # lottiefiles, jitter, lottieflow
    local_path: str  # Relative to lottie_dir

    # Dimensions and timing
    width: int = 0
    height: int = 0
    fps: float = 30.0
    duration_seconds: float = 0.0

    # Metadata
    tags: list[str] = field(default_factory=list)
    description: str = ""
    author: str = ""
    license: str = ""

    # Schema status
    has_schema: bool = False
    schema_fields: list[str] = field(default_factory=list)

    # Colors (for style matching)
    color_palette: list[str] = field(default_factory=list)


class TemplateCatalog:
    """Unified catalog for all Lottie templates."""

    def __init__(self, lottie_dir: str | Path = "assets/common/lottie"):
        self.lottie_dir = Path(lottie_dir)
        self.templates: dict[str, TemplateInfo] = {}
        self._load_all_catalogs()

    def _load_all_catalogs(self) -> None:
        """Load and merge all catalog sources."""
        # LottieFiles catalog
        lf_path = self.lottie_dir / "catalog.json"
        if lf_path.exists():
            self._load_lottiefiles_catalog(lf_path)

        # Jitter catalog
        jitter_path = self.lottie_dir / "jitter-catalog.json"
        if jitter_path.exists():
            self._load_jitter_catalog(jitter_path)

        # Lottieflow catalog
        lflow_path = self.lottie_dir / "lottieflow-catalog.json"
        if lflow_path.exists():
            self._load_lottieflow_catalog(lflow_path)

        # Scan for files not in any catalog
        self._scan_uncataloged()

        # Check for schemas
        self._detect_schemas()

    def _load_lottiefiles_catalog(self, path: Path) -> None:
        """Load LottieFiles catalog format."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for category, items in data.get("categories", {}).items():
            for item in items:
                template = TemplateInfo(
                    id=item.get("id", ""),
                    name=item.get("title", "").replace("Free ", "").split(" Animation")[0],
                    category=category,
                    source="lottiefiles",
                    local_path=item.get("local_path", "").replace("\\", "/"),
                    width=int(item.get("width", 0)),
                    height=int(item.get("height", 0)),
                    fps=float(item.get("fps", 30)),
                    duration_seconds=float(item.get("duration_seconds", 0)),
                    tags=item.get("tags", []),
                    author=item.get("author", ""),
                    license=item.get("license", ""),
                    color_palette=item.get("color_palette", []),
                )
                self.templates[template.id] = template

    def _load_jitter_catalog(self, path: Path) -> None:
        """Load Jitter catalog format."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for category, items in data.get("categories", {}).items():
            for item in items:
                template = TemplateInfo(
                    id=f"jitter-{item.get('id', '')}",
                    name=item.get("name", ""),
                    category=f"jitter-{category}",
                    source="jitter",
                    local_path=item.get("local_path", "").replace("\\", "/"),
                    width=int(item.get("width", 0)),
                    height=int(item.get("height", 0)),
                    fps=float(item.get("fps", 30)),
                    duration_seconds=float(item.get("duration_seconds", 0)),
                )
                self.templates[template.id] = template

    def _load_lottieflow_catalog(self, path: Path) -> None:
        """Load Lottieflow catalog format."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for category, items in data.get("categories", {}).items():
            for item in items:
                template = TemplateInfo(
                    id=f"lottieflow-{item.get('id', '')}",
                    name=item.get("name", "").replace("-", " ").title(),
                    category=f"lottieflow-{category}",
                    source="lottieflow",
                    local_path=item.get("local_path", "").replace("\\", "/"),
                    width=int(item.get("width", 0)),
                    height=int(item.get("height", 0)),
                    fps=float(item.get("fps", 30)),
                    duration_seconds=float(item.get("duration_seconds", 0)),
                )
                self.templates[template.id] = template

    def _scan_uncataloged(self) -> None:
        """Scan for template files not in any catalog."""
        cataloged_paths = {t.local_path for t in self.templates.values()}

        for json_file in self.lottie_dir.rglob("*.json"):
            # Skip catalogs, schemas, meta, tags files
            if any(x in json_file.name for x in ["catalog", ".schema.", ".meta.", "template-tags", "unified-catalog"]):
                continue

            rel_path = str(json_file.relative_to(self.lottie_dir)).replace("\\", "/")
            if rel_path in cataloged_paths:
                continue

            # Uncataloged file - add it
            category = json_file.parent.name
            source = "lottiefiles"  # Default
            if category.startswith("jitter-"):
                source = "jitter"
            elif category.startswith("lottieflow-"):
                source = "lottieflow"

            # Try to get info from the file
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                width = int(data.get("w", 0))
                height = int(data.get("h", 0))
                fps = float(data.get("fr", 30))
                ip = data.get("ip", 0)
                op = data.get("op", 0)
                duration = (op - ip) / fps if fps > 0 else 0
            except (json.JSONDecodeError, KeyError):
                width, height, fps, duration = 0, 0, 30.0, 0.0

            template_id = f"{source}-{json_file.stem}"
            template = TemplateInfo(
                id=template_id,
                name=json_file.stem.replace("-", " ").replace("_", " ").title(),
                category=category,
                source=source,
                local_path=rel_path,
                width=width,
                height=height,
                fps=fps,
                duration_seconds=round(duration, 2),
            )
            self.templates[template_id] = template

    def _detect_schemas(self) -> None:
        """Check which templates have schema files."""
        for template in self.templates.values():
            template_path = self.lottie_dir / template.local_path
            schema_path = template_path.with_suffix(".schema.json")

            if schema_path.exists():
                template.has_schema = True
                try:
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        schema = json.load(f)
                    template.schema_fields = list(schema.get("fields", {}).keys())
                    if schema.get("description"):
                        template.description = schema["description"]
                except (json.JSONDecodeError, KeyError):
                    pass

    def get(self, template_id: str) -> Optional[TemplateInfo]:
        """Get template by ID."""
        return self.templates.get(template_id)

    def get_by_path(self, local_path: str) -> Optional[TemplateInfo]:
        """Get template by local path."""
        normalized = local_path.replace("\\", "/")
        for template in self.templates.values():
            if template.local_path == normalized:
                return template
        return None

    def list_all(self) -> list[TemplateInfo]:
        """List all templates."""
        return list(self.templates.values())

    def list_by_category(self, category: str) -> list[TemplateInfo]:
        """List templates in a category."""
        return [t for t in self.templates.values() if t.category == category]

    def list_by_source(self, source: str) -> list[TemplateInfo]:
        """List templates from a source."""
        return [t for t in self.templates.values() if t.source == source]

    def list_with_schema(self) -> list[TemplateInfo]:
        """List templates that have schemas."""
        return [t for t in self.templates.values() if t.has_schema]

    def categories(self) -> list[str]:
        """Get all unique categories."""
        return sorted(set(t.category for t in self.templates.values()))

    def count(self) -> int:
        """Total template count."""
        return len(self.templates)

    def get_full_path(self, template: TemplateInfo) -> Path:
        """Get absolute path to template file."""
        return self.lottie_dir / template.local_path

    def save_unified(self, output_path: str | Path = None) -> Path:
        """Save unified catalog to JSON."""
        if output_path is None:
            output_path = self.lottie_dir / "unified-catalog.json"
        else:
            output_path = Path(output_path)

        data = {
            "version": "1.0",
            "total_count": self.count(),
            "sources": list(set(t.source for t in self.templates.values())),
            "categories": self.categories(),
            "templates": {
                tid: asdict(t) for tid, t in self.templates.items()
            }
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        return output_path

    def summary(self) -> dict:
        """Get catalog summary stats."""
        by_source = {}
        by_category = {}
        with_schema = 0

        for t in self.templates.values():
            by_source[t.source] = by_source.get(t.source, 0) + 1
            by_category[t.category] = by_category.get(t.category, 0) + 1
            if t.has_schema:
                with_schema += 1

        return {
            "total": self.count(),
            "with_schema": with_schema,
            "by_source": by_source,
            "by_category": by_category,
        }

    # =========================================================================
    # Tagging System
    # =========================================================================

    def add_tags(self, template_id: str, tags: list[str]) -> bool:
        """Add tags to a template."""
        template = self.templates.get(template_id)
        if not template:
            return False
        for tag in tags:
            if tag not in template.tags:
                template.tags.append(tag)
        return True

    def set_tags(self, template_id: str, tags: list[str]) -> bool:
        """Replace all tags on a template."""
        template = self.templates.get(template_id)
        if not template:
            return False
        template.tags = list(tags)
        return True

    def search_by_tag(self, tag: str) -> list[TemplateInfo]:
        """Find templates with a specific tag."""
        tag_lower = tag.lower()
        return [t for t in self.templates.values() if tag_lower in [x.lower() for x in t.tags]]

    def search_by_tags(self, tags: list[str], match_all: bool = False) -> list[TemplateInfo]:
        """Find templates matching tags (any or all)."""
        tags_lower = [t.lower() for t in tags]
        results = []
        for template in self.templates.values():
            template_tags_lower = [t.lower() for t in template.tags]
            if match_all:
                if all(t in template_tags_lower for t in tags_lower):
                    results.append(template)
            else:
                if any(t in template_tags_lower for t in tags_lower):
                    results.append(template)
        return results

    def auto_tag_all(self) -> int:
        """Auto-generate tags for all templates based on category and name."""
        count = 0
        for template in self.templates.values():
            new_tags = self._generate_tags(template)
            if new_tags:
                for tag in new_tags:
                    if tag not in template.tags:
                        template.tags.append(tag)
                        count += 1
        return count

    def _generate_tags(self, template: TemplateInfo) -> list[str]:
        """Generate tags from template metadata."""
        tags = []

        # Category-based tags
        category_tags = {
            "lower-thirds": ["lower-third", "name", "title", "speaker", "label"],
            "title-cards": ["title", "heading", "intro", "text"],
            "transitions": ["transition", "wipe", "fade", "animation"],
            "data-callouts": ["number", "counter", "statistic", "data"],
            "progress-bars": ["progress", "loading", "bar", "percentage"],
            "loaders": ["loading", "spinner", "wait", "animation"],
            "icons": ["icon", "symbol", "ui"],
            "jitter-text": ["text", "typography", "kinetic", "motion"],
            "jitter-icons": ["icon", "ui", "micro-interaction"],
            "lottieflow-menu-nav": ["menu", "navigation", "hamburger", "ui"],
            "lottieflow-arrow": ["arrow", "direction", "navigation", "slider"],
            "lottieflow-checkbox": ["checkbox", "toggle", "form", "ui"],
            "lottieflow-loading": ["loading", "spinner", "wait"],
            "lottieflow-play": ["play", "pause", "media", "button"],
            "lottieflow-scroll-down": ["scroll", "arrow", "navigation", "indicator"],
            "lottieflow-success": ["success", "check", "done", "confirmation"],
            "lottieflow-attention": ["attention", "alert", "notification", "emphasis"],
        }

        if template.category in category_tags:
            tags.extend(category_tags[template.category])

        # Name-based tags
        name_lower = template.name.lower()
        name_keywords = {
            "counter": ["counter", "number", "counting"],
            "reveal": ["reveal", "appear", "show"],
            "morph": ["morph", "transform", "shape"],
            "glide": ["glide", "slide", "smooth"],
            "bounce": ["bounce", "spring", "elastic"],
            "wipe": ["wipe", "transition"],
            "check": ["checkmark", "success", "done"],
            "arrow": ["arrow", "direction"],
            "menu": ["menu", "navigation"],
            "loading": ["loading", "loader"],
            "progress": ["progress", "bar"],
        }

        for keyword, keyword_tags in name_keywords.items():
            if keyword in name_lower:
                tags.extend(keyword_tags)

        # Dedupe and return
        return list(dict.fromkeys(tags))

    def save_tags(self, output_path: str | Path = None) -> Path:
        """Save all tags to a separate tags file for persistence."""
        if output_path is None:
            output_path = self.lottie_dir / "template-tags.json"
        else:
            output_path = Path(output_path)

        tags_data = {
            tid: t.tags for tid, t in self.templates.items() if t.tags
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(tags_data, f, indent=2)

        return output_path

    def load_tags(self, tags_path: str | Path = None) -> int:
        """Load tags from a tags file."""
        if tags_path is None:
            tags_path = self.lottie_dir / "template-tags.json"
        else:
            tags_path = Path(tags_path)

        if not tags_path.exists():
            return 0

        with open(tags_path, 'r', encoding='utf-8') as f:
            tags_data = json.load(f)

        count = 0
        for tid, tags in tags_data.items():
            if tid in self.templates:
                self.templates[tid].tags = tags
                count += 1

        return count


# =============================================================================
# Semantic Template Search
# =============================================================================

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass
class TemplateSearchResult:
    """A semantic search result with similarity score."""
    template: TemplateInfo
    score: float  # Similarity score (higher = more similar)


class TemplateSearch:
    """Semantic search over template catalog using ChromaDB."""

    COLLECTION_NAME = "nolan_templates"

    def __init__(
        self,
        catalog: TemplateCatalog,
        db_path: str | Path = None,
        embedding_model: str = EMBEDDING_MODEL
    ):
        """Initialize template search.

        Args:
            catalog: TemplateCatalog instance
            db_path: Path to ChromaDB storage (default: .template_vectors in lottie_dir)
            embedding_model: Sentence-transformers model for embeddings
        """
        self.catalog = catalog
        self.embedding_model = embedding_model

        if db_path is None:
            self.db_path = catalog.lottie_dir / ".template_vectors"
        else:
            self.db_path = Path(db_path)

        self.db_path.mkdir(parents=True, exist_ok=True)

        # Lazy init chromadb
        self._client = None
        self._embedding_fn = None
        self._collection = None

    def _get_client(self):
        """Get or create ChromaDB client."""
        if self._client is None:
            import chromadb
            from chromadb.config import Settings
            self._client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(anonymized_telemetry=False)
            )
        return self._client

    def _get_embedding_function(self):
        """Get or create embedding function."""
        if self._embedding_fn is None:
            from chromadb.utils import embedding_functions
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model
            )
        return self._embedding_fn

    def _get_collection(self):
        """Get or create templates collection."""
        if self._collection is None:
            self._collection = self._get_client().get_or_create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self._get_embedding_function(),
                metadata={"description": "Lottie animation templates"}
            )
        return self._collection

    def _template_to_document(self, template: TemplateInfo) -> str:
        """Convert template to searchable document text."""
        parts = [
            template.name,
            template.category.replace("-", " ").replace("_", " "),
            template.description if template.description else "",
            " ".join(template.tags),
        ]
        return " ".join(p for p in parts if p).strip()

    def index_templates(self, force: bool = False) -> int:
        """Index all templates into vector database.

        Args:
            force: If True, reindex all templates even if already indexed

        Returns:
            Number of templates indexed
        """
        collection = self._get_collection()

        # Get existing IDs
        existing = set()
        if not force:
            try:
                existing = set(collection.get()["ids"])
            except Exception:
                pass

        # Index templates
        count = 0
        for template in self.catalog.templates.values():
            if not force and template.id in existing:
                continue

            doc = self._template_to_document(template)
            if not doc:
                continue

            metadata = {
                "name": template.name,
                "category": template.category,
                "source": template.source,
                "local_path": template.local_path,
                "has_schema": template.has_schema,
                "tags": ",".join(template.tags[:10]),  # Limit for ChromaDB
            }

            collection.upsert(
                ids=[template.id],
                documents=[doc],
                metadatas=[metadata]
            )
            count += 1

        return count

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str = None,
        with_schema_only: bool = False
    ) -> list[TemplateSearchResult]:
        """Search templates by natural language query.

        Args:
            query: Natural language search query
            top_k: Number of results to return
            category: Filter to specific category
            with_schema_only: Only return templates with schemas

        Returns:
            List of TemplateSearchResult sorted by relevance
        """
        collection = self._get_collection()

        # Build where filter
        where = None
        where_conditions = []
        if category:
            where_conditions.append({"category": category})
        if with_schema_only:
            where_conditions.append({"has_schema": True})

        if len(where_conditions) == 1:
            where = where_conditions[0]
        elif len(where_conditions) > 1:
            where = {"$and": where_conditions}

        # Add query prefix for BGE model
        prefixed_query = QUERY_PREFIX + query

        # Search
        try:
            results = collection.query(
                query_texts=[prefixed_query],
                n_results=top_k,
                where=where
            )
        except Exception:
            # Collection might be empty
            return []

        # Convert to results
        search_results = []
        if results and results["ids"] and results["ids"][0]:
            for i, tid in enumerate(results["ids"][0]):
                template = self.catalog.get(tid)
                if template:
                    # ChromaDB returns distance, convert to similarity
                    distance = results["distances"][0][i] if results["distances"] else 0
                    score = 1 / (1 + distance)  # Convert distance to 0-1 score
                    search_results.append(TemplateSearchResult(
                        template=template,
                        score=score
                    ))

        return search_results

    def clear(self) -> None:
        """Clear the vector index."""
        try:
            self._get_client().delete_collection(self.COLLECTION_NAME)
            self._collection = None
        except Exception:
            pass


# =============================================================================
# Scene-to-Template Matching
# =============================================================================

# Map visual_type to template categories
VISUAL_TYPE_TO_CATEGORIES = {
    "lower-third": ["lower-thirds"],
    "text-overlay": ["title-cards", "jitter-text", "lower-thirds"],
    "title": ["title-cards", "jitter-text"],
    "infographic": ["data-callouts", "progress-bars"],
    "lottie": None,  # Any category
    "chart": ["data-callouts", "progress-bars"],
    "counter": ["data-callouts", "jitter-text"],
    "transition": ["transitions"],
    "icon": ["icons", "jitter-icons", "lottieflow-success", "lottieflow-attention"],
    "loading": ["loaders", "lottieflow-loading"],
    "ui": ["lottieflow-menu-nav", "lottieflow-checkbox", "lottieflow-play",
           "lottieflow-arrow", "lottieflow-scroll-down"],
}


def find_templates_for_scene(
    scene,  # Scene dataclass from nolan.scenes
    catalog: TemplateCatalog,
    search: TemplateSearch = None,
    top_k: int = 5,
    require_schema: bool = False
) -> list[TemplateSearchResult]:
    """Find matching templates for a scene.

    Uses visual_type to filter categories, then semantic search on visual_description.

    Args:
        scene: Scene object with visual_type and visual_description
        catalog: TemplateCatalog instance
        search: TemplateSearch instance (created if not provided)
        top_k: Number of results to return
        require_schema: Only return templates with schemas

    Returns:
        List of TemplateSearchResult sorted by relevance
    """
    if search is None:
        search = TemplateSearch(catalog)
        # Ensure indexed
        try:
            existing = search._get_collection().count()
            if existing == 0:
                search.index_templates()
        except Exception:
            search.index_templates()

    visual_type = getattr(scene, 'visual_type', None) or ''
    visual_desc = getattr(scene, 'visual_description', None) or ''
    narration = getattr(scene, 'narration_excerpt', None) or ''

    # Build search query from scene
    query_parts = []
    if visual_desc:
        query_parts.append(visual_desc)
    if narration:
        query_parts.append(narration[:100])  # Limit length

    if not query_parts:
        query_parts.append(visual_type)

    query = " ".join(query_parts)

    # Determine category filter
    category = None
    categories = VISUAL_TYPE_TO_CATEGORIES.get(visual_type.lower())

    if categories and len(categories) == 1:
        category = categories[0]
    # For multiple categories, we search all and filter results

    results = search.search(
        query=query,
        top_k=top_k * 2 if categories and len(categories) > 1 else top_k,
        category=category,
        with_schema_only=require_schema
    )

    # Filter by allowed categories if multiple
    if categories and len(categories) > 1:
        results = [r for r in results if r.template.category in categories]
        results = results[:top_k]

    return results


def match_scene_to_template(
    scene,
    catalog: TemplateCatalog,
    search: TemplateSearch = None,
    require_schema: bool = True
) -> Optional[TemplateInfo]:
    """Find the best matching template for a scene.

    Convenience method that returns just the top match.

    Args:
        scene: Scene object
        catalog: TemplateCatalog instance
        search: TemplateSearch instance
        require_schema: Only consider templates with schemas

    Returns:
        Best matching TemplateInfo or None
    """
    results = find_templates_for_scene(
        scene=scene,
        catalog=catalog,
        search=search,
        top_k=1,
        require_schema=require_schema
    )

    if results:
        return results[0].template
    return None
