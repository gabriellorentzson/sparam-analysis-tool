from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QLabel, QGroupBox

from app.models.loaded_dataset import MarkerReadout


class MarkerReadoutWidget(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__("Marker Readout", parent)
        self.axis_label = QLabel("None")
        self.x_label = QLabel("-")
        self.y_label = QLabel("-")
        layout = QFormLayout(self)
        layout.addRow("Plot", self.axis_label)
        layout.addRow("X", self.x_label)
        layout.addRow("Y", self.y_label)

    def update_readout(self, readout: MarkerReadout | None) -> None:
        if readout is None:
            self.axis_label.setText("None")
            self.x_label.setText("-")
            self.y_label.setText("-")
            return
        self.axis_label.setText(readout.axis_name)
        self.x_label.setText(f"{readout.x_label}: {readout.x_value:.4f}")
        self.y_label.setText(f"{readout.y_label}: {readout.y_value:.4f}")
