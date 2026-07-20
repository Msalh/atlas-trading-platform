"""
Sprint RE-2. Markdown rendering for the six computed RE-2 deliverables -
deliberately thin, mechanical templates over an already-computed report
dataclass (models.py), the same "rendering step over deterministic content"
discipline RE-1's own reports.py establishes. No number is computed here -
every value is read directly from the dataclass passed in. RE2_Research_Notes
.md (the 7th deliverable) is hand-written prose reading these six reports,
the same posture RE1_Research_Notes.md already took - not auto-rendered from
a dataclass here.
"""
from atlas.research.setup_profiling.models import (
    RunManifest,
    SetupClustering,
    SetupContextProfile,
    SetupOverlap,
    SetupProfile,
    SetupTimeDistribution,
    SetupTransitions,
)


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _num(value, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _render_manifest(manifest: RunManifest, title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        f"- **Symbol**: {manifest.symbol}  **Timeframe**: {manifest.timeframe}",
        f"- **Requested range**: {manifest.requested_start} -> {manifest.requested_end}",
        f"- **Source**: {manifest.source_description}",
        f"- **Row count**: {manifest.row_count}",
        f"- **Generated at**: {manifest.generated_at}",
        f"- **Code version**: {manifest.code_version or 'unknown'}",
        "",
        "Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, "
        "MFE/MAE, or win-rate content. trend_1m is never used - it is not a registered Rule Engine fact.",
        "",
    ]


def render_setup_profile_report(profile: SetupProfile) -> str:
    lines = _render_manifest(profile.manifest, "RE-2 Setup Profile")
    for entry in profile.entries:
        lines.append(f"## {entry.setup_name}")
        lines.append("")
        lines.append(f"- Computable bars: {entry.computable_bars}  Active bars: {entry.active_bars} "
                      f"({_pct(entry.active_bar_rate)})")
        lines.append(f"- Episode count: {entry.episode_count}  "
                      f"(left-censored: {entry.left_censored_count}, right-censored: {entry.right_censored_count}, "
                      f"fully observed: {entry.fully_observed_count})")
        lines.append(f"- Single-bar episodes: {entry.single_bar_episode_count}  "
                      f"Multi-bar episodes: {entry.multi_bar_episode_count}")
        lines.append(f"- Activation bars: {entry.activation_bar_count}  Continuation bars: {entry.continuation_bar_count}")
        lines.append(f"- Eligible trading days: {entry.eligible_trading_days}  "
                      f"Episodes/trading day: {_num(entry.episodes_per_trading_day)}")
        lines.append(f"- Days with >=1 activation: {entry.days_with_activation_count} "
                      f"({_pct(entry.days_with_activation_rate)})")
        lines.append("")
        d = entry.all_episodes_duration
        lines.append(f"**All observed episodes** (n={d.count}) duration (bars): "
                      f"mean={_num(d.mean)} median={_num(d.median)} p75={_num(d.p75)} p90={_num(d.p90)} "
                      f"p95={_num(d.p95)} max={_num(d.max)}")
        f = entry.fully_observed_duration
        lines.append(f"**Fully observed (non-censored) episodes only** (n={f.count}) duration (bars): "
                      f"mean={_num(f.mean)} median={_num(f.median)} p75={_num(f.p75)} p90={_num(f.p90)} "
                      f"p95={_num(f.p95)} max={_num(f.max)}")
        lines.append("")

    lines.append("## Computability evidence")
    lines.append("")
    lines.append("| setup | total bars | computable | non-computable | detected true | detected false |")
    lines.append("|---|---|---|---|---|---|")
    for c in profile.computability:
        lines.append(f"| {c.setup_name} | {c.total_bars} | {c.computable_bars} | {c.non_computable_bars} | "
                      f"{c.detected_true_bars} | {c.detected_false_bars} |")
    lines.append("")
    for c in profile.computability:
        if c.insufficient_reason_counts:
            lines.append(f"**{c.setup_name} insufficient-data reasons**:")
            for reason, count in sorted(c.insufficient_reason_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  - {count}x: {reason}")
            lines.append("")

    return "\n".join(lines)


def _render_time_bucket_table(buckets) -> list[str]:
    lines = ["| bucket | activations | active bars | eligible bars | eligible days | "
             "activation rate/bar | activation rate/day | active-bar rate/bar |",
             "|---|---|---|---|---|---|---|---|"]
    for b in buckets:
        lines.append(f"| {b.bucket_key} | {b.activation_count} | {b.active_bar_count} | {b.eligible_bar_count} | "
                      f"{b.eligible_trading_days} | {_pct(b.activation_rate_per_eligible_bar)} | "
                      f"{_num(b.activation_rate_per_trading_day)} | {_pct(b.active_bar_rate_per_eligible_bar)} |")
    return lines


def render_time_distribution_report(distribution: SetupTimeDistribution) -> str:
    lines = _render_manifest(distribution.manifest, "RE-2 Time Distribution")
    lines.append("Activation distribution buckets by each episode's FIRST bar. Active-bar exposure is folded "
                  "into the same table (`active bars` column) - every bar where the setup is detected=True, "
                  "including continuation bars, not just activations. Activation count and unique episode "
                  "count are definitionally identical (one activation bar per episode) and are not reported "
                  "as two separate numbers.")
    lines.append("")
    for entry in distribution.entries:
        lines.append(f"## {entry.setup_name}")
        lines.append("")
        lines.append("### By session")
        lines += _render_time_bucket_table(entry.by_session)
        lines.append("")
        lines.append("### By hour (America/Chicago)")
        lines += _render_time_bucket_table(entry.by_hour_ct)
        lines.append("")
        lines.append("### By weekday (America/Chicago)")
        lines += _render_time_bucket_table(entry.by_weekday_ct)
        lines.append("")
        lines.append("### By month (America/Chicago)")
        lines += _render_time_bucket_table(entry.by_month)
        lines.append("")
    return "\n".join(lines)


def render_clustering_report(clustering: SetupClustering) -> str:
    lines = _render_manifest(clustering.manifest, "RE-2 Clustering")
    lines.append("Inter-episode time is computed only within the same market-data segment (never bridging a "
                  "maintenance/weekend/holiday gap). An episode with no within-segment successor is counted "
                  "as `censored_by_gap`, not given a fabricated inactivity duration. No certified maintenance/"
                  "weekend/holiday classifier exists as reusable code in this project (only as prose in a "
                  "certification report), so segment-boundary gaps are reported as raw duration with the "
                  "generic label `segment_boundary`, not re-classified here.")
    lines.append("")
    for entry in clustering.entries:
        lines.append(f"## {entry.setup_name}")
        lines.append("")
        lines.append(f"- Within-segment inter-episode gaps: {entry.within_segment_gap_count}  "
                      f"Censored by gap (no within-segment successor): {entry.censored_by_gap_count}")
        g = entry.gap_minutes_stats
        lines.append(f"- Gap minutes (n={g.count}): mean={_num(g.mean)} median={_num(g.median)} "
                      f"p75={_num(g.p75)} p90={_num(g.p90)} p95={_num(g.p95)} max={_num(g.max)}")
        lines.append(f"- Episodes/trading day: {_num(entry.episodes_per_trading_day)}")
        lines.append("")
        lines.append("**Repeat activation within N minutes** (count of within-segment gaps <= N):")
        for threshold, count in sorted(entry.repeat_within_minutes.items()):
            lines.append(f"  - <= {threshold}min: {count}")
        lines.append("")
        lines.append("**Burst/cluster sizes, reported at every threshold (no single canonical choice)**:")
        for burst in entry.bursts:
            sizes = ", ".join(str(s) for s in burst.burst_sizes[:20])
            more = "..." if len(burst.burst_sizes) > 20 else ""
            lines.append(f"  - threshold <= {burst.threshold_minutes}min: {burst.burst_count} bursts, "
                          f"longest={burst.longest_burst_size} episodes; sizes: [{sizes}{more}]")
        lines.append("")
    return "\n".join(lines)


def render_setup_overlap_report(overlap: SetupOverlap) -> str:
    lines = _render_manifest(overlap.manifest, "RE-2 Setup Overlap")
    lines.append("Five separately defined metrics per pair - never a single undefined \"overlap\" number. "
                  "`relationship` distinguishes LOGICALLY_IMPLIED (proven from the setup definitions), "
                  "SHARED_INPUTS_ONLY (inputs overlap, no implication proven), EMPIRICAL (no shared inputs, "
                  "any relationship found is a genuine finding), and UNKNOWN.")
    lines.append("")
    for e in overlap.entries:
        lines.append(f"## {e.setup_a} x {e.setup_b}")
        lines.append("")
        lines.append(f"**Relationship**: `{e.relationship.category.value}` - {e.relationship.rationale}")
        lines.append("")

        o = e.active_bar_overlap
        lines.append(f"**1. Concurrent active-bar overlap** (n jointly computable={o.jointly_computable_bars}): "
                      f"P(A)={_pct(o.p_a_active)} P(B)={_pct(o.p_b_active)} P(A and B)={_pct(o.p_both_active)} "
                      f"lift={_num(o.lift)} correlation={_num(o.correlation, 3)} "
                      f"P(A|B)={_pct(o.conditional_p_a_given_b)} Jaccard={_num(o.jaccard_active_bars, 3)}")

        a = e.activation_overlap
        lines.append(f"**2. Same-bar activation overlap**: {a.same_bar_activation_count} shared / "
                      f"{a.a_activation_count} A-activations ({_pct(a.p_same_bar_given_a)}), "
                      f"{a.b_activation_count} B-activations ({_pct(a.p_same_bar_given_b)})")

        i = e.episode_intersection
        lines.append(f"**3. Temporal episode intersection**: {i.intersecting_pair_count} overlapping episode "
                      f"pairs; {_pct(i.rate_of_a_episodes_intersecting)} of A's {i.a_episode_count} episodes, "
                      f"{_pct(i.rate_of_b_episodes_intersecting)} of B's {i.b_episode_count} episodes")

        c = e.episode_containment
        lines.append(f"**4. Full episode containment**: A fully inside B: {c.a_contained_in_b_count}  "
                      f"B fully inside A: {c.b_contained_in_a_count}")

        prox = "; ".join(
            f"<= {p.threshold_minutes}min: A-with-nearby-B={p.a_activations_with_nearby_b}, "
            f"B-with-nearby-A={p.b_activations_with_nearby_a}"
            for p in e.activation_proximity
        )
        lines.append(f"**5. Activation proximity**: {prox}")
        lines.append("")
    return "\n".join(lines)


def render_context_profile_report(context: SetupContextProfile) -> str:
    lines = _render_manifest(context.manifest, "RE-2 Context Profile")
    lines.append("At each offset, bar-level availability (was the offset bar inside the same segment) and "
                  "fact-level computability (was this specific registered fact computable at that bar) are "
                  "tracked independently - one fact's InsufficientData never marks the whole context snapshot "
                  "unavailable. Descriptive state transitions only - not outcome or return analysis.")
    lines.append("")
    for entry in context.entries:
        lines.append(f"## {entry.setup_name}")
        lines.append("")
        for offset in entry.offsets:
            lines.append(f"### Offset: {offset.offset_label} (n episodes={offset.episode_count})")
            lines.append("")
            lines.append("| fact | bar available | bar unavailable | computable | insufficient | "
                          "true rate / value counts |")
            lines.append("|---|---|---|---|---|---|")
            for f in offset.facts:
                if f.enum_value_counts:
                    values = ", ".join(f"{v}={c}" for v, c in sorted(f.enum_value_counts.items()))
                else:
                    values = _pct(f.boolean_true_rate)
                lines.append(f"| {f.fact_name} | {f.bar_available_count} | {f.bar_unavailable_count} | "
                              f"{f.computable_count} | {f.insufficient_count} | {values} |")
            lines.append("")
            session_str = ", ".join(f"{k}={v}" for k, v in sorted(offset.session_counts.items()))
            lines.append(f"Session at this offset: {session_str or 'n/a'}")
            lines.append("")
    return "\n".join(lines)


def render_setup_transitions_report(transitions: SetupTransitions) -> str:
    lines = _render_manifest(transitions.manifest, "RE-2 Setup Transitions")
    lines.append("Every transition points to the NEXT ActivationEvent (possibly multi-label, when two or "
                  "more setups activate on the identical bar) - no ordering is invented among setups tied on "
                  "the same bar. An episode with no qualifying next event before its segment ends is censored "
                  "(never resolved across a data gap).")
    lines.append("")
    censored = sum(1 for t in transitions.transitions if t.censored)
    lines.append(f"Total episode-level transitions: {len(transitions.transitions)}  Censored: {censored} "
                  f"({_pct(censored / len(transitions.transitions) if transitions.transitions else None)})")
    lines.append("")

    lines.append("## Transition matrix (from setup -> to setup, expanding multi-label events)")
    lines.append("")
    lines.append("| from | to | count | probability |")
    lines.append("|---|---|---|---|")
    for m in sorted(transitions.matrix, key=lambda m: (m.from_setup, -m.count)):
        lines.append(f"| {m.from_setup} | {m.to_setup} | {m.count} | {_pct(m.probability)} |")
    lines.append("")

    lines.append("## Recurrence rates")
    lines.append("")
    lines.append("| setup | same-setup recurrence | cross-setup recurrence |")
    lines.append("|---|---|---|")
    for name in sorted(transitions.same_setup_recurrence_rate):
        same = transitions.same_setup_recurrence_rate[name]
        cross = transitions.cross_setup_recurrence_rate[name]
        lines.append(f"| {name} | {_pct(same)} | {_pct(cross)} |")
    lines.append("")

    lines.append("## Transition matrix by session (at the FROM-episode's activation session)")
    lines.append("")
    for session, rows in sorted(transitions.by_session.items()):
        lines.append(f"### {session}")
        lines.append("")
        lines.append("| from | to | count | probability |")
        lines.append("|---|---|---|---|")
        for m in sorted(rows, key=lambda m: (m.from_setup, -m.count)):
            lines.append(f"| {m.from_setup} | {m.to_setup} | {m.count} | {_pct(m.probability)} |")
        lines.append("")

    return "\n".join(lines)
