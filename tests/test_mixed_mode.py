import numpy as np

from app.analysis.mixed_mode import compute_sdd11_sdd21


def test_compute_sdd11_sdd21_for_simple_forward_path() -> None:
    s_parameters = np.zeros((1, 4, 4), dtype=complex)
    s_parameters[0, 2, 0] = 1.0
    s_parameters[0, 3, 1] = 1.0

    sdd11, sdd21 = compute_sdd11_sdd21(s_parameters)

    assert np.allclose(sdd11, [0.0 + 0.0j])
    assert np.allclose(sdd21, [1.0 + 0.0j])


def test_compute_sdd21_for_alternate_pairing() -> None:
    s_parameters = np.zeros((1, 4, 4), dtype=complex)
    s_parameters[0, 1, 0] = 1.0
    s_parameters[0, 3, 2] = 1.0

    sdd11, sdd21 = compute_sdd11_sdd21(s_parameters, port_order=(0, 2, 1, 3))

    assert np.allclose(sdd11, [0.0 + 0.0j])
    assert np.allclose(sdd21, [1.0 + 0.0j])
