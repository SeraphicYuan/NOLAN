from pathlib import Path

import pytest

from math_animation.contracts import (
    AssetRef,
    BeatSpec,
    ProjectSpec,
    RequestSpec,
    TitleCardBlock,
)
from math_animation.preflight import PreflightError, validate_local_inputs


def _project(*, assets: list[AssetRef]) -> ProjectSpec:
    return ProjectSpec(
        project_id="inputs",
        title="Inputs",
        request=RequestSpec(content="inputs"),
        assets=assets,
        beats=[
            BeatSpec(
                id="beat",
                title="Beat",
                learning_objective="test",
                duration_seconds=1.0,
                blocks=[TitleCardBlock(id="title", title="Test")],
            )
        ],
    )


def test_missing_asset_fails_local_preflight(tmp_path: Path) -> None:
    project = _project(
        assets=[
            AssetRef(
                id="missing",
                path=str(tmp_path / "missing.png"),
                media_type="image",
            )
        ]
    )
    with pytest.raises(PreflightError, match="missing local input"):
        validate_local_inputs(project, require_audio=False)


def test_asset_checksum_mismatch_fails(tmp_path: Path) -> None:
    asset = tmp_path / "asset.txt"
    asset.write_text("content", encoding="utf-8")
    project = _project(
        assets=[
            AssetRef(
                id="bad-checksum",
                path=str(asset),
                media_type="data",
                sha256="0" * 64,
            )
        ]
    )
    with pytest.raises(PreflightError, match="checksum mismatch"):
        validate_local_inputs(project, require_audio=False)
