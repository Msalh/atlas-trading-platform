"""
Phase N4 Sprint 6. WalkForwardSpec/MonteCarloSpec - named in the blueprint,
package-local (mirroring atlas.research.features.models.CandidateFeatureSpec's
own precedent): neither is embedded in ValidationResult's own stored shape,
each is purely an input parameter to validate(), never referenced by any
other Research Engine entity. Sprint 1's models.py is not touched by this
sprint at all.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardSpec:
    """A declared, cross-checked DESCRIPTION of the fold structure the
    caller already built (via repeated, unmodified build_experiment()/
    compute_evidence() calls) - not something validate() constructs from
    a raw dataset. validate() cross-checks in_sample_fold_count/
    out_of_sample_fold_count against the actual number of Evidence
    records supplied, catching an accidental caller mistake (e.g.
    claiming 3 folds while supplying 2)."""

    in_sample_fold_count: int
    out_of_sample_fold_count: int
    fold_scheme_description: str

    def __post_init__(self) -> None:
        if self.in_sample_fold_count < 1:
            raise ValueError(f"in_sample_fold_count must be >= 1, got {self.in_sample_fold_count}")
        if self.out_of_sample_fold_count < 1:
            raise ValueError(f"out_of_sample_fold_count must be >= 1, got {self.out_of_sample_fold_count}")
        if not self.fold_scheme_description or not self.fold_scheme_description.strip():
            raise ValueError("fold_scheme_description must not be blank")


@dataclass(frozen=True)
class MonteCarloSpec:
    """n_draws seeded random draws from Normal(mean, std_dev) per fold -
    see this package's own __init__.py for why this is deliberately
    parametric, not a resample of raw observations. seed makes every run
    reproducible (Design Principle VII.2: every stochastic process is
    explicitly seeded, never sourced from system entropy)."""

    n_draws: int
    seed: int

    def __post_init__(self) -> None:
        if self.n_draws < 1:
            raise ValueError(f"n_draws must be >= 1, got {self.n_draws}")
