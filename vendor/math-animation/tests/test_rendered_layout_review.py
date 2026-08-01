from math_animation.expanded_planning import ExpandedPlanner
from math_animation.planning import PlanningRequest
from math_animation.review import _box_collisions, _layout_snapshots


def _comparison_project():
    return ExpandedPlanner().plan(
        PlanningRequest(
            project_id="layout-review",
            title="Layout review",
            script=(
                "Compare standard form $y=x^2-6x+5$ with vertex form "
                "$y=(x-3)^2-4$."
            ),
        )
    ).project


def _comparison_boxes(project):
    return _layout_snapshots(project)["beat-001"][
        "beat-001.comparison.show.stable"
    ]


def test_projected_review_reproduces_the_observed_formula_collision() -> None:
    project = _comparison_project()
    formulas = [
        item
        for item in project.beats[0].scene_program.objects
        if item.type == "math_tex"
    ]
    formulas[0].position = (-2.5, 0.0, 0.0)
    formulas[1].position = (2.5, 0.0, 0.0)
    collisions = _box_collisions(_comparison_boxes(project))
    assert len(collisions) == 1
    assert collisions[0]["object_ids"] == [
        "beat-001.comparison.left",
        "beat-001.comparison.right",
    ]
    assert collisions[0]["collision_type"] == (
        "insufficient_horizontal_separation"
    )


def test_current_comparison_template_has_safe_label_separation() -> None:
    project = _comparison_project()
    assert _box_collisions(_comparison_boxes(project)) == []
