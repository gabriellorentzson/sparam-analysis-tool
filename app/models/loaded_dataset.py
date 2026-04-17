from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


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
    sdd11: np.ndarray
    sdd21: np.ndarray
    sdd21_db: np.ndarray
    tdr_time_ns: np.ndarray
    tdr_impedance_ohms: np.ndarray
    metrics: dict[str, float | int | str]
    color: str = field(default="")
