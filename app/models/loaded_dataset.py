from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class FrequencyMarkerRow:
    trace_name: str
    frequency_ghz: float
    magnitude_db: float


@dataclass(slots=True)
class MarkerReadout:
    axis_name: str
    x_label: str
    y_label: str
    x_value: float
    y_value: float


@dataclass(slots=True)
class LoadedDataset:
    file_path: str
    display_name: str
    enabled: bool
    frequency_hz: np.ndarray
    raw_s_parameters: np.ndarray
    raw_z0: np.ndarray
    mixed_mode_s_parameters: np.ndarray
    tdr_time_ns: np.ndarray
    tdr_impedance_ohms: np.ndarray
    metrics: dict[str, float | int | str]
    color: str = field(default="")
    source_note: str = field(default="")
