from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import numpy as np
from PyQt6.QtCore import QSignalBlocker, QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.analysis.metrics import build_summary_metrics, magnitude_db
from app.analysis.mixed_mode import PAIRING_OPTIONS, single_ended_to_mixed_mode
from app.models.loaded_dataset import FrequencyMarkerRow, LoadedDataset
from app.plots.mpl_canvas import PlotCanvas
from app.services.update_checker import (
    GitHubReleaseChecker,
    UpdateCheckError,
    UpdateInstallError,
    can_self_update,
    prepare_windows_self_update,
)
from app.ui.widgets.file_list_widget import FileListWidget
from app.ui.widgets.marker_readout import MarkerReadoutWidget
from app.version import __version__


PLOT_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]
MIXED_MODE_INDEX_LABELS = ("1", "2")
MIXED_MODE_FAMILIES = ("SDD", "SDC", "SCD", "SCC")
DEFAULT_TRACE = "SDD21"


def single_ended_trace_names() -> list[str]:
    return [f"S{i}{j}" for i in range(1, 5) for j in range(1, 5)]


def mixed_mode_trace_names() -> list[str]:
    return [
        f"{family}{i}{j}"
        for family in MIXED_MODE_FAMILIES
        for i in MIXED_MODE_INDEX_LABELS
        for j in MIXED_MODE_INDEX_LABELS
    ]


ALL_TRACE_NAMES = single_ended_trace_names() + mixed_mode_trace_names()

_SPARAM_LOADER_MODULE: ModuleType | None = None
_TDR_MODULE: ModuleType | None = None


def load_touchstone_dataset_lazy(file_path: str) -> LoadedDataset:
    global _SPARAM_LOADER_MODULE
    if _SPARAM_LOADER_MODULE is None:
        _SPARAM_LOADER_MODULE = importlib.import_module("app.analysis.sparam_loader")
    return _SPARAM_LOADER_MODULE.load_touchstone_dataset(file_path=file_path)


