from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import QSignalBlocker, QTimer, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QUrl

from app.analysis.sparam_loader import load_touchstone_dataset
from app.models.loaded_dataset import LoadedDataset, MarkerReadout
from app.plots.mpl_canvas import PlotCanvas
from app.services.update_checker import GitHubReleaseChecker, UpdateCheckError
from app.ui.widgets.file_list_widget import FileListWidget
from app.ui.widgets.marker_readout import MarkerReadoutWidget
from app.version import __version__


PLOT_COLORS = [
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#9467bd",
    "#ff7f0e",
    "#8c564b",
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"S-Parameter Analysis Tool v{__version__}")
        self.resize(1500, 900)

        self.datasets: dict[str, LoadedDataset] = {}
        self._next_color_index = 0
        self.update_checker = GitHubReleaseChecker(current_version=__version__)

        self.file_list = FileListWidget()
        self.file_list.itemChanged.connect(self._on_file_item_changed)
        self.summary_table = QTableWidget(0, 6)
        self.marker_readout = MarkerReadoutWidget()
        self.il_plot = PlotCanvas("Insertion Loss", "Frequency (GHz)", "SDD21 (dB)")
        self.tdr_plot = PlotCanvas("Differential TDR", "Time (ns)", "Impedance (Ohms)")
        self.il_plot.set_click_callback(self._handle_il_marker)
        self.tdr_plot.set_click_callback(self._handle_tdr_marker)

        self.freq_limit_ghz = QDoubleSpinBox()
        self.freq_limit_ghz.setRange(1.0, 200.0)
        self.freq_limit_ghz.setValue(30.0)
        self.freq_limit_ghz.setSuffix(" GHz")
        self.freq_limit_ghz.valueChanged.connect(self.refresh_plots)

        self.tdr_time_limit_ns = QDoubleSpinBox()
        self.tdr_time_limit_ns.setRange(0.1, 1e6)
        self.tdr_time_limit_ns.setDecimals(3)
        self.tdr_time_limit_ns.setValue(10.0)
        self.tdr_time_limit_ns.setSuffix(" ns")
        self.tdr_time_limit_ns.valueChanged.connect(self.refresh_plots)

        self.reference_impedance = QDoubleSpinBox()
        self.reference_impedance.setRange(1.0, 1000.0)
        self.reference_impedance.setDecimals(2)
        self.reference_impedance.setValue(100.0)
        self.reference_impedance.setSuffix(" Ohm")

        self.tdr_oversample = QSpinBox()
        self.tdr_oversample.setRange(1, 16)
        self.tdr_oversample.setValue(4)

        self.status_label = QLabel("Ready.")
        self._build_ui()
        self._configure_summary_table()

        QTimer.singleShot(1200, lambda: self.check_for_updates(silent_if_current=True))

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([340, 1100])

        root_layout.addWidget(splitter, stretch=1)
        root_layout.addWidget(self._build_summary_group(), stretch=0)
        root_layout.addWidget(self.status_label)
        self.setCentralWidget(central)

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        files_group = QGroupBox("Loaded Files")
        files_layout = QVBoxLayout(files_group)
        files_layout.addWidget(self.file_list)

        button_row = QHBoxLayout()
        load_button = QPushButton("Load .s4p Files")
        remove_button = QPushButton("Remove Selected")
        clear_button = QPushButton("Clear All")
        load_button.clicked.connect(self.load_files)
        remove_button.clicked.connect(self.remove_selected_files)
        clear_button.clicked.connect(self.clear_files)
        button_row.addWidget(load_button)
        button_row.addWidget(remove_button)
        button_row.addWidget(clear_button)
        files_layout.addLayout(button_row)

        settings_group = QGroupBox("Analysis Controls")
        settings_layout = QFormLayout(settings_group)
        settings_layout.addRow("IL Upper Limit", self.freq_limit_ghz)
        settings_layout.addRow("TDR Time Limit", self.tdr_time_limit_ns)
        settings_layout.addRow("Ref. Impedance", self.reference_impedance)
        settings_layout.addRow("TDR Oversample", self.tdr_oversample)

        action_group = QGroupBox("Actions")
        action_layout = QGridLayout(action_group)
        recalc_button = QPushButton("Recompute TDR")
        update_button = QPushButton("Check for Updates")
        autoscale_button = QPushButton("Autoscale Plots")
        recalc_button.clicked.connect(self.recompute_all_datasets)
        update_button.clicked.connect(lambda: self.check_for_updates(silent_if_current=False))
        autoscale_button.clicked.connect(self.refresh_plots)
        action_layout.addWidget(recalc_button, 0, 0)
        action_layout.addWidget(update_button, 0, 1)
        action_layout.addWidget(autoscale_button, 1, 0, 1, 2)

        layout.addWidget(files_group, stretch=1)
        layout.addWidget(settings_group)
        layout.addWidget(self.marker_readout)
        layout.addWidget(action_group)
        layout.addStretch(1)
        return widget

    def _build_right_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(self.il_plot, stretch=1)
        layout.addWidget(self.tdr_plot, stretch=1)
        return widget

    def _build_summary_group(self) -> QWidget:
        group = QGroupBox("Summary")
        layout = QVBoxLayout(group)
        layout.addWidget(self.summary_table)
        return group

    def _configure_summary_table(self) -> None:
        self.summary_table.setHorizontalHeaderLabels(
            [
                "Filename",
                "Start (GHz)",
                "Stop (GHz)",
                "Points",
                "SDD21 @ 13.28 GHz (dB)",
                "SDD21 @ 26.5625 GHz (dB)",
            ]
        )
        header = self.summary_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, self.summary_table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    def load_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Touchstone Files",
            "",
            "Touchstone Files (*.s4p);;All Files (*)",
        )
        if not file_paths:
            return

        loaded_count = 0
        for file_path in file_paths:
            if file_path in self.datasets:
                continue
            try:
                dataset = load_touchstone_dataset(
                    file_path=file_path,
                    reference_impedance_ohms=self.reference_impedance.value(),
                    tdr_oversample=self.tdr_oversample.value(),
                )
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(self, "Load Error", f"Could not load {file_path}:\n{exc}")
                continue

            dataset.color = PLOT_COLORS[self._next_color_index % len(PLOT_COLORS)]
            self._next_color_index += 1
            self.datasets[file_path] = dataset
            with QSignalBlocker(self.file_list):
                self.file_list.add_file(file_path, Path(file_path).name, checked=True)
            loaded_count += 1

        self.refresh_all_views()
        self.status_label.setText(f"Loaded {loaded_count} file(s).")

    def remove_selected_files(self) -> None:
        selected_paths = self.file_list.selected_file_paths()
        if not selected_paths:
            return
        for file_path in selected_paths:
            self.datasets.pop(file_path, None)
            self.file_list.remove_file(file_path)
        self.refresh_all_views()
        self.status_label.setText(f"Removed {len(selected_paths)} file(s).")

    def clear_files(self) -> None:
        self.datasets.clear()
        self.file_list.clear_files()
        self.marker_readout.update_readout(None)
        self.refresh_all_views()
        self.status_label.setText("Cleared all files.")

    def recompute_all_datasets(self) -> None:
        if not self.datasets:
            return

        updated_datasets: dict[str, LoadedDataset] = {}
        for file_path, existing in self.datasets.items():
            dataset = load_touchstone_dataset(
                file_path=file_path,
                reference_impedance_ohms=self.reference_impedance.value(),
                tdr_oversample=self.tdr_oversample.value(),
            )
            dataset.enabled = existing.enabled
            dataset.color = existing.color
            updated_datasets[file_path] = dataset

        self.datasets = updated_datasets
        self.refresh_all_views()
        self.status_label.setText("Recomputed TDR for loaded files.")

    def refresh_all_views(self) -> None:
        self.refresh_summary_table()
        self.refresh_plots()

    def refresh_summary_table(self) -> None:
        self.summary_table.setRowCount(0)
        for row_index, dataset in enumerate(self.datasets.values()):
            self.summary_table.insertRow(row_index)
            metrics = dataset.metrics
            values = [
                metrics["filename"],
                f"{metrics['freq_start_ghz']:.3f}",
                f"{metrics['freq_stop_ghz']:.3f}",
                str(metrics["point_count"]),
                self._format_metric(metrics["sdd21_db_13p28_ghz"]),
                self._format_metric(metrics["sdd21_db_26p5625_ghz"]),
            ]
            for column_index, value in enumerate(values):
                self.summary_table.setItem(row_index, column_index, QTableWidgetItem(value))

    def refresh_plots(self) -> None:
        self._plot_il()
        self._plot_tdr()

    def _plot_il(self) -> None:
        self.il_plot.clear()
        self.il_plot.reset_labels("Insertion Loss", "Frequency (GHz)", "SDD21 (dB)")
        x_limit = self.freq_limit_ghz.value()

        visible_count = 0
        for dataset in self.datasets.values():
            if not dataset.enabled:
                continue
            freq_ghz = dataset.frequency_hz / 1e9
            mask = freq_ghz <= x_limit
            if not np.any(mask):
                continue
            self.il_plot.axes.plot(
                freq_ghz[mask],
                dataset.sdd21_db[mask],
                label=dataset.display_name,
                linewidth=1.6,
                color=dataset.color,
            )
            visible_count += 1

        if visible_count:
            self.il_plot.axes.legend(loc="best")
        self.il_plot.axes.set_xlim(left=0.0, right=x_limit)
        self.il_plot.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
        self.il_plot.draw_idle()

    def _plot_tdr(self) -> None:
        self.tdr_plot.clear()
        self.tdr_plot.reset_labels("Differential TDR", "Time (ns)", "Impedance (Ohms)")
        x_limit = self.tdr_time_limit_ns.value()

        visible_count = 0
        for dataset in self.datasets.values():
            if not dataset.enabled:
                continue
            mask = dataset.tdr_time_ns <= x_limit
            if not np.any(mask):
                continue
            self.tdr_plot.axes.plot(
                dataset.tdr_time_ns[mask],
                dataset.tdr_impedance_ohms[mask],
                label=dataset.display_name,
                linewidth=1.6,
                color=dataset.color,
            )
            visible_count += 1

        if visible_count:
            self.tdr_plot.axes.legend(loc="best")
        self.tdr_plot.axes.set_xlim(left=0.0, right=x_limit)
        self.tdr_plot.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
        self.tdr_plot.draw_idle()

    def _handle_il_marker(self, x_value: float, _y_value: float) -> None:
        dataset = self._first_enabled_dataset()
        if dataset is None:
            return
        freq_ghz = dataset.frequency_hz / 1e9
        y_value = float(np.interp(x_value, freq_ghz, dataset.sdd21_db))
        self.il_plot.set_marker(x_value, y_value)
        self.marker_readout.update_readout(
            MarkerReadout(
                axis_name="Insertion Loss",
                x_label="Freq (GHz)",
                y_label="SDD21 (dB)",
                x_value=x_value,
                y_value=y_value,
            )
        )

    def _handle_tdr_marker(self, x_value: float, _y_value: float) -> None:
        dataset = self._first_enabled_dataset()
        if dataset is None:
            return
        y_value = float(np.interp(x_value, dataset.tdr_time_ns, dataset.tdr_impedance_ohms))
        self.tdr_plot.set_marker(x_value, y_value)
        self.marker_readout.update_readout(
            MarkerReadout(
                axis_name="Differential TDR",
                x_label="Time (ns)",
                y_label="Zdiff (Ohm)",
                x_value=x_value,
                y_value=y_value,
            )
        )

    def _first_enabled_dataset(self) -> LoadedDataset | None:
        for dataset in self.datasets.values():
            if dataset.enabled:
                return dataset
        return None

    def _on_file_item_changed(self, item) -> None:
        file_path = item.data(Qt.ItemDataRole.UserRole)
        dataset = self.datasets.get(file_path)
        if dataset is None:
            return
        dataset.enabled = item.checkState() == Qt.CheckState.Checked
        self.refresh_plots()

    def _format_metric(self, value: float | int | str) -> str:
        if isinstance(value, float):
            if np.isnan(value):
                return "N/A"
            return f"{value:.3f}"
        return str(value)

    def check_for_updates(self, silent_if_current: bool) -> None:
        try:
            info = self.update_checker.check_for_updates()
        except UpdateCheckError as exc:
            if not silent_if_current:
                QMessageBox.warning(self, "Update Check", str(exc))
            self.status_label.setText("Update check unavailable.")
            return

        if info.is_update_available:
            result = QMessageBox.question(
                self,
                "Update Available",
                (
                    f"Installed version: {info.current_version}\n"
                    f"Latest release: {info.latest_version}\n\n"
                    f"Open the release page?\n{info.html_url}"
                ),
            )
            if result == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(info.html_url))
            self.status_label.setText(f"Update available: {info.latest_version}")
            return

        self.status_label.setText("App is up to date.")
        if not silent_if_current:
            QMessageBox.information(self, "Update Check", "You are already on the latest version.")
