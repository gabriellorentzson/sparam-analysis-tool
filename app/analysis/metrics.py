from __future__ import annotations

import numpy as np


TARGET_FREQUENCIES_HZ = {
    "sdd21_db_13p28_ghz": 13.28e9,
    "sdd21_db_26p5625_ghz": 26.5625e9,
}


def magnitude_db(values: np.ndarray, floor_db: float = -120.0) -> np.ndarray:
    magnitude = np.abs(values)
    with np.errstate(divide="ignore"):
        values_db = 20.0 * np.log10(magnitude)
    return np.maximum(values_db, floor_db)


def interpolate_complex(x: np.ndarray, y: np.ndarray, target_x: float) -> complex:
    real_value = np.interp(target_x, x, np.real(y))
    imag_value = np.interp(target_x, x, np.imag(y))
    return real_value + 1j * imag_value


def summarize_frequency_range(frequency_hz: np.ndarray) -> dict[str, float | int]:
    return {
        "freq_start_ghz": float(frequency_hz[0] / 1e9),
        "freq_stop_ghz": float(frequency_hz[-1] / 1e9),
        "point_count": int(frequency_hz.size),
    }


def summarize_sdd21_metrics(
    frequency_hz: np.ndarray,
    sdd21: np.ndarray,
) -> dict[str, float]:
    sdd21_db = magnitude_db(sdd21)
    summary: dict[str, float] = {}
    for key, target_hz in TARGET_FREQUENCIES_HZ.items():
        if target_hz < frequency_hz[0] or target_hz > frequency_hz[-1]:
            summary[key] = float("nan")
            continue
        value = interpolate_complex(frequency_hz, sdd21, target_hz)
        summary[key] = float(magnitude_db(np.asarray([value]))[0])
    summary["sdd21_min_db"] = float(np.min(sdd21_db))
    return summary


def build_summary_metrics(
    file_name: str,
    frequency_hz: np.ndarray,
    sdd21: np.ndarray,
) -> dict[str, float | int | str]:
    metrics: dict[str, float | int | str] = {"filename": file_name}
    metrics.update(summarize_frequency_range(frequency_hz))
    metrics.update(summarize_sdd21_metrics(frequency_hz, sdd21))
    return metrics