def compute_differential_tdr_lazy(*, frequency_hz, sdd11, reference_impedance_ohms, oversample):
    global _TDR_MODULE
    if _TDR_MODULE is None:
        _TDR_MODULE = importlib.import_module("app.analysis.tdr")
    return _TDR_MODULE.compute_differential_tdr(
        frequency_hz=frequency_hz,
        sdd11=sdd11,
        reference_impedance_ohms=reference_impedance_ohms,
        oversample=oversample,
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"S-Parameter Analysis Tool v{__version__}")
        self.resize(1600, 940)

        self.datasets: dict[str, LoadedDataset] = {}
        self.trace_checkboxes: dict[str, QCheckBox] = {}
        self._next_color_index = 0
        self._frequency_marker_ghz = 13.28
        self._tdr_marker_time_ns = 0.0
        self.update_checker = GitHubReleaseChecker(current_version=__version__)

        self.file_list = FileListWidget()
        self.file_list.itemChanged.connect(self._on_file_item_changed)
        self.file_list.itemSelectionChanged.connect(self._on_selected_file_changed)
        self.file_list.files_dropped.connect(self.load_files_from_paths)

        self.summary_table = QTableWidget(0, 6)
        self.marker_readout = MarkerReadoutWidget()
        self.marker_readout.frequency_input.valueChanged.connect(self._on_manual_marker_frequency_changed)
        self.il_plot = PlotCanvas("Frequency-Domain Plot", "Frequency (GHz)", "Magnitude (dB)")
        self.tdr_plot = PlotCanvas("Differential TDR", "Time (ns)", "Impedance (Ohms)")
        self.il_plot.set_click_callback(self._handle_il_marker)
        self.il_plot.set_drag_callback(self._handle_il_marker)
        self.il_plot.set_hover_callback(self._handle_il_hover)
        self.tdr_plot.set_click_callback(self._handle_tdr_marker)

        self.freq_limit_ghz = QDoubleSpinBox()
        self.freq_limit_ghz.setRange(1.0, 1000.0)
        self.freq_limit_ghz.setValue(30.0)
        self.freq_limit_ghz.setSuffix(" GHz")
        self.freq_limit_ghz.valueChanged.connect(self.refresh_plots)
        self.freq_limit_ghz.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.freq_limit_from_file_button = QPushButton("From file")
        self.freq_limit_from_file_button.clicked.connect(self._apply_frequency_limit_from_file)

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

        self.port_pairing = QComboBox()
        self.port_pairing.addItems(PAIRING_OPTIONS.keys())
        self.port_pairing.setCurrentText("Ports (1,3) / (2,4)")
        self.port_pairing.currentIndexChanged.connect(self._rebuild_derived_data)

        self.hover_readout_label = QLabel("Hover: -")
        self.status_label = QLabel("Ready.")
        self._build_ui()
        self._configure_summary_table()
        self.marker_readout.set_frequency_value(self._frequency_marker_ghz)

        QTimer.singleShot(1200, lambda: self.check_for_updates(silent_if_current=True))

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([430, 1170])
        root_layout.addWidget(splitter, stretch=1)
        root_layout.addWidget(self._build_summary_group())
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
        il_limit_widget = QWidget()
        il_limit_layout = QHBoxLayout(il_limit_widget)
        il_limit_layout.setContentsMargins(0, 0, 0, 0)
        il_limit_layout.addWidget(self.freq_limit_ghz, stretch=1)
        il_limit_layout.addWidget(self.freq_limit_from_file_button)
        settings_layout.addRow("IL Upper Limit", il_limit_widget)
        settings_layout.addRow("TDR Time Limit", self.tdr_time_limit_ns)
        settings_layout.addRow("Ref. Impedance", self.reference_impedance)
        settings_layout.addRow("TDR Oversample", self.tdr_oversample)
        settings_layout.addRow("Port Pairing", self.port_pairing)

        traces_group = QGroupBox("Frequency Traces")
        traces_layout = QVBoxLayout(traces_group)
        traces_layout.addWidget(self._build_trace_selector())

        action_group = QGroupBox("Actions")
        action_layout = QGridLayout(action_group)
        recalc_button = QPushButton("Recompute TDR")
        update_button = QPushButton("Check for Updates")
        refresh_button = QPushButton("Refresh Plots")
        recalc_button.clicked.connect(self._rebuild_derived_data)
        update_button.clicked.connect(lambda: self.check_for_updates(silent_if_current=False))
        refresh_button.clicked.connect(self.refresh_all_views)
        action_layout.addWidget(recalc_button, 0, 0)
        action_layout.addWidget(update_button, 0, 1)
        action_layout.addWidget(refresh_button, 1, 0, 1, 2)

        layout.addWidget(files_group, stretch=1)
        layout.addWidget(settings_group)
        layout.addWidget(traces_group, stretch=1)
        layout.addWidget(self.marker_readout, stretch=1)
        layout.addWidget(self.hover_readout_label)
        layout.addWidget(action_group)
        return widget

    def _build_trace_selector(self) -> QWidget:
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(6, 6, 6, 6)
        for index, trace_name in enumerate(ALL_TRACE_NAMES):
            checkbox = QCheckBox(trace_name)
            checkbox.setChecked(trace_name == DEFAULT_TRACE)
            checkbox.toggled.connect(self._on_trace_selection_changed)
            grid.addWidget(checkbox, index // 4, index % 4)
            self.trace_checkboxes[trace_name] = checkbox

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

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
        if file_paths:
            self.load_files_from_paths(file_paths)

    def load_files_from_paths(self, file_paths: list[str]) -> None:
        loaded_count = 0
        for file_path in file_paths:
            if file_path in self.datasets:
                continue
            try:
                dataset = load_touchstone_dataset_lazy(file_path=file_path)
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(self, "Load Error", f"Could not load {file_path}:\n{exc}")
                continue

            dataset.color = PLOT_COLORS[self._next_color_index % len(PLOT_COLORS)]
            self._next_color_index += 1
            self.datasets[file_path] = dataset
            with QSignalBlocker(self.file_list):
                self.file_list.add_file(file_path, Path(file_path).name, checked=True)
            loaded_count += 1

        if loaded_count == 0:
            return
        self._rebuild_derived_data()
        self._apply_frequency_limit_from_file()
        if self.file_list.currentItem() is None and self.file_list.count() > 0:
            self.file_list.setCurrentRow(0)
        self.status_label.setText(f"Loaded {loaded_count} file(s).")

    def remove_selected_files(self) -> None:
        selected_paths = self.file_list.selected_file_paths()
        if not selected_paths:
            return
        for file_path in selected_paths:
            self.datasets.pop(file_path, None)
            self.file_list.remove_file(file_path)
        self._apply_frequency_limit_from_file()
        self.refresh_all_views()
        self.status_label.setText(f"Removed {len(selected_paths)} file(s).")

    def clear_files(self) -> None:
        self.datasets.clear()
        self.file_list.clear_files()
        self.marker_readout.set_active_file(None)
        self.marker_readout.update_rows([])
        self.freq_limit_ghz.setValue(30.0)
        self.hover_readout_label.setText("Hover: -")
        self.refresh_all_views()
        self.status_label.setText("Cleared all files.")

    def _current_port_order(self) -> tuple[int, int, int, int]:
        return PAIRING_OPTIONS[self.port_pairing.currentText()]

    def _rebuild_derived_data(self) -> None:
        if not self.datasets:
            self.refresh_all_views()
            return
        port_order = self._current_port_order()
        for dataset in self.datasets.values():
            mixed_mode = single_ended_to_mixed_mode(dataset.raw_s_parameters, port_order=port_order)
            sdd11 = mixed_mode[:, 0, 0]
            sdd21 = mixed_mode[:, 1, 0]
            tdr_result = compute_differential_tdr_lazy(
                frequency_hz=dataset.frequency_hz,
                sdd11=sdd11,
                reference_impedance_ohms=self.reference_impedance.value(),
                oversample=self.tdr_oversample.value(),
            )
            dataset.mixed_mode_s_parameters = mixed_mode
            dataset.tdr_time_ns = tdr_result.time_ns
            dataset.tdr_impedance_ohms = tdr_result.impedance_ohms
            dataset.metrics = build_summary_metrics(dataset.display_name, dataset.frequency_hz, sdd21)
        self.refresh_all_views()
        self.status_label.setText("Updated derived traces for current pairing.")

    def _apply_frequency_limit_from_file(self) -> None:
        if not self.datasets:
            self.freq_limit_ghz.blockSignals(True)
            self.freq_limit_ghz.setValue(30.0)
            self.freq_limit_ghz.blockSignals(False)
            self.refresh_plots()
            return
        max_stop_ghz = max(float(dataset.frequency_hz[-1] / 1e9) for dataset in self.datasets.values())
        self.freq_limit_ghz.blockSignals(True)
        self.freq_limit_ghz.setValue(max_stop_ghz)
        self.freq_limit_ghz.blockSignals(False)
        self.refresh_plots()

    def refresh_all_views(self) -> None:
        self.refresh_summary_table()
        self.refresh_plots()
        self.refresh_marker_readout()

    def refresh_summary_table(self) -> None:
        self.summary_table.setRowCount(0)
        for row_index, dataset in enumerate(self.datasets.values()):
            self.summary_table.insertRow(row_index)
            metrics = dataset.metrics
            values = [
                metrics.get("filename", dataset.display_name),
                self._format_metric(metrics.get("freq_start_ghz", float("nan"))),
                self._format_metric(metrics.get("freq_stop_ghz", float("nan"))),
                str(metrics.get("point_count", "")),
                self._format_metric(metrics.get("sdd21_db_13p28_ghz", float("nan"))),
                self._format_metric(metrics.get("sdd21_db_26p5625_ghz", float("nan"))),
            ]
            for column_index, value in enumerate(values):
                self.summary_table.setItem(row_index, column_index, QTableWidgetItem(value))

    def refresh_plots(self) -> None:
        self._plot_frequency_traces()
        self._plot_tdr()

    def _plot_frequency_traces(self) -> None:
        self.il_plot.clear()
        self.il_plot.reset_labels("Frequency-Domain Plot", "Frequency (GHz)", "Magnitude (dB)")
        x_limit = self.freq_limit_ghz.value()
        visible_count = 0
        selected_traces = self.selected_trace_names()
        selected_dataset = self._selected_dataset()
        for dataset in self.datasets.values():
            if not dataset.enabled:
                continue
            freq_ghz = dataset.frequency_hz / 1e9
            mask = freq_ghz <= x_limit
            if not np.any(mask):
                continue
            is_selected = dataset is selected_dataset
            for trace_name in selected_traces:
                trace_db = magnitude_db(self._trace_values(dataset, trace_name))
                self.il_plot.axes.plot(
                    freq_ghz[mask],
                    trace_db[mask],
                    label=f"{dataset.display_name}: {trace_name}",
                    linewidth=2.3 if is_selected else 1.3,
                    alpha=1.0 if is_selected else 0.85,
                )
                visible_count += 1
        if visible_count:
            self.il_plot.axes.legend(loc="best", fontsize=8)
        self.il_plot.axes.set_xlim(left=0.0, right=x_limit)
        self.il_plot.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
        if self._selected_dataset() is not None:
            self.il_plot.set_vertical_marker(self._frequency_marker_ghz)
        self.il_plot.draw_idle()

    def _plot_tdr(self) -> None:
        self.tdr_plot.clear()
        self.tdr_plot.reset_labels("Differential TDR", "Time (ns)", "Impedance (Ohms)")
        x_limit = self.tdr_time_limit_ns.value()
        visible_count = 0
        selected_dataset = self._selected_dataset()
        for dataset in self.datasets.values():
            if not dataset.enabled:
                continue
            mask = dataset.tdr_time_ns <= x_limit
            if not np.any(mask):
                continue
            is_selected = dataset is selected_dataset
            self.tdr_plot.axes.plot(
                dataset.tdr_time_ns[mask],
                dataset.tdr_impedance_ohms[mask],
                label=dataset.display_name,
                linewidth=2.6 if is_selected else 1.6,
                color=dataset.color,
                alpha=1.0 if is_selected else 0.85,
            )
            visible_count += 1
        if visible_count:
            self.tdr_plot.axes.legend(loc="best")
        self.tdr_plot.axes.set_xlim(left=0.0, right=x_limit)
        self.tdr_plot.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
        if selected_dataset is not None:
            tdr_value = float(
                np.interp(
                    min(self._tdr_marker_time_ns, x_limit),
                    selected_dataset.tdr_time_ns,
                    selected_dataset.tdr_impedance_ohms,
                )
            )
            self.tdr_plot.set_point_marker(min(self._tdr_marker_time_ns, x_limit), tdr_value)
        self.tdr_plot.draw_idle()

    def refresh_marker_readout(self) -> None:
        dataset = self._selected_dataset()
        self.marker_readout.set_active_file(dataset.display_name if dataset else None)
        if dataset is None:
            self.marker_readout.update_rows([])
            return
        rows: list[FrequencyMarkerRow] = []
        for trace_name in self.selected_trace_names():
            trace_db = magnitude_db(self._trace_values(dataset, trace_name))
            value = np.interp(self._frequency_marker_ghz * 1e9, dataset.frequency_hz, trace_db)
            rows.append(
                FrequencyMarkerRow(
                    trace_name=trace_name,
                    frequency_ghz=self._frequency_marker_ghz,
                    magnitude_db=float(value),
                )
            )
        self.marker_readout.update_rows(rows)

    def selected_trace_names(self) -> list[str]:
        return [trace_name for trace_name, checkbox in self.trace_checkboxes.items() if checkbox.isChecked()]

    def _trace_values(self, dataset: LoadedDataset, trace_name: str) -> np.ndarray:
        if len(trace_name) == 3:
            row = int(trace_name[1]) - 1
            column = int(trace_name[2]) - 1
            return dataset.raw_s_parameters[:, row, column]
        family = trace_name[:3]
        row = int(trace_name[3]) - 1
        column = int(trace_name[4]) - 1
        family_offsets = {"SDD": (0, 0), "SDC": (0, 2), "SCD": (2, 0), "SCC": (2, 2)}
        row_offset, column_offset = family_offsets[family]
        return dataset.mixed_mode_s_parameters[:, row + row_offset, column + column_offset]

    def _selected_dataset(self) -> LoadedDataset | None:
        current_item = self.file_list.currentItem()
        if current_item is None:
            return None
        return self.datasets.get(current_item.data(Qt.ItemDataRole.UserRole))

    def _on_selected_file_changed(self) -> None:
        self.refresh_marker_readout()
        self.refresh_plots()

    def _on_file_item_changed(self, item: QListWidgetItem) -> None:
        dataset = self.datasets.get(item.data(Qt.ItemDataRole.UserRole))
        if dataset is None:
            return
        dataset.enabled = item.checkState() == Qt.CheckState.Checked
        self.refresh_plots()
        self.refresh_marker_readout()

    def _on_trace_selection_changed(self) -> None:
        self.refresh_plots()
        self.refresh_marker_readout()

    def _on_manual_marker_frequency_changed(self, frequency_ghz: float) -> None:
        self._frequency_marker_ghz = frequency_ghz
        self.refresh_plots()
        self.refresh_marker_readout()

    def _handle_il_marker(self, x_value: float, _y_value: float) -> None:
        self._frequency_marker_ghz = max(0.0, x_value)
        self.marker_readout.set_frequency_value(self._frequency_marker_ghz)
        self.refresh_plots()
        self.refresh_marker_readout()

    def _handle_tdr_marker(self, x_value: float, _y_value: float) -> None:
        self._tdr_marker_time_ns = max(0.0, x_value)
        self.refresh_plots()

    def _handle_il_hover(self, x_value: float | None, _y_value: float | None) -> None:
        dataset = self._selected_dataset()
        if dataset is None or x_value is None:
            self.hover_readout_label.setText("Hover: -")
            return

        trace_names = self.selected_trace_names()
        if not trace_names:
            self.hover_readout_label.setText("Hover: no traces selected")
            return

        frequency_ghz = max(0.0, x_value)
        parts = []
        for trace_name in trace_names:
            trace_db = magnitude_db(self._trace_values(dataset, trace_name))
            value = float(np.interp(frequency_ghz * 1e9, dataset.frequency_hz, trace_db))
            parts.append(f"{trace_name} {value:.2f} dB")
        self.hover_readout_label.setText(f"Hover @ {frequency_ghz:.4f} GHz: " + " | ".join(parts))

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
            message_box = QMessageBox(self)
            message_box.setWindowTitle("Update Available")
            message_box.setIcon(QMessageBox.Icon.Information)
            message_box.setText(
                f"Installed version: {info.current_version}\n"
                f"Latest release: {info.latest_version}"
            )
            message_box.setInformativeText("Choose how you want to get the update.")
            install_button = None
            if can_self_update() and info.asset_download_url:
                install_button = message_box.addButton("Download and Install", QMessageBox.ButtonRole.AcceptRole)
            open_button = message_box.addButton("Open Release Page", QMessageBox.ButtonRole.ActionRole)
            cancel_button = message_box.addButton(QMessageBox.StandardButton.Cancel)
            message_box.exec()

            clicked = message_box.clickedButton()
            if install_button is not None and clicked == install_button:
                try:
                    prepare_windows_self_update(info)
                except UpdateInstallError as exc:
                    QMessageBox.warning(self, "Automatic Update", str(exc))
                    self.status_label.setText("Automatic update could not be started.")
                    return
                self.status_label.setText(f"Installing update {info.latest_version}...")
                QMessageBox.information(
                    self,
                    "Installing Update",
                    "The update was downloaded. The app will now close and restart after replacement.",
                )
                self.close()
                return

            if clicked == open_button:
                QDesktopServices.openUrl(QUrl(info.html_url))
            if clicked == cancel_button:
                self.status_label.setText(f"Update available: {info.latest_version}")
                return
            self.status_label.setText(f"Update available: {info.latest_version}")
            return

        self.status_label.setText("App is up to date.")
        if not silent_if_current:
            QMessageBox.information(self, "Update Check", "You are already on the latest version.")
