"""Tests for template catalog system."""

import pytest
from pathlib import Path
from dataclasses import dataclass

from nolan.template_catalog import (
    TemplateCatalog,
    TemplateInfo,
    TemplateSearch,
    TemplateSearchResult,
    find_templates_for_scene,
    match_scene_to_template,
    VISUAL_TYPE_TO_CATEGORIES,
)


class TestTemplateCatalog:
    """Tests for TemplateCatalog class."""

    def test_load_catalog(self):
        """Catalog loads templates from all sources."""
        catalog = TemplateCatalog()
        assert catalog.count() > 0
        assert len(catalog.categories()) > 0

    def test_get_by_id(self):
        """Can get template by ID."""
        catalog = TemplateCatalog()
        # Get first template
        templates = catalog.list_all()
        assert len(templates) > 0

        first = templates[0]
        result = catalog.get(first.id)
        assert result is not None
        assert result.id == first.id

    def test_get_nonexistent(self):
        """Returns None for non-existent template."""
        catalog = TemplateCatalog()
        result = catalog.get("nonexistent-id-12345")
        assert result is None

    def test_get_by_path(self):
        """Can get template by local path."""
        catalog = TemplateCatalog()
        templates = catalog.list_all()

        for t in templates:
            if t.local_path:
                result = catalog.get_by_path(t.local_path)
                assert result is not None
                break

    def test_list_by_category(self):
        """Can filter templates by category."""
        catalog = TemplateCatalog()
        categories = catalog.categories()

        if categories:
            cat = categories[0]
            results = catalog.list_by_category(cat)
            assert all(t.category == cat for t in results)

    def test_list_by_source(self):
        """Can filter templates by source."""
        catalog = TemplateCatalog()
        summary = catalog.summary()

        for source in summary['by_source']:
            results = catalog.list_by_source(source)
            assert len(results) > 0
            assert all(t.source == source for t in results)

    def test_list_with_schema(self):
        """Can filter templates with schemas."""
        catalog = TemplateCatalog()
        results = catalog.list_with_schema()
        assert all(t.has_schema for t in results)

    def test_summary(self):
        """Summary returns correct structure."""
        catalog = TemplateCatalog()
        summary = catalog.summary()

        assert 'total' in summary
        assert 'with_schema' in summary
        assert 'by_source' in summary
        assert 'by_category' in summary
        assert summary['total'] == catalog.count()


class TestTagging:
    """Tests for tagging system."""

    def test_auto_tag_all(self):
        """Auto-tagging generates tags."""
        catalog = TemplateCatalog()
        count = catalog.auto_tag_all()
        assert count > 0

    def test_search_by_tag(self):
        """Can search by single tag."""
        catalog = TemplateCatalog()
        catalog.auto_tag_all()

        results = catalog.search_by_tag("loading")
        # Should find loaders
        assert len(results) > 0

    def test_search_by_tags_any(self):
        """Can search by multiple tags (any match)."""
        catalog = TemplateCatalog()
        catalog.auto_tag_all()

        results = catalog.search_by_tags(["loading", "counter"], match_all=False)
        assert len(results) > 0

    def test_search_by_tags_all(self):
        """Can search requiring all tags."""
        catalog = TemplateCatalog()
        catalog.auto_tag_all()

        # Lower-thirds should have both "lower-third" and "name"
        results = catalog.search_by_tags(["lower-third", "name"], match_all=True)
        for r in results:
            assert "lower-third" in [t.lower() for t in r.tags]

    def test_add_tags(self):
        """Can add tags to template."""
        catalog = TemplateCatalog()
        templates = catalog.list_all()

        if templates:
            tid = templates[0].id
            result = catalog.add_tags(tid, ["custom-tag"])
            assert result is True
            assert "custom-tag" in catalog.get(tid).tags

    def test_set_tags(self):
        """Can replace all tags on template."""
        catalog = TemplateCatalog()
        templates = catalog.list_all()

        if templates:
            tid = templates[0].id
            result = catalog.set_tags(tid, ["only-this-tag"])
            assert result is True
            assert catalog.get(tid).tags == ["only-this-tag"]


class TestTemplateSearch:
    """Tests for semantic search."""

    @pytest.fixture
    def search_setup(self):
        """Set up catalog and search."""
        catalog = TemplateCatalog()
        catalog.load_tags()
        catalog.auto_tag_all()
        search = TemplateSearch(catalog)
        search.index_templates(force=True)
        return catalog, search

    def test_index_templates(self, search_setup):
        """Can index templates."""
        catalog, search = search_setup
        # Already indexed in fixture
        count = search.index_templates(force=False)
        # Should skip all since already indexed
        assert count == 0

    def test_search_returns_results(self, search_setup):
        """Search returns results."""
        catalog, search = search_setup
        results = search.search("loading spinner animation", top_k=5)
        assert len(results) > 0
        assert all(isinstance(r, TemplateSearchResult) for r in results)

    def test_search_with_category_filter(self, search_setup):
        """Search can filter by category."""
        catalog, search = search_setup
        results = search.search("animation", top_k=10, category="loaders")
        assert all(r.template.category == "loaders" for r in results)

    def test_search_scores_descending(self, search_setup):
        """Results are sorted by score descending."""
        catalog, search = search_setup
        results = search.search("lower third name", top_k=5)
        if len(results) > 1:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)


class TestSceneMatching:
    """Tests for scene-to-template matching."""

    @dataclass
    class MockScene:
        visual_type: str
        visual_description: str
        narration_excerpt: str = ""

    def test_find_templates_for_scene(self):
        """Can find templates for a scene."""
        catalog = TemplateCatalog()
        catalog.load_tags()
        catalog.auto_tag_all()

        scene = self.MockScene(
            visual_type="counter",
            visual_description="show statistic counting up"
        )
        results = find_templates_for_scene(scene, catalog, top_k=3)
        assert len(results) > 0

    def test_match_scene_to_template(self):
        """Can get single best match."""
        catalog = TemplateCatalog()
        catalog.load_tags()
        catalog.auto_tag_all()

        scene = self.MockScene(
            visual_type="lower-third",
            visual_description="show speaker name"
        )
        result = match_scene_to_template(scene, catalog, require_schema=False)
        assert result is not None
        assert isinstance(result, TemplateInfo)

    def test_visual_type_routing(self):
        """Visual type routes to correct categories."""
        assert "lower-thirds" in VISUAL_TYPE_TO_CATEGORIES.get("lower-third", [])
        assert "loaders" in VISUAL_TYPE_TO_CATEGORIES.get("loading", [])
        assert "transitions" in VISUAL_TYPE_TO_CATEGORIES.get("transition", [])
