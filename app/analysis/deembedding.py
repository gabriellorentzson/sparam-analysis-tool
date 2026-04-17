from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class DeembedRequest:
    mode: str
    dut_name: str
    left_name: str = ""
    right_name: str = ""


def _to_network(dataset):
    import skrf as rf

    frequency = rf.Frequency.from_f(dataset.frequency_hz, unit="Hz")
    return rf.Network(
        frequency=frequency,
        s=dataset.raw_s_parameters,
        z0=dataset.raw_z0,
        name=dataset.display_name,
    )


def _align_network(reference_network, network):
    if np.array_equal(reference_network.f, network.f):
        return network
    return network.interpolate(reference_network.frequency)


def _crop_network_to_frequency_range(network, start_hz: float, stop_hz: float):
    import skrf as rf

    mask = (network.f >= start_hz) & (network.f <= stop_hz)
    if not np.any(mask):
        raise ValueError("No overlapping frequency span exists between the selected networks.")

    frequency = rf.Frequency.from_f(network.f[mask], unit="Hz")
    return rf.Network(
        frequency=frequency,
        s=network.s[mask, :, :],
        z0=network.z0[mask, :],
        name=network.name,
    )


def _common_frequency_window(networks) -> tuple[float, float]:
    start_hz = max(float(network.f[0]) for network in networks)
    stop_hz = min(float(network.f[-1]) for network in networks)
    if start_hz >= stop_hz:
        raise ValueError("Selected networks do not share an overlapping frequency range.")
    return start_hz, stop_hz


def deembed_datasets(dut_dataset, left_dataset=None, right_dataset=None, mode: str = "left"):
    dut = _to_network(dut_dataset)
    left = _to_network(left_dataset) if left_dataset is not None else None
    right = _to_network(right_dataset) if right_dataset is not None else None

    networks = [dut]
    if left is not None:
        networks.append(left)
    if right is not None:
        networks.append(right)

    start_hz, stop_hz = _common_frequency_window(networks)
    dut = _crop_network_to_frequency_range(dut, start_hz, stop_hz)
    left = _align_network(dut, _crop_network_to_frequency_range(left, start_hz, stop_hz)) if left is not None else None
    right = _align_network(dut, _crop_network_to_frequency_range(right, start_hz, stop_hz)) if right is not None else None

    if mode == "left":
        if left is None:
            raise ValueError("Left fixture is required for left de-embedding.")
        result = left.inv ** dut
    elif mode == "right":
        if right is None:
            raise ValueError("Right fixture is required for right de-embedding.")
        result = dut ** right.inv
    elif mode == "both_same":
        if left is None:
            raise ValueError("Fixture is required for both-side de-embedding.")
        result = left.inv ** dut ** left.inv
    elif mode == "both_separate":
        if left is None or right is None:
            raise ValueError("Both left and right fixtures are required for separate de-embedding.")
        result = left.inv ** dut ** right.inv
    else:
        raise ValueError(f"Unsupported de-embedding mode '{mode}'.")

    result.name = dut_dataset.display_name
    return result
