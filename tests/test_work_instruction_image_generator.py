from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QImage

from scripts._stinger_instruction_images import (
    RenderVariant,
    generate_instruction_images,
    get_app,
    workflow_scene_catalog,
)


def _image_bytes(path: Path) -> tuple[int, int, bytes]:
    image = QImage(str(path))
    assert not image.isNull()
    return image.width(), image.height(), image.bits().asstring(image.sizeInBytes())


def test_qal16_catalog_scene_ids_and_filenames() -> None:
    scenes = workflow_scene_catalog('qal16')
    assert [scene.id for scene in scenes] == [
        '01_login_open',
        '02_login_validated',
        '03_ready_to_test',
        '04_cycling_in_progress',
        '05_precision_test_in_progress',
        '06_review_pass',
        '07_review_fail_retest',
        '08_review_final_failure',
    ]
    assert [scene.filename_stem for scene in scenes] == [
        'qal16_01_login_open',
        'qal16_02_login_validated',
        'qal16_03_ready_to_test',
        'qal16_04_cycling_in_progress',
        'qal16_05_precision_test_in_progress',
        'qal16_06_review_pass',
        'qal16_07_review_fail_retest',
        'qal16_08_review_final_failure',
    ]


def test_qal16_single_dialog_scene_renders_annotated_and_clean(tmp_path: Path) -> None:
    get_app()
    exports, _ = generate_instruction_images(
        workflow='qal16',
        output_dir=tmp_path,
        variant=RenderVariant.BOTH.value,
        scene_id='01_login_open',
        review_sheet=False,
    )

    assert len(exports) == 2
    annotated = next(record.path for record in exports if record.variant == RenderVariant.ANNOTATED.value)
    clean = next(record.path for record in exports if record.variant == RenderVariant.CLEAN.value)
    assert annotated.exists()
    assert clean.exists()

    annotated_width, annotated_height, annotated_bytes = _image_bytes(annotated)
    clean_width, clean_height, clean_bytes = _image_bytes(clean)
    assert (annotated_width, annotated_height) == (clean_width, clean_height)
    assert annotated_bytes != clean_bytes


def test_qal16_single_main_scene_renders_annotated_and_clean(tmp_path: Path) -> None:
    get_app()
    exports, _ = generate_instruction_images(
        workflow='qal16',
        output_dir=tmp_path,
        variant=RenderVariant.BOTH.value,
        scene_id='06_review_pass',
        review_sheet=False,
    )

    assert len(exports) == 2
    annotated = next(record.path for record in exports if record.variant == RenderVariant.ANNOTATED.value)
    clean = next(record.path for record in exports if record.variant == RenderVariant.CLEAN.value)
    assert annotated.exists()
    assert clean.exists()

    annotated_width, annotated_height, annotated_bytes = _image_bytes(annotated)
    clean_width, clean_height, clean_bytes = _image_bytes(clean)
    assert (annotated_width, annotated_height) == (clean_width, clean_height)
    assert annotated_bytes != clean_bytes


def test_scene_filter_renders_only_requested_scene(tmp_path: Path) -> None:
    get_app()
    exports, review_path = generate_instruction_images(
        workflow='qal16',
        output_dir=tmp_path,
        variant=RenderVariant.ANNOTATED.value,
        scene_id='04_cycling_in_progress',
        review_sheet=True,
    )

    assert len(exports) == 1
    assert exports[0].scene.id == '04_cycling_in_progress'
    assert exports[0].path.name == 'qal16_04_cycling_in_progress.png'
    assert review_path is not None and review_path.exists()


def test_full_qal16_export_renders_all_scenes_and_review_sheet(tmp_path: Path) -> None:
    get_app()
    exports, review_path = generate_instruction_images(
        workflow='qal16',
        output_dir=tmp_path,
        variant=RenderVariant.ANNOTATED.value,
        scene_id='all',
        review_sheet=True,
    )

    assert len(exports) == 8
    assert review_path is not None and review_path.exists()
    annotated_dir = tmp_path / 'qal16' / 'annotated'
    assert sorted(path.name for path in annotated_dir.glob('*.png')) == [
        'qal16_01_login_open.png',
        'qal16_02_login_validated.png',
        'qal16_03_ready_to_test.png',
        'qal16_04_cycling_in_progress.png',
        'qal16_05_precision_test_in_progress.png',
        'qal16_06_review_pass.png',
        'qal16_07_review_fail_retest.png',
        'qal16_08_review_final_failure.png',
    ]
