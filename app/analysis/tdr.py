from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import interpolate, signal


@dataclass(slots=True)
class TdrResult:
    time_ns: np.ndarray
    impedance_ohms: np.ndarray


WINDOW_BUILDERS = {
    "rectangular": None,
    "hann": signal.windows.hann,
    "kaiser": lambda size: signal.windows.kaiser(size, beta=6.0),
}


def _ensure_uniform_frequency(
    frequency_hz: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    diffs = np.diff(frequency_hz)
    if np.allclose(diffs, diffs[0], rtol=1e-6, atol=1e-3):
        return frequency_hz, values

    target_frequency = np.linspace(frequency_hz[0], frequency_hz[-1], frequency_hz.size)
    interpolator = interpolate.interp1d(
        frequency_hz,
        values,
        kind="linear",
        fill_value="extrapolate",
        assume_sorted=True,
    )
    return target_frequency, interpolator(target_frequency)


def _apply_window(values: np.ndarray, window: str) -> np.ndarray:
    if window not in WINDOW_BUILDERS:
        raise ValueError(f"Unsupported window '{window}'.")

    builder = WINDOW_BUILDERS[window]
    if builder is None:
        return values
    return values * builder(values.size)


def compute_differential_tdr(
    frequency_hz: np.ndarray,
    sdd11: np.ndarray,
    reference_impedance_ohms: float = 100.0,
    window: str = "rectangular",
    oversample: int = 4,
) -> TdrResult:
    if frequency_hz.ndim != 1 or sdd11.ndim != 1:
        raise ValueError("Expected 1-D frequency and SDD11 arrays.")
    if frequency_hz.size != sdd11.size:
        raise ValueError("Frequency and SDD11 arrays must have the same length.")
    if oversample < 1:
        raise ValueError("Oversample factor must be >= 1.")

    frequency_hz, sdd11 = _ensure_uniform_frequency(frequency_hz, sdd11)

    if frequency_hz[0] > 0.0:
        frequency_hz = np.insert(frequency_hz, 0, 0.0)
        sdd11 = np.insert(sdd11, 0, sdd11[0])

    sdd11 = _apply_window(sdd11, window)
    df = frequency_hz[1] - frequency_hz[0]
    n_positive = sdd11.size
    n_time = max(2 * (n_positive - 1) * oversample, 2)

    gamma_impulse = np.fft.irfft(sdd11, n=n_time)
    gamma_step = np.cumsum(gamma_impulse)
    gamma_step = np.clip(gamma_step, -0.999, 0.999)

    time_s = np.arange(n_time, dtype=float) / (n_time * df)
    impedance = reference_impedance_ohms * (1.0 + gamma_step) / (1.0 - gamma_step)
    return TdrResult(time_ns=time_s * 1e9, impedance_ohms=np.real(impedance))
