from __future__ import annotations

from pathlib import Path

from app.models.loaded_dataset import LoadedDataset


def load_touchstone_dataset(
    file_path: str,
) -> LoadedDataset:
    import skrf as rf

    network = rf.Network(file_path)
    if network.nports != 4:
        raise ValueError(f"{file_path} is not a 4-port Touchstone file.")

    return LoadedDataset(
        file_path=file_path,
        display_name=Path(file_path).name,
        enabled=True,
        frequency_hz=network.f,
        raw_s_parameters=network.s,
        mixed_mode_s_parameters=network.s.copy(),
        tdr_time_ns=network.f * 0.0,
        tdr_impedance_ohms=network.f * 0.0,
        metrics={},
    )
