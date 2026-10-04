"""Quantum-encoding resource estimates used by the QML feasibility matrix.

These are back-of-envelope circuit-resource estimates for planning simulator experiments. They say nothing
about quantum advantage, which requires matched, properly designed experiments.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Practical planning limits (assumptions, documented in documentation/qml_feasibility.md).
STATEVECTOR_QUBIT_LIMIT = 30      # laptop/workstation statevector simulation ceiling
COMFORTABLE_QUBITS = 16           # fast enough for repeated CV training on a CPU simulator
QSVM_KERNEL_EVAL_BUDGET = 2_000_000  # ~N^2/2 kernel circuit evaluations considered tractable on a simulator


@dataclass
class EncodingEstimate:
    reduced_features: int
    angle_qubits: int
    amplitude_qubits: int
    amplitude_state_prep_cnots: int
    basis_qubits: int
    zz_feature_map_entanglers: int
    qsvm_kernel_evals_full: int
    qsvm_max_train_samples: int
    simulator_tier: str


def amplitude_qubits(n_features: int) -> int:
    return max(1, math.ceil(math.log2(max(n_features, 1))))


def amplitude_state_prep_cnots(n_qubits: int) -> int:
    """Generic (Mottonen-style) state preparation needs on the order of 2^n CNOTs; use 2^n - n - 1 as the estimate."""
    return max(0, 2 ** n_qubits - n_qubits - 1)


def estimate(n_samples: int, n_features: int, *, target_qubits: int = 8, bits_per_feature: int = 1) -> EncodingEstimate:
    """Estimate resources after reducing ``n_features`` to at most ``target_qubits`` (PCA or selection)."""
    reduced = min(n_features, target_qubits)
    amp_q = amplitude_qubits(n_features)
    train_n = int(0.75 * n_samples)
    max_qsvm_n = int(math.sqrt(2 * QSVM_KERNEL_EVAL_BUDGET))
    if reduced <= COMFORTABLE_QUBITS:
        tier = "CPU statevector simulator"
    elif reduced <= STATEVECTOR_QUBIT_LIMIT:
        tier = "high-memory / GPU statevector simulator"
    else:
        tier = "requires further reduction (beyond statevector limits)"
    return EncodingEstimate(
        reduced_features=reduced,
        angle_qubits=reduced,
        amplitude_qubits=amp_q,
        amplitude_state_prep_cnots=amplitude_state_prep_cnots(amp_q),
        basis_qubits=reduced * bits_per_feature,
        zz_feature_map_entanglers=reduced * (reduced - 1) // 2,
        qsvm_kernel_evals_full=train_n * (train_n - 1) // 2,
        qsvm_max_train_samples=min(train_n, max_qsvm_n),
        simulator_tier=tier,
    )
