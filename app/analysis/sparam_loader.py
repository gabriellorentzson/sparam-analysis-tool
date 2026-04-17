from __future__ import annotations

from pathlib import Path

from app.models.loaded_dataset import LoadedDataset


def dataset_from_network(network, file_path: str, display_name: str | None = None, source_note: str = "") -> LoadedDataset:
    if network.nports != 4:
        raise ValueError(f"{display_name or file_path} is not a 4-port network.")

    label = display_name or Path(file_path).name
    frequency_hz = network.f
    return LoadedDataset(
        file_path=file_path,
        display_name=label,
        enabled=True,
        frequency_hz=frequency_hz,
        raw_s_parameters=network.s,
        raw_z0=network.z0,
        mixed_mode_s_parameters=network.s.copy(),
        tdr_time_ns=frequency_hz * 0.0,
        tdr_impedance_ohms=frequency_hz * 0.0,
        metrics={},
        source_note=source_note,
    )


def load_touchstone_dataset(file_path: str) -> LoadedDataset:
    import skrf as rf

    network = rf.Network(file_path)
    return dataset_from_network(network, file_path=file_path)
