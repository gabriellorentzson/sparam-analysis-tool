from __future__ import annotations

from pathlib import Path

import skrf as rf

from app.analysis.metrics import build_summary_metrics, magnitude_db
from app.analysis.mixed_mode import compute_sdd11_sdd21
from app.analysis.tdr import compute_differential_tdr
from app.models.loaded_dataset import LoadedDataset


def load_touchstone_dataset(
    file_path: str,
    reference_impedance_ohms: float = 100.0,
    tdr_window: str = "rectangular",
    tdr_oversample: int = 4,
) -> LoadedDataset:
    network = rf.Network(file_path)
    if network.nports != 4:
        raise ValueError(f"{file_path} is not a 4-port Touchstone file.")

    frequency_hz = network.f
    sdd11, sdd21 = compute_sdd11_sdd21(network.s)
    sdd21_db = magnitude_db(sdd21)
    tdr_result = compute_differential_tdr(
        frequency_hz=frequency_hz,
        sdd11=sdd11,
        reference_impedance_ohms=reference_impedance_ohms,
        window=tdr_window,
        oversample=tdr_oversample,
    )
    metrics = build_summary_metrics(Path(file_path).name, frequency_hz, sdd21)

    return LoadedDataset(
        file_path=file_path,
        display_name=Path(file_path).name,
        enabled=True,
        frequency_hz=frequency_hz,
        sdd11=sdd11,
        sdd21=sdd21,
        sdd21_db=sdd21_db,
        tdr_time_ns=tdr_result.time_ns,
        tdr_impedance_ohms=tdr_result.impedance_ohms,
        metrics=metrics,
    )
