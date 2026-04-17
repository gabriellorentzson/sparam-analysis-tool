from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.loaded_dataset import FrequencyMarkerRow


class MarkerReadoutWidget(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Marker Readout", parent)
        self.active_file_label = QLabel("No file selected")
        self.frequency_input = QDoubleSpinBox()
        self.frequency_input.setRange(0.0, 200.0)
        self.frequency_input.setDecimals(6)
        self.frequency_input.setSuffix(" GHz")
        self.frequency_input.setSingleStep(0.1)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Trace", "Freq (GHz)", "dB loss"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.addWidget(self.active_file_label)
        layout.addWidget(self.frequency_input)
        layout.addWidget(self.table)

    def set_active_file(self, display_name: str | None) -> None:
        self.active_file_label.setText(display_name or "No file selected")

    def set_frequency_value(self, frequency_ghz: float) -> None:
        self.frequency_input.blockSignals(True)
        self.frequency_input.setValue(frequency_ghz)
        self.frequency_input.blockSignals(False)

    def update_rows(self, rows: Sequence[FrequencyMarkerRow]) -> None:
        self.table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)
            self.table.setItem(row_index, 0, QTableWidgetItem(row.trace_name))
            self.table.setItem(row_index, 1, QTableWidgetItem(f"{row.frequency_ghz:.6f}"))
            self.table.setItem(row_index, 2, QTableWidgetItem(f"{row.magnitude_db:.3f}"))
