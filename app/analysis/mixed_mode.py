from __future__ import annotations

import numpy as np


PAIRING_OPTIONS: dict[str, tuple[int, int, int, int]] = {
    "Ports (1,2) / (3,4)": (0, 1, 2, 3),
    "Ports (1,3) / (2,4)": (0, 2, 1, 3),
}


def _mixed_mode_transform() -> np.ndarray:
    """Return orthonormal transform for [d1, d2, c1, c2] ordering."""
    return (1 / np.sqrt(2)) * np.array(
        [
            [1, -1, 0, 0],
            [0, 0, 1, -1],
            [1, 1, 0, 0],
            [0, 0, 1, 1],
        ],
        dtype=complex,
    )


def reorder_ports(s_parameters: np.ndarray, port_order: tuple[int, int, int, int]) -> np.ndarray:
    if tuple(sorted(port_order)) != (0, 1, 2, 3):
        raise ValueError("Port order must be a permutation of (0, 1, 2, 3).")
    return s_parameters[:, port_order][:, :, port_order]


def single_ended_to_mixed_mode(
    s_parameters: np.ndarray,
    port_order: tuple[int, int, int, int] = (0, 1, 2, 3),
) -> np.ndarray:
    """
    Convert a 4-port single-ended S-parameter array to mixed-mode form.

    Parameters
    ----------
    s_parameters:
        Array shaped as (n_freq, 4, 4).
    """
    if s_parameters.ndim != 3 or s_parameters.shape[1:] != (4, 4):
        raise ValueError("Expected S-parameters with shape (n_freq, 4, 4).")

    reordered = reorder_ports(s_parameters, port_order)
    transform = _mixed_mode_transform()
    inverse = transform.T
    return np.einsum("ab,fbc,cd->fad", transform, reordered, inverse, optimize=True)


def compute_sdd11_sdd21(
    s_parameters: np.ndarray,
    port_order: tuple[int, int, int, int] = (0, 1, 2, 3),
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute SDD11 and SDD21 from 4-port single-ended S-parameters.

    The mixed-mode ordering is [d1, d2, c1, c2], where port pair (1, 2)
    becomes differential port 1 and pair (3, 4) becomes differential port 2.
    """
    mixed_mode = single_ended_to_mixed_mode(s_parameters, port_order=port_order)
    sdd11 = mixed_mode[:, 0, 0]
    sdd21 = mixed_mode[:, 1, 0]
    return sdd11, sdd21
