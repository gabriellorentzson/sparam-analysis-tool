from __future__ import annotations

import numpy as np


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


def single_ended_to_mixed_mode(s_parameters: np.ndarray) -> np.ndarray:
    """
    Convert a 4-port single-ended S-parameter array to mixed-mode form.

    Parameters
    ----------
    s_parameters:
        Array shaped as (n_freq, 4, 4).
    """
    if s_parameters.ndim != 3 or s_parameters.shape[1:] != (4, 4):
        raise ValueError("Expected S-parameters with shape (n_freq, 4, 4).")

    transform = _mixed_mode_transform()
    inverse = transform.T
    return np.einsum("ab,fbc,cd->fad", transform, s_parameters, inverse, optimize=True)


def compute_sdd11_sdd21(s_parameters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute SDD11 and SDD21 from 4-port single-ended S-parameters.

    The mixed-mode ordering is [d1, d2, c1, c2], where port pair (1, 2)
    becomes differential port 1 and pair (3, 4) becomes differential port 2.
    """
    mixed_mode = single_ended_to_mixed_mode(s_parameters)
    sdd11 = mixed_mode[:, 0, 0]
    sdd21 = mixed_mode[:, 1, 0]
    return sdd11, sdd21
