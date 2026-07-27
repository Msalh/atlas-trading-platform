"""Read-only, allowlisted Shadow results projection."""

from atlas.shadow_results.service import build_shadow_results
from atlas.shadow_results.telemetry import ProcessTelemetry

__all__ = ["ProcessTelemetry", "build_shadow_results"]
