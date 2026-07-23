"""
Phase N4 Sprint 7. RankingPolicy - a package-local spec type (mirroring
atlas.research.features.models.CandidateFeatureSpec/
atlas.research.validation.models.WalkForwardSpec's own precedent): never
embedded in LeaderboardSnapshot itself, purely an input parameter to
rank()/snapshot_leaderboard(), identified in the resulting snapshot by
policy_id/policy_version alone.

RANKING_POLICY_V1 is deliberately named "recency_organizational", not
anything implying merit or quality - see this package's own __init__.py
for why no scientific scoring policy exists yet.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RankingPolicy:
    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        if not self.policy_id or not self.policy_id.strip():
            raise ValueError("policy_id must not be blank")
        if not self.policy_version or not self.policy_version.strip():
            raise ValueError("policy_version must not be blank")


RANKING_POLICY_V1 = RankingPolicy(policy_id="recency_organizational", policy_version="1.0")
