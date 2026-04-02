#!/usr/bin/env python3
"""Generate QAL 15 setup screenshots for work-instruction updates."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow


@dataclass(frozen=True)
class SampleWorkOrder:
    operator_id: str = 'OPR1472'
    shop_order: str = '65018432'
    part_id: str = 'SCP-10P-SPDT'
    sequence_id: str = '300'
    order_qty: str = '24'
    process: str = 'QAL15'
    ptp_setpoint: float = 10.0
    ptp_direction: str = 'Increasing'
    ptp_units: str = 'PSIG'


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Create QAL 15 setup screenshots for the work instruction.',
    )
    parser.add_argument(
        '--output-dir',
        default=str(ROOT / 'docs' / 'generated' / 'qal15'),
        help='Directory to write the PNG files into.',
    )
    return parser


def get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
        )
        app = QApplication([])
        app.setApplicationName('QAL15 Image Generator')
    return app


def process_events(app: QApplication, cycles: int = 6) -> None:
    for _ in range(cycles):
        app.processEvents()


def grab_widget(widget: QWidget, app: QApplication) -> QPixmap:
    widget.show()
    process_events(app)
    return widget.grab()


def add_header(content: QPixmap, title: str, subtitle: str) -> QImage:
    padding = 34
    header_height = 122
    width = content.width() + padding * 2
    height = content.height() + header_height + padding * 2
    canvas = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor('#f3f4f6'))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    title_font = QFont('Segoe UI', 24, QFont.Weight.Bold)
    subtitle_font = QFont('Segoe UI', 11)

    painter.setPen(QColor('#111827'))
    painter.setFont(title_font)
    painter.drawText(
        QRect(padding, 26, width - (padding * 2), 34),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        title,
    )

    painter.setPen(QColor('#4b5563'))
    painter.setFont(subtitle_font)
    painter.drawText(
        QRect(padding, 64, width - (padding * 2), 46),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
        subtitle,
    )

    image_rect = QRect(padding, header_height, content.width(), content.height())
    shadow_rect = image_rect.adjusted(8, 8, 8, 8)
    painter.fillRect(shadow_rect, QColor(17, 24, 39, 22))
    painter.fillRect(image_rect, QColor('white'))
    painter.setPen(QPen(QColor(17, 24, 39, 30), 1))
    painter.drawRect(image_rect)
    painter.drawPixmap(QPoint(image_rect.x(), image_rect.y()), content)
    painter.end()
    return canvas


def render_dialog_scene(
    app: QApplication,
    window: MainWindow,
    dialog: LoginDialog,
    title: str,
    subtitle: str,
) -> QImage:
    window_pixmap = grab_widget(window, app)
    dialog.adjustSize()
    dialog_pixmap = grab_widget(dialog, app)

    scene = QImage(
        window_pixmap.size(),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    scene.fill(QColor('white'))

    painter = QPainter(scene)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap(0, 0, window_pixmap)
    painter.fillRect(scene.rect(), QColor(15, 23, 42, 92))

    dialog_x = (scene.width() - dialog_pixmap.width()) // 2
    dialog_y = (scene.height() - dialog_pixmap.height()) // 2
    painter.fillRect(
        QRect(dialog_x + 10, dialog_y + 12, dialog_pixmap.width(), dialog_pixmap.height()),
        QColor(17, 24, 39, 35),
    )
    painter.drawPixmap(dialog_x, dialog_y, dialog_pixmap)
    painter.end()

    return add_header(QPixmap.fromImage(scene), title, subtitle)


def render_standalone_widget(widget: QWidget, app: QApplication, title: str, subtitle: str) -> QImage:
    content = grab_widget(widget, app)
    return add_header(content, title, subtitle)


def populate_validated_login(dialog: LoginDialog, sample: SampleWorkOrder) -> None:
    dialog.validation_timer.stop()
    for field, value in (
        (dialog.operator_id_input, sample.operator_id),
        (dialog.shop_order_input, sample.shop_order),
    ):
        previous = field.blockSignals(True)
        field.setText(value)
        field.blockSignals(previous)

    dialog.work_order_details = {
        'ShopOrder': sample.shop_order,
        'PartID': sample.part_id,
        'SequenceID': sample.sequence_id,
        'OrderQTY': sample.order_qty,
    }
    dialog._manual_entry_mode = False
    dialog._set_shop_order_validity(True)
    dialog._update_details(dialog.work_order_details)
    dialog.status_label.setText('Shop Order Validated.')
    dialog.status_label.setStyleSheet('color: #16a34a; font-weight: bold;')
    dialog._update_login_button_state()


def populate_main_window(window: MainWindow, sample: SampleWorkOrder) -> None:
    window.update_work_order_display(
        {
            'operator_id': sample.operator_id,
            'shop_order': sample.shop_order,
            'part_id': sample.part_id,
            'sequence_id': sample.sequence_id,
            'process_id': sample.process,
            'completed': 3,
            'total': 24,
        },
    )
    window._on_ptp_updated(
        {
            'part_id': sample.part_id,
            'sequence_id': sample.sequence_id,
            'source': 'Validated work order',
            'units_label': sample.ptp_units,
            'params': {
                'ActivationTarget': sample.ptp_setpoint,
                'TargetActivationDirection': sample.ptp_direction,
            },
        },
    )
    window._status_data.update(
        {
            'system': 'Ready',
            'database': 'Connected',
            'hardware': 'Online',
            'hardware_port_a': 'Ready',
            'hardware_port_b': 'Ready',
            'last_error': 'None',
        },
    )
    window._refresh_status_level()

    for serial, port in ((1207, window._port_a_widget), (1208, window._port_b_widget)):
        port.set_serial(serial)
        port.set_pressure(0.0, sample.ptp_units)
        port.set_pressure_visualization(
            {
                'min_psi': 0.0,
                'max_psi': 15.0,
                'activation_band': (9.85, 10.15),
                'deactivation_band': (9.45, 9.75),
                'show_atmosphere_reference': True,
                'show_acceptance_bands': True,
                'show_measured_points': False,
            },
        )
        port.set_result(None, None, None)
        port.set_switch_state(True, False)
        port.set_button_state(
            {
                'label': 'Pressurize',
                'enabled': True,
                'action': 'pressurize',
                'color': 'green',
            },
            {
                'label': 'Vent',
                'enabled': False,
                'action': 'vent',
            },
        )


def save_image(image: QImage, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(output_path)):
        raise RuntimeError(f'Failed to save image: {output_path}')


def generate_images(output_dir: Path) -> list[Path]:
    app = get_app()
    sample = SampleWorkOrder()
    created: list[Path] = []

    base_window = MainWindow(config={}, ui_bridge=None)
    base_window.resize(1600, 900)
    populate_main_window(base_window, sample)

    step1_dialog = LoginDialog(base_window, config={})
    step1_dialog.resize(560, step1_dialog.height())
    image = render_dialog_scene(
        app,
        base_window,
        step1_dialog,
        'WTL01460 Setup - Step 1',
        'Open the Stinger calibration program. The Operator Login window opens automatically when the station is ready.',
    )
    output_path = output_dir / 'qal15_wtl01460_setup_01_open_program.png'
    save_image(image, output_path)
    created.append(output_path)
    step1_dialog.close()

    step2_dialog = LoginDialog(base_window, config={})
    populate_validated_login(step2_dialog, sample)
    image = render_standalone_widget(
        step2_dialog,
        app,
        'WTL01460 Setup - Step 2',
        'Enter Operator ID and Work Order. After validation, Part ID and Sequence auto-populate and the Login button becomes available.',
    )
    output_path = output_dir / 'qal15_wtl01460_setup_02_login_validated.png'
    save_image(image, output_path)
    created.append(output_path)
    step2_dialog.close()

    ready_window = MainWindow(config={}, ui_bridge=None)
    ready_window.resize(1600, 900)
    populate_main_window(ready_window, sample)
    image = render_standalone_widget(
        ready_window,
        app,
        'WTL01460 Setup - Station Ready',
        'Reference view after login. Operator, work-order, PTP, and port status data are visible before calibration begins.',
    )
    output_path = output_dir / 'qal15_wtl01460_setup_03_station_ready.png'
    save_image(image, output_path)
    created.append(output_path)
    ready_window.close()
    base_window.close()

    process_events(app)
    return created


def main() -> int:
    args = build_arg_parser().parse_args()
    output_dir = Path(args.output_dir).resolve()
    created = generate_images(output_dir)
    print('Created QAL 15 setup images:')
    for path in created:
        print(f' - {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
