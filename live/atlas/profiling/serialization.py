"""
Sprint 24C. Pure domain serialization for atlas.profiling.models.ProfilingReport -
the same domain/transport split atlas.rule_engine.service.rule_engine_output_to_dict
and atlas.setup_engine.service.setup_engine_output_to_dict already establish:
this module knows nothing about HTTP/FastAPI, and produces a plain,
JSON-safe dict, not a transport envelope.

Determinism (Sprint 24C scope M): every field here is either directly
deterministic (counts, rates, distributions - the same input always
produces the same output) or is run_metadata.generated_at, which is
deliberately the one field this module does NOT attempt to make
deterministic - it is execution metadata (when this run happened), never
folded into any count or rate, and a caller wanting a byte-identical
content fingerprint across separate runs should exclude
run_metadata.generated_at from that comparison (or, in tests, hold it fixed
by injecting the same generated_at into profile_market_state_series).

Ordering: fact_metrics and setup_metrics are serialized as dicts in the
exact order atlas.profiling.service already builds them in - Rule Engine
and Setup Engine registry order, respectively (not sorted, not insertion-
order-by-accident: the dict comprehensions that build
ProfilingReport.fact_metrics/setup_metrics in service.py iterate
RULE_ENGINE_REGISTRY/SETUP_ENGINE_REGISTRY directly). Python dicts preserve
insertion order; json.dumps preserves that order in its output.

Undefined rates (firing_rate, detection_rate, held_rate when their
denominator is zero) serialize as JSON null, never 0 and never omitted -
the same "null means undefined, not zero" convention used throughout this
package. No NaN/Infinity is ever emitted - _json_safe_float defensively
converts either to null rather than producing invalid JSON.
"""
import math
from typing import Any, Optional

from atlas.profiling.models import (
    DataQualitySummary,
    FactProfile,
    HierarchyRelationshipProfile,
    ProfilingReport,
    RunMetadata,
    ScalarDistribution,
    SegmentSummary,
    SessionBreakdown,
    SessionBucketCounts,
    SetupProfile,
)


