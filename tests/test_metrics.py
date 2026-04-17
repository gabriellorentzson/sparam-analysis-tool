import numpy as np

from app.analysis.metrics import build_summary_metrics, magnitude_db
from app.analysis.tdr import compute_differential_tdr


def test_magnitude_db_for_half_voltage() -> None:
    values = np.asarray([0.5 + 0j])
    assert np.allclose(magnitude_db(values), [-6.02059991])


def test_build_summary_metrics_interpolates_target_frequency() -> None:
    frequency_hz = np.asarray([10e9, 20e9, 30e9])
    sdd21 = np.asarray([1.0, 0.5, 0.25], dtype=complex)

    metrics = build_summary_metrics("demo.s4p", frequency_hz, sdd21)

    assert metrics["filename"] == "demo.s4p"
    assert metrics["point_count"] == 3
    assert np.isfinite(metrics["sdd21_db_13p28_ghz"])
    assert np.isfinite(metrics["sdd21_db_26p5625_ghz"])


def test_compute_differential_tdr_returns_matching_shapes() -> None:
    frequency_hz = np.linspace(1e9, 20e9, 200)
    sdd11 = np.zeros_like(frequency_hz, dtype=complex)

    result = compute_differential_tdr(frequency_hz, sdd11)

    assert result.time_ns.shape == result.impedance_ohms.shape
    assert result.time_ns.ndim == 1
    assert np.isclose(result.impedance_ohms[0], 100.0)
