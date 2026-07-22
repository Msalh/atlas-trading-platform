"""
Phase N4 Sprint 6 (Validation) - the platform's scientific gatekeeper.
Given already-computed Evidence (Sprint 5's own, separate job) for one or
more in-sample and out-of-sample folds, decides whether a hypothesis's
acceptance criterion is scientifically supported - never computes a new
number from raw data, never builds an Experiment, never touches the
Ledger.

validate() is the one public interface. It is structurally impossible to
call without at least one out-of-sample Evidence record (Design Principle
IV.3 - in_sample_evidence and out_of_sample_evidence are both required,
non-empty parameters, not optional ones), and whenever batch_size > 1,
multiple_testing_correction becomes a required, non-None parameter too
(Principle IV.4 - mandatory, structurally enforced by the API, never
merely documented).

--- Why this package never does true (nonparametric) resampling ---

Evidence.metrics is Mapping[str, Union[int, float, str, bool]] - it never
retains the raw per-bar Feature values feeding a fold, only aggregate
statistics (mean, std_dev, sample_size). True bootstrap/permutation
testing needs the raw observations. Giving Validation the raw Feature
series instead would require a dependency the roadmap does not list and
would blur "Validation must never compute Statistics" - recomputing means/
effect sizes from raw data is exactly Statistics's own job. This
package's Monte Carlo procedure is therefore deliberately PARAMETRIC:
seeded simulation from Evidence's own already-published mean/std_dev (the
same normal-approximation Statistics's own confidence interval already
assumes) - a genuine, reproducible simulation, disclosed explicitly as
parametric, not a resample of raw observations. This is a real,
disclosed scope boundary, not an oversight.

--- Fold construction happens before this package, not inside it ---

Walk-forward "fold construction" is not code in this package. The caller
(a human, or a future orchestration layer) builds each fold's own
Experiment + Evidence by calling atlas.research.experiment_builder.
build_experiment()/atlas.research.statistics.compute_evidence()
repeatedly, once per fold, entirely unmodified - then hands the resulting
Evidence records to validate() together. WalkForwardSpec is a declared,
cross-checked DESCRIPTION of that fold structure (fold counts), used to
catch an accidental caller mistake (e.g. claiming 3 folds while supplying
2) - never something Validation itself constructs from a raw dataset.

--- Statistical rule ---

For each fold's Evidence, a one-sided p-value for "mean > threshold" is
computed exactly via math.erf (no approximation, no external
dependency), then Bonferroni-corrected when batch_size > 1
(alpha_corrected = 0.05 / batch_size). verdict = SUPPORTED only when
EVERY in-sample AND EVERY out-of-sample fold clears the (possibly
corrected) alpha; NOT_SUPPORTED when NONE of the out-of-sample folds
clear; INCONCLUSIVE otherwise (a genuine, honest "we don't know yet" -
Principle IV.5, never forced into a binary).

Pure with respect to persistence, the same "orchestration decides
persistence, not the pure core" split every other Research Engine service
function already follows: validate() returns a ValidationResult value; it
never calls atlas.research.stores.ValidationResultTracker itself.
"""
