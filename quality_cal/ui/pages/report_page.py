"""Final report page for the quality calibration wizard."""

from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWizardPage,
)

from quality_cal.core.report_generator import (
    build_report_html,
    build_text_document,
    export_report_pdf,
)


class ReportPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Final Report")
        self.setSubTitle("Review, print, and save the calibration report.")

        layout = QVBoxLayout(self)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.browser = QTextBrowser()
        layout.addWidget(self.browser, 1)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save PDF")
        self.save_button.clicked.connect(self._save_pdf)
        button_row.addWidget(self.save_button)

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._print_report)
        button_row.addWidget(self.print_button)

        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.clicked.connect(self._open_output_folder)
        button_row.addWidget(self.open_folder_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def initializePage(self) -> None:
        wizard = self.wizard()
        if wizard is None:
            return
        wizard.session.complete()
        self.browser.setHtml(build_report_html(wizard.session, wizard.settings))
        self.summary_label.setText(
            f"Output folder: {wizard.settings.report_output_dir}\n"
            f"Template reference: {wizard.settings.report_template_path}"
        )

    def _save_pdf(self) -> None:
        wizard = self.wizard()
        if wizard is None:
            return
        try:
            path = export_report_pdf(wizard.session, wizard.settings)
            wizard.session.last_report_path = path
            QMessageBox.information(self, "Report Saved", f"Saved report to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _print_report(self) -> None:
        wizard = self.wizard()
        if wizard is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec():
            document = build_text_document(wizard.session, wizard.settings)
            document.print(printer)

    def _open_output_folder(self) -> None:
        wizard = self.wizard()
        if wizard is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(wizard.settings.report_output_dir)))
