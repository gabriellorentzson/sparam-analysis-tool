from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import numpy as np
from PyQt6.QtCore import QObject, QSignalBlocker, QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QProgressDialog,
    QPushButton,
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
    PreparedUpdate,
    UpdateCheckError,
    UpdateInstallError,
    can_self_update,
    launch_prepared_update,
    prepare_windows_self_update,
)
from app.ui.widgets.file_list_widget import FileListWidget
from app.ui.widgets.collapsible_section import CollapsibleSection
from app.ui.widgets.marker_readout import MarkerReadoutWidget
from app.version import __version__


PLOT_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]
TRACE_COLORS = [
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#f28e2b",
    "#4e79a7",
    "#9c755f",
]
MIXED_MODE_INDEX_LABELS = ("1", "2")
MIXED_MODE_FAMILIES = ("SDD", "SDC", "SCD", "SCC")
DEFAULT_TRACE = "SDD21"
TRACE_LINESTYLES = ["-", "--", "-.", ":"]
SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
INTERNAL_TDR_OVERSAMPLE = 4
FAVORITE_TRACE_NAMES = ["SDD21", "S21", "S12"]


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
_DEEMBED_MODULE: ModuleType | None = None
_TDR_MODULE: ModuleType | None = None


def load_touchstone_dataset_lazy(file_path: str) -> LoadedDataset:
    global _SPARAM_LOADER_MODULE
    if _SPARAM_LOADER_MODULE is None:
        _SPARAM_LOADER_MODULE = importlib.import_module("app.analysis.sparam_loader")
    return _SPARAM_LOADER_MODULE.load_touchstone_dataset(file_path=file_path)


def compute_differential_tdr_with_rise_time_lazy(
    *,
    frequency_hz,
    sdd11,
    reference_impedance_ohms,
    oversample,
    rise_time_ps,
):
    global _TDR_MODULE
    if _TDR_MODULE is None:
        _TDR_MODULE = importlib.import_module("app.analysis.tdr")
    return _TDR_MODULE.compute_differential_tdr(
        frequency_hz=frequency_hz,
        sdd11=sdd11,
        reference_impedance_ohms=reference_impedance_ohms,
        oversample=oversample,
        rise_time_ps=rise_time_ps,
    )


def minimum_supported_rise_time_ps_lazy(frequency_hz):
    global _TDR_MODULE
    if _TDR_MODULE is None:
        _TDR_MODULE = importlib.import_module("app.analysis.tdr")
    return _TDR_MODULE.minimum_supported_rise_time_ps(frequency_hz)


def dataset_from_network_lazy(network, *, file_path: str, display_name: str, source_note: str = "") -> LoadedDataset:
    global _SPARAM_LOADER_MODULE
    if _SPARAM_LOADER_MODULE is None:
        _SPARAM_LOADER_MODULE = importlib.import_module("app.analysis.sparam_loader")
    return _SPARAM_LOADER_MODULE.dataset_from_network(
        network,
        file_path=file_path,
        display_name=display_name,
        source_note=source_note,
    )


def deembed_datasets_lazy(dut_dataset, *, left_dataset=None, right_dataset=None, mode: str = "left"):
    global _DEEMBED_MODULE
    if _DEEMBED_MODULE is None:
        _DEEMBED_MODULE = importlib.import_module("app.analysis.deembedding")
    return _DEEMBED_MODULE.deembed_datasets(
        dut_dataset,
        left_dataset=left_dataset,
        right_dataset=right_dataset,
        mode=mode,
    )


def trace_linestyle(trace_name: str) -> str:
    if trace_name == "SDD21":
        return "-"
    style_index = sum(ord(character) for character in trace_name) % len(TRACE_LINESTYLES)
    return TRACE_LINESTYLES[style_index]


def trace_color(trace_name: str, dataset_color: str) -> str:
    if trace_name == "SDD21":
        return dataset_color
    color_index = sum(ord(character) for character in trace_name) % len(TRACE_COLORS)
    return TRACE_COLORS[color_index]


class UpdateInstallWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, update_info, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.update_info = update_info

    def run(self) -> None:
        try:
            prepared_update = prepare_windows_self_update(self.update_info)
        except UpdateInstallError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(prepared_update)


class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, value: float, display_text: str) -> None:
        super().__init__(display_text)
        self.numeric_value = value

    def __lt__(self, other) -> bool:
        if isinstance(other, NumericTableWidgetItem):
            return self.numeric_value < other.numeric_value
        return super().__lt__(other)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"S-Parameter Analysis Tool v{__version__}")
        self.resize(1600, 940)

        self.datasets: dict[str, LoadedDataset] = {}
        self.trace_checkboxes: dict[str, QCheckBox] = {}
        self._next_color_index = 0
        self._derived_dataset_counter = 0
        self._frequency_marker_ghz = 13.28
        self._tdr_marker_time_ns = 0.0
        self._update_thread: QThread | None = None
        self._update_worker: UpdateInstallWorker | None = None
        self._update_progress_dialog: QProgressDialog | None = None
        self._pending_prepared_update: PreparedUpdate | None = None
        self.update_checker = GitHubReleaseChecker(current_version=__version__)

        self.file_list = FileListWidget()
        self.file_list.itemChanged.connect(self._on_file_item_changed)
        self.file_list.itemSelectionChanged.connect(self._on_selected_file_changed)
        self.file_list.files_dropped.connect(self.load_files_from_paths)

        self.summary_table = QTableWidget(0, 7)
        self.marker_readout = MarkerReadoutWidget()
        self.marker_readout.frequency_input.valueChanged.connect(self._on_manual_marker_frequency_changed)
        self.il_plot = PlotCanvas("Frequency-Domain Plot", "Frequency (GHz)", "Magnitude (dB)")
        self.tdr_plot = PlotCanvas("Differential TDR", "Time (ns)", "Impedance (Ohms)")
        self.il_plot.set_click_callback(self._handle_il_marker)
        self.il_plot.set_drag_callback(self._handle_il_marker)
        self.il_plot.set_hover_callback(self._handle_il_hover)
        self.tdr_plot.set_click_callback(self._handle_tdr_marker)
        self.tdr_plot.set_hover_callback(self._handle_tdr_hover)
        self.il_plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tdr_plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.il_plot.customContextMenuRequested.connect(lambda pos: self._show_plot_visibility_menu(self.il_plot, pos))
        self.tdr_plot.customContextMenuRequested.connect(lambda pos: self._show_plot_visibility_menu(self.tdr_plot, pos))

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

        self.tdr_rise_time_ps = QDoubleSpinBox()
        self.tdr_rise_time_ps.setRange(1.0, 1000.0)
        self.tdr_rise_time_ps.setDecimals(1)
        self.tdr_rise_time_ps.setValue(20.0)
        self.tdr_rise_time_ps.setSuffix(" ps")
        self.tdr_rise_time_ps.valueChanged.connect(self._on_tdr_rise_time_changed)

        self.show_distance_axis = QCheckBox("Show distance axis")
        self.show_distance_axis.setChecked(True)
        self.show_distance_axis.toggled.connect(self.refresh_plots)

        self.er_eff = QDoubleSpinBox()
        self.er_eff.setRange(1.0, 20.0)
        self.er_eff.setDecimals(3)
        self.er_eff.setValue(4.0)
        self.er_eff.setSingleStep(0.1)
        self.er_eff.valueChanged.connect(self.refresh_plots)

        self.port_pairing = QComboBox()
        self.port_pairing.addItems(PAIRING_OPTIONS.keys())
        self.port_pairing.setCurrentText("Ports (1,3) / (2,4)")
        self.port_pairing.currentIndexChanged.connect(self._rebuild_derived_data)

        self.deembed_dut = QComboBox()
        self.deembed_left = QComboBox()
        self.deembed_right = QComboBox()
        self.deembed_mode = QComboBox()
        self.deembed_mode.addItem("Remove Left Fixture", "left")
        self.deembed_mode.addItem("Remove Right Fixture", "right")
        self.deembed_mode.addItem("Remove Both Sides (Same Fixture)", "both_same")
        self.deembed_mode.addItem("Remove Both Sides (Separate Fixtures)", "both_separate")
        self.deembed_mode.currentIndexChanged.connect(self._update_deembed_control_state)
        self.create_deembedded_button = QPushButton("Create De-Embedded Result")
        self.create_deembedded_button.clicked.connect(self.create_deembedded_dataset)

        self.sidebar_toggle_button = QPushButton("Hide Sidebar")
        self.sidebar_toggle_button.clicked.connect(self._toggle_sidebar)
        self.status_label = QLabel("Ready.")
        self._build_ui()
        self._configure_summary_table()
        self._refresh_deembed_selectors()
        self.marker_readout.set_frequency_value(self._frequency_marker_ghz)

        QTimer.singleShot(1200, lambda: self.check_for_updates(silent_if_current=True))

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.sidebar_toggle_button)
        top_bar.addStretch(1)
        root_layout.addLayout(top_bar)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.sidebar_widget = self._build_left_panel()
        self.main_splitter.addWidget(self.sidebar_widget)
        self.main_splitter.addWidget(self._build_right_panel())
        self.main_splitter.setSizes([430, 1170])
        root_layout.addWidget(self.main_splitter, stretch=1)
        root_layout.addWidget(self._build_bottom_panel())
        root_layout.addWidget(self.status_label)
        self.setCentralWidget(central)

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        files_section = CollapsibleSection("Loaded Files", expanded=True)
        files_container = QWidget()
        files_layout = QVBoxLayout(files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
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
        files_section.add_widget(files_container)

        settings_section = CollapsibleSection("Analysis Controls", expanded=False)
        settings_widget = QWidget()
        settings_layout = QFormLayout(settings_widget)
        il_limit_widget = QWidget()
        il_limit_layout = QHBoxLayout(il_limit_widget)
        il_limit_layout.setContentsMargins(0, 0, 0, 0)
        il_limit_layout.addWidget(self.freq_limit_ghz, stretch=1)
        il_limit_layout.addWidget(self.freq_limit_from_file_button)
        settings_layout.addRow("IL Upper Limit", il_limit_widget)
        settings_layout.addRow("TDR Time Limit", self.tdr_time_limit_ns)
        settings_layout.addRow("Ref. Impedance", self.reference_impedance)
        settings_layout.addRow("TDR Rise Time", self.tdr_rise_time_ps)
        settings_layout.addRow("Show Distance", self.show_distance_axis)
        settings_layout.addRow("Eff. Dk", self.er_eff)
        settings_layout.addRow("Port Pairing", self.port_pairing)
        settings_section.add_widget(settings_widget)

        traces_section = CollapsibleSection("Frequency Traces", expanded=False)
        traces_section.add_widget(self._build_trace_selector())

        deembed_section = CollapsibleSection("De-Embedding", expanded=False)
        deembed_widget = QWidget()
        deembed_layout = QFormLayout(deembed_widget)
        deembed_layout.addRow("DUT", self.deembed_dut)
        deembed_layout.addRow("Left Fixture", self.deembed_left)
        deembed_layout.addRow("Right Fixture", self.deembed_right)
        deembed_layout.addRow("Mode", self.deembed_mode)
        deembed_layout.addRow(self.create_deembedded_button)
        deembed_section.add_widget(deembed_widget)

        action_section = CollapsibleSection("Actions", expanded=False)
        action_widget = QWidget()
        action_layout = QGridLayout(action_widget)
        recalc_button = QPushButton("Recompute TDR")
        update_button = QPushButton("Check for Updates")
        refresh_button = QPushButton("Refresh Plots")
        recalc_button.clicked.connect(self._rebuild_derived_data)
        update_button.clicked.connect(lambda: self.check_for_updates(silent_if_current=False))
        refresh_button.clicked.connect(self.refresh_all_views)
        action_layout.addWidget(recalc_button, 0, 0)
        action_layout.addWidget(update_button, 0, 1)
        action_layout.addWidget(refresh_button, 1, 0, 1, 2)
        action_section.add_widget(action_widget)

        layout.addWidget(files_section)
        layout.addWidget(settings_section)
        layout.addWidget(traces_section)
        layout.addWidget(deembed_section)
        layout.addWidget(action_section)
        layout.addStretch(1)
        return widget

    def _build_trace_selector(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        favorites_widget = QWidget()
        favorites_grid = QGridLayout(favorites_widget)
        favorites_grid.setContentsMargins(6, 6, 6, 6)
        for index, trace_name in enumerate(FAVORITE_TRACE_NAMES):
            checkbox = QCheckBox(trace_name)
            checkbox.setChecked(trace_name == DEFAULT_TRACE)
            checkbox.toggled.connect(self._on_trace_selection_changed)
            favorites_grid.addWidget(checkbox, 0, index)
            self.trace_checkboxes[trace_name] = checkbox
        layout.addWidget(favorites_widget)

        advanced_section = CollapsibleSection("More Traces", expanded=False)
        advanced_widget = QWidget()
        advanced_grid = QGridLayout(advanced_widget)
        advanced_grid.setContentsMargins(6, 6, 6, 6)
        remaining_traces = [trace_name for trace_name in ALL_TRACE_NAMES if trace_name not in FAVORITE_TRACE_NAMES]
        for index, trace_name in enumerate(remaining_traces):
            checkbox = QCheckBox(trace_name)
            checkbox.setChecked(False)
            checkbox.toggled.connect(self._on_trace_selection_changed)
            advanced_grid.addWidget(checkbox, index // 4, index % 4)
            self.trace_checkboxes[trace_name] = checkbox
        advanced_section.add_widget(advanced_widget)
        layout.addWidget(advanced_section)
        return container

    def _build_right_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(self.il_plot, stretch=1)
        layout.addWidget(self.tdr_plot, stretch=1)
        return widget

    def _show_plot_visibility_menu(self, source_widget: QWidget, position) -> None:
        menu = QMenu(self)

        show_frequency_action = QAction("Show Frequency Plot", self)
        show_frequency_action.setCheckable(True)
        show_frequency_action.setChecked(self.il_plot.isVisible())

        show_tdr_action = QAction("Show TDR Plot", self)
        show_tdr_action.setCheckable(True)
        show_tdr_action.setChecked(self.tdr_plot.isVisible())

        toggle_sidebar_action = QAction("Hide Sidebar" if self.sidebar_widget.isVisible() else "Show Sidebar", self)

        menu.addAction(show_frequency_action)
        menu.addAction(show_tdr_action)
        menu.addSeparator()
        menu.addAction(toggle_sidebar_action)

        selected_action = menu.exec(source_widget.mapToGlobal(position))
        if selected_action is None:
            return
        if selected_action == toggle_sidebar_action:
            self._toggle_sidebar()
            return

        new_show_frequency = show_frequency_action.isChecked()
        new_show_tdr = show_tdr_action.isChecked()
        if not new_show_frequency and not new_show_tdr:
            QMessageBox.information(self, "Plot Visibility", "At least one plot must remain visible.")
            return

        self.il_plot.setVisible(new_show_frequency)
        self.tdr_plot.setVisible(new_show_tdr)
        self.status_label.setText(
            "Showing "
            + ("frequency and TDR plots" if new_show_frequency and new_show_tdr else "frequency plot" if new_show_frequency else "TDR plot")
            + "."
        )

    def _build_bottom_panel(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        summary_section = CollapsibleSection("Summary")
        summary_section.add_widget(self.summary_table)
        marker_section = CollapsibleSection("Marker Readout")
        marker_section.add_widget(self.marker_readout)
        layout.addWidget(summary_section, stretch=3)
        layout.addWidget(marker_section, stretch=2)
        return widget

    def _configure_summary_table(self) -> None:
        self.summary_table.setSortingEnabled(True)
        self.summary_table.setHorizontalHeaderLabels(
            [
                "Filename",
                "Start (GHz)",
                "Stop (GHz)",
                "Points",
                "TDR Rise (ps)",
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
        self._refresh_deembed_selectors()
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
        self._refresh_deembed_selectors()
        self._apply_frequency_limit_from_file()
        self.refresh_all_views()
        self.status_label.setText(f"Removed {len(selected_paths)} file(s).")

    def clear_files(self) -> None:
        self.datasets.clear()
        self.file_list.clear_files()
        self._refresh_deembed_selectors()
        self.marker_readout.set_active_file(None)
        self.marker_readout.update_rows([])
        self.freq_limit_ghz.setValue(30.0)
        self.il_plot.clear_hover_annotation()
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
            tdr_result = compute_differential_tdr_with_rise_time_lazy(
                frequency_hz=dataset.frequency_hz,
                sdd11=sdd11,
                reference_impedance_ohms=self.reference_impedance.value(),
                oversample=INTERNAL_TDR_OVERSAMPLE,
                rise_time_ps=self.tdr_rise_time_ps.value(),
            )
            dataset.mixed_mode_s_parameters = mixed_mode
            dataset.tdr_time_ns = tdr_result.time_ns
            dataset.tdr_impedance_ohms = tdr_result.impedance_ohms
            dataset.metrics = build_summary_metrics(dataset.display_name, dataset.frequency_hz, sdd21)
        self.refresh_all_views()
        self._update_tdr_rise_time_status()

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

    def _toggle_sidebar(self) -> None:
        is_hidden = self.sidebar_widget.isHidden()
        self.sidebar_widget.setVisible(is_hidden)
        self.sidebar_toggle_button.setText("Hide Sidebar" if is_hidden else "Show Sidebar")

    def _on_tdr_rise_time_changed(self) -> None:
        self._rebuild_derived_data()

    def _update_tdr_rise_time_status(self) -> None:
        if not self.datasets:
            self.status_label.setText("Ready.")
            return
        requested_rise_time_ps = self.tdr_rise_time_ps.value()
        min_supported_ps = max(minimum_supported_rise_time_ps_lazy(dataset.frequency_hz) for dataset in self.datasets.values())
        effective_rise_time_ps = max(requested_rise_time_ps, min_supported_ps)
        if effective_rise_time_ps > requested_rise_time_ps:
            self.status_label.setText(
                f"TDR rise time limited by bandwidth to {effective_rise_time_ps:.1f} ps."
            )
            return
        self.status_label.setText(f"TDR rise time set to {effective_rise_time_ps:.1f} ps.")

    def refresh_all_views(self) -> None:
        self.refresh_summary_table()
        self.refresh_plots()
        self.refresh_marker_readout()

    def _refresh_deembed_selectors(self) -> None:
        combos = [self.deembed_dut, self.deembed_left, self.deembed_right]
        current_values = [combo.currentData() for combo in combos]
        choices = list(self.datasets.items())

        for combo, previous in zip(combos, current_values):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(None)", "")
            for key, dataset in choices:
                combo.addItem(dataset.display_name, key)
            index = combo.findData(previous)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        self._update_deembed_control_state()

    def _update_deembed_control_state(self) -> None:
        mode = self.deembed_mode.currentData()
        if mode is None:
            mode = "left"
        self.deembed_left.setEnabled(mode in {"left", "both_same", "both_separate"})
        self.deembed_right.setEnabled(mode in {"right", "both_separate"})

    def create_deembedded_dataset(self) -> None:
        dut_key = self.deembed_dut.currentData()
        left_key = self.deembed_left.currentData()
        right_key = self.deembed_right.currentData()
        mode = self.deembed_mode.currentData() or "left"

        dut_dataset = self.datasets.get(dut_key or "")
        left_dataset = self.datasets.get(left_key or "") if left_key else None
        right_dataset = self.datasets.get(right_key or "") if right_key else None

        if dut_dataset is None:
            QMessageBox.warning(self, "De-Embedding", "Select a DUT dataset first.")
            return

        try:
            result_network = deembed_datasets_lazy(
                dut_dataset,
                left_dataset=left_dataset,
                right_dataset=right_dataset,
                mode=mode,
            )
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "De-Embedding", f"Could not create de-embedded result:\n{exc}")
            return

        self._derived_dataset_counter += 1
        derived_key = f"derived://deembed/{self._derived_dataset_counter}"
        derived_label = f"{dut_dataset.display_name} [deembedded]"
        derived_dataset = dataset_from_network_lazy(
            result_network,
            file_path=derived_key,
            display_name=derived_label,
            source_note=f"De-embedded from {dut_dataset.display_name}",
        )
        derived_dataset.color = PLOT_COLORS[self._next_color_index % len(PLOT_COLORS)]
        self._next_color_index += 1
        self.datasets[derived_key] = derived_dataset
        with QSignalBlocker(self.file_list):
            self.file_list.add_file(derived_key, derived_label, checked=True)
        self._refresh_deembed_selectors()
        self._rebuild_derived_data()
        self.status_label.setText(f"Created de-embedded result for {dut_dataset.display_name}.")

    def refresh_summary_table(self) -> None:
        sorting_enabled = self.summary_table.isSortingEnabled()
        self.summary_table.setSortingEnabled(False)
        self.summary_table.setRowCount(0)
        for row_index, dataset in enumerate(self.datasets.values()):
            self.summary_table.insertRow(row_index)
            metrics = dataset.metrics
            self.summary_table.setItem(row_index, 0, QTableWidgetItem(str(metrics.get("filename", dataset.display_name))))
            self.summary_table.setItem(
                row_index,
                1,
                self._create_numeric_item(metrics.get("freq_start_ghz", float("nan"))),
            )
            self.summary_table.setItem(
                row_index,
                2,
                self._create_numeric_item(metrics.get("freq_stop_ghz", float("nan"))),
            )
            point_count = float(metrics.get("point_count", float("nan")))
            self.summary_table.setItem(row_index, 3, NumericTableWidgetItem(point_count, str(metrics.get("point_count", ""))))
            self.summary_table.setItem(
                row_index,
                4,
                self._create_numeric_item(metrics.get("tdr_rise_time_ps", float("nan"))),
            )
            self.summary_table.setItem(
                row_index,
                5,
                self._create_numeric_item(metrics.get("sdd21_db_13p28_ghz", float("nan"))),
            )
            self.summary_table.setItem(
                row_index,
                6,
                self._create_numeric_item(metrics.get("sdd21_db_26p5625_ghz", float("nan"))),
            )
        self.summary_table.setSortingEnabled(sorting_enabled)

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
                    color=trace_color(trace_name, dataset.color),
                    linestyle=trace_linestyle(trace_name),
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
        if self.show_distance_axis.isChecked():
            self._add_tdr_distance_axis()
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

    def _add_tdr_distance_axis(self) -> None:
        er_eff = max(self.er_eff.value(), 1.0)
        propagation_velocity_mm_per_ns = (SPEED_OF_LIGHT_M_PER_S / np.sqrt(er_eff)) * 1e3 / 1e9

        def time_to_distance_mm(time_ns: float | np.ndarray) -> float | np.ndarray:
            return np.asarray(time_ns) * propagation_velocity_mm_per_ns / 2.0

        def distance_to_time_ns(distance_mm: float | np.ndarray) -> float | np.ndarray:
            return np.asarray(distance_mm) * 2.0 / propagation_velocity_mm_per_ns

        secondary_axis = self.tdr_plot.axes.secondary_xaxis("top", functions=(time_to_distance_mm, distance_to_time_ns))
        secondary_axis.set_xlabel("Distance (mm)")

    def refresh_marker_readout(self) -> None:
        selected_dataset = self._selected_dataset()
        self.marker_readout.set_active_file(selected_dataset.display_name if selected_dataset else "All visible traces/files")
        if not self.datasets:
            self.marker_readout.update_rows([])
            return
        rows: list[FrequencyMarkerRow] = []
        for dataset in self.datasets.values():
            if not dataset.enabled:
                continue
            for trace_name in self.selected_trace_names():
                trace_db = magnitude_db(self._trace_values(dataset, trace_name))
                value = np.interp(self._frequency_marker_ghz * 1e9, dataset.frequency_hz, trace_db)
                rows.append(
                    FrequencyMarkerRow(
                        trace_name=f"{dataset.display_name}: {trace_name}",
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

    def _hover_sample_for_selected_dataset(self, x_value_ghz: float) -> tuple[float, float, str] | None:
        dataset = self._selected_dataset()
        if dataset is None:
            return None

        trace_names = self.selected_trace_names()
        if not trace_names:
            return None

        freq_ghz = dataset.frequency_hz / 1e9
        best_sample: tuple[float, float, str] | None = None
        best_distance = float("inf")
        for trace_name in trace_names:
            trace_db = magnitude_db(self._trace_values(dataset, trace_name))
            index = int(np.argmin(np.abs(freq_ghz - x_value_ghz)))
            distance = abs(float(freq_ghz[index]) - x_value_ghz)
            if distance < best_distance:
                best_distance = distance
                best_sample = (float(freq_ghz[index]), float(trace_db[index]), trace_name)
        return best_sample

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
        if x_value is None:
            self.il_plot.clear_hover_annotation()
            return
        sample = self._hover_sample_for_selected_dataset(max(0.0, x_value))
        if sample is None:
            self.il_plot.clear_hover_annotation()
            return
        frequency_ghz, magnitude_db_value, trace_name = sample
        self.il_plot.set_hover_annotation(
            frequency_ghz,
            magnitude_db_value,
            f"{trace_name}\n{frequency_ghz:.4f} GHz\n{magnitude_db_value:.2f} dB",
        )

    def _handle_tdr_hover(self, x_value: float | None, _y_value: float | None) -> None:
        if x_value is None:
            self.tdr_plot.clear_hover_annotation()
            return

        dataset = self._selected_dataset()
        if dataset is None or not dataset.enabled:
            self.tdr_plot.clear_hover_annotation()
            return

        time_ns = dataset.tdr_time_ns
        if time_ns.size == 0:
            self.tdr_plot.clear_hover_annotation()
            return

        index = int(np.argmin(np.abs(time_ns - x_value)))
        sample_time_ns = float(time_ns[index])
        sample_impedance = float(dataset.tdr_impedance_ohms[index])
        self.tdr_plot.set_hover_annotation(
            sample_time_ns,
            sample_impedance,
            f"{dataset.display_name}\n{sample_time_ns:.4f} ns\n{sample_impedance:.2f} Ohm",
        )

    def _format_metric(self, value: float | int | str) -> str:
        if isinstance(value, float):
            if np.isnan(value):
                return "N/A"
            return f"{value:.3f}"
        return str(value)

    def _create_numeric_item(self, value: float | int | str) -> QTableWidgetItem:
        numeric_value = float(value) if isinstance(value, (int, float)) else float("nan")
        return NumericTableWidgetItem(numeric_value, self._format_metric(value))

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
                self._start_update_install(info)
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

    def _start_update_install(self, update_info) -> None:
        if self._update_thread is not None:
            return

        self.status_label.setText(f"Downloading update {update_info.latest_version}...")
        progress = QProgressDialog("Downloading and preparing update...", None, 0, 0, self)
        progress.setWindowTitle("Installing Update")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        self._update_progress_dialog = progress

        thread = QThread(self)
        worker = UpdateInstallWorker(update_info)
        worker.moveToThread(thread)
        self._update_worker = worker
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_update_prepared)
        worker.failed.connect(self._on_update_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_update_thread)
        self._update_thread = thread
        thread.start()

    def _on_update_prepared(self, prepared_update: object) -> None:
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        self._pending_prepared_update = prepared_update  # type: ignore[assignment]
        self.status_label.setText("Update ready. Restarting...")
        try:
            launch_prepared_update(self._pending_prepared_update)
        except UpdateInstallError as exc:
            self._pending_prepared_update = None
            QMessageBox.warning(self, "Automatic Update", str(exc))
            self.status_label.setText("Automatic update could not be started.")
            return
        QTimer.singleShot(150, self.close)

    def _on_update_failed(self, message: str) -> None:
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None
        self.status_label.setText("Automatic update could not be started.")
        QMessageBox.warning(self, "Automatic Update", message)

    def _clear_update_thread(self) -> None:
        self._update_thread = None
        self._update_worker = None