def _json_safe_float(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _scalar_distribution_to_dict(distribution: ScalarDistribution) -> dict[str, Any]:
    return {
        "count": distribution.count,
        "min": _json_safe_float(distribution.min),
        "max": _json_safe_float(distribution.max),
        "mean": _json_safe_float(distribution.mean),
        "p50": _json_safe_float(distribution.p50),
        "p95": _json_safe_float(distribution.p95),
    }


def _session_bucket_to_dict(bucket: SessionBucketCounts) -> dict[str, Any]:
    return {"computable_count": bucket.computable_count, "positive_count": bucket.positive_count}


def _session_breakdown_to_dict(breakdown: SessionBreakdown) -> dict[str, Any]:
    return {
        "by_session_name": {
            key: _session_bucket_to_dict(bucket) for key, bucket in breakdown.by_session_name.items()
        },
        "by_is_rth": {
            key: _session_bucket_to_dict(bucket) for key, bucket in breakdown.by_is_rth.items()
        },
    }


def _fact_profile_to_dict(profile: FactProfile) -> dict[str, Any]:
    return {
        "fact_name": profile.fact_name,
        "value_kind": profile.value_kind,
        "computable_count": profile.computable_count,
        "insufficient_data_count": profile.insufficient_data_count,
        "value_counts": dict(profile.value_counts),
        "firing_rate": _json_safe_float(profile.firing_rate),
        "evidence_distributions": {
            field_name: _scalar_distribution_to_dict(distribution)
            for field_name, distribution in profile.evidence_distributions.items()
        },
        "session_breakdown": _session_breakdown_to_dict(profile.session_breakdown),
    }


def _setup_profile_to_dict(profile: SetupProfile) -> dict[str, Any]:
    return {
        "setup_name": profile.setup_name,
        "computable_count": profile.computable_count,
        "insufficient_data_count": profile.insufficient_data_count,
        "detected_count": profile.detected_count,
        "not_detected_count": profile.not_detected_count,
        "detection_rate": _json_safe_float(profile.detection_rate),
        "session_breakdown": _session_breakdown_to_dict(profile.session_breakdown),
    }


def _hierarchy_relationship_to_dict(profile: HierarchyRelationshipProfile) -> dict[str, Any]:
    return {
        "child_fact": profile.child_fact,
        "parent_fact": profile.parent_fact,
        "expected_relationship": profile.expected_relationship,
        "child_true_count": profile.child_true_count,
        "child_and_parent_true_count": profile.child_and_parent_true_count,
        "held_rate": _json_safe_float(profile.held_rate),
        "discrepancy_count": profile.discrepancy_count,
        "window_metadata": None if profile.window_metadata is None else {
            "child_window": profile.window_metadata.child_window,
            "parent_window": profile.window_metadata.parent_window,
            "windows_matched": profile.window_metadata.windows_matched,
        },
    }


def _segment_summary_to_dict(segment: SegmentSummary) -> dict[str, Any]:
    return {
        "first_timestamp": segment.first_timestamp,
        "last_timestamp": segment.last_timestamp,
        "bar_count": segment.bar_count,
        "fact_warm_up_observations": segment.fact_warm_up_observations,
        "setup_warm_up_observations": segment.setup_warm_up_observations,
    }


def _data_quality_to_dict(data_quality: DataQualitySummary) -> dict[str, Any]:
    return {
        "raw_row_count": data_quality.raw_row_count,
        "excluded_forming_bar_count": data_quality.excluded_forming_bar_count,
        "excluded_synthetic_symbol_count": data_quality.excluded_synthetic_symbol_count,
        "segments": [_segment_summary_to_dict(segment) for segment in data_quality.segments],
        "segment_boundary_count": data_quality.segment_boundary_count,
        "possible_truncation": data_quality.possible_truncation,
        "roll_boundaries_configured": list(data_quality.roll_boundaries_configured),
        "observations_near_roll_boundary": data_quality.observations_near_roll_boundary,
    }


def _run_metadata_to_dict(run_metadata: RunMetadata) -> dict[str, Any]:
    return {
        "schema_version": run_metadata.schema_version,
        "symbol": run_metadata.symbol,
        "timeframe": run_metadata.timeframe,
        "requested_start": run_metadata.requested_start,
        "requested_end": run_metadata.requested_end,
        "source_row_count": run_metadata.source_row_count,
        "generated_at": run_metadata.generated_at,
        "rule_engine_fact_names": list(run_metadata.rule_engine_fact_names),
        "rule_engine_required_history": run_metadata.rule_engine_required_history,
        "setup_engine_setup_names": list(run_metadata.setup_engine_setup_names),
        "setup_engine_required_history": run_metadata.setup_engine_required_history,
        "excluded_symbols": list(run_metadata.excluded_symbols),
        "hierarchy_fact_definitions": {
            fact_name: dict(params) for fact_name, params in run_metadata.hierarchy_fact_definitions.items()
        },
    }


def profiling_report_to_dict(report: ProfilingReport) -> dict[str, Any]:
    """The single conversion entry point - mirrors
    rule_engine_output_to_dict/setup_engine_output_to_dict's own posture
    exactly. Top-level key order is the schema order Sprint 24B's design
    specified: run_metadata, data_quality, fact_metrics, setup_metrics,
    setup_co_detection_matrix, hierarchy_summary."""
    return {
        "run_metadata": _run_metadata_to_dict(report.run_metadata),
        "data_quality": _data_quality_to_dict(report.data_quality),
        "fact_metrics": {
            fact_name: _fact_profile_to_dict(profile) for fact_name, profile in report.fact_metrics.items()
        },
        "setup_metrics": {
            setup_name: _setup_profile_to_dict(profile) for setup_name, profile in report.setup_metrics.items()
        },
        "setup_co_detection_matrix": {
            a: dict(row) for a, row in report.setup_co_detection_matrix.items()
        },
        "hierarchy_summary": [
            _hierarchy_relationship_to_dict(profile) for profile in report.hierarchy_summary
        ],
    }
