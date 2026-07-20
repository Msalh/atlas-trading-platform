"""
Sprint RE-1. Markdown rendering for the five RE-1 deliverables - deliberately
thin, mechanical templates over an already-computed StatisticalProfile, the
same "rendering step over deterministic content, never a tool that decides
what a finding means" discipline atlas.research.serialization
.research_report_to_markdown already established. No number is computed
here - every value is read directly from the StatisticalProfile passed in.
"""
from atlas.research.statistical_profiling.models import RunManifest, StatisticalProfile


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _num(value, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _render_manifest(manifest: RunManifest, title: str, validation_run: bool = False) -> list[str]:
    lines = [
        f"# {title}",
        "",
    ]
    if validation_run:
        lines += [
            "> **VALIDATION RUN** - this report exists to prove the RE-1 pipeline computes correctly, "
            "not to characterize real market behavior. The dataset behind it "
            f"({manifest.row_count} bars) is a correctness-validation dataset, not a basis for any "
            "market-characteristics or trading conclusion. The same pipeline, unchanged, is designed "
            "to be re-run against a much larger historical dataset once one is available.",
            "",
        ]
    lines += [
        f"- **Symbol**: {manifest.symbol}  **Timeframe**: {manifest.timeframe}",
        f"- **Requested range**: {manifest.requested_start} -> {manifest.requested_end}",
        f"- **Source**: {manifest.source_description}",
        f"- **Row count**: {manifest.row_count}",
        f"- **Generated at**: {manifest.generated_at}",
        f"- **Code version**: {manifest.code_version or 'unknown'}",
        "",
        "No trading conclusions. No alpha claims. No expectancy. No forward returns.",
        "This is a statistical characterization of the Market State only.",
        "",
    ]
    return lines


def render_fact_profile_report(profile: StatisticalProfile, validation_run: bool = False) -> str:
    lines = _render_manifest(profile.manifest, "RE-1 Fact Profile", validation_run)
    for fact_name, fp in profile.fact_profiles.items():
        base = fp.base
        lines.append(f"## {fact_name} ({base.value_kind})")
        lines.append("")
        lines.append(f"- Computable: {base.computable_count}  Insufficient data: {base.insufficient_data_count}")
        if base.value_kind == "boolean":
            lines.append(f"- True: {_pct(base.firing_rate)} ({base.value_counts.get('true', 0)})  "
                          f"False: {base.value_counts.get('false', 0)}")
        else:
            lines.append("- First-order distribution (value: count):")
            total = sum(base.value_counts.values()) or 1
            for value, count in sorted(base.value_counts.items()):
                lines.append(f"  - {value}: {count} ({count / total * 100:.1f}%)")
        lines.append("")
        lines.append("**Persistence summary** (see RE1_Persistence.md for full run-length distributions):")
        lines.append("")
        lines.append("| value | run count | mean length | median length | p95 length | max length |")
        lines.append("|---|---|---|---|---|---|")
        for stats in fp.run_length_stats:
            lines.append(
                f"| {stats.value} | {stats.run_count} | {_num(stats.mean_length, 2)} | "
                f"{stats.median_length if stats.median_length is not None else 'n/a'} | "
                f"{stats.p95_length if stats.p95_length is not None else 'n/a'} | "
                f"{stats.max_length if stats.max_length is not None else 'n/a'} |"
            )
        lines.append("")
        lines.append("**Transitions** (P(next value | current value), consecutive computable bars only):")
        lines.append("")
        values = sorted(fp.transitions.probabilities.keys())
        if values:
            lines.append("| from \\ to | " + " | ".join(values) + " |")
            lines.append("|---|" + "---|" * len(values))
            for a in values:
                row = " | ".join(_pct(fp.transitions.probabilities[a][b]) for b in values)
                lines.append(f"| {a} | {row} |")
        else:
            lines.append("(no computable observations)")
        lines.append("")
    return "\n".join(lines)


def render_rule_relationships_report(profile: StatisticalProfile, validation_run: bool = False) -> str:
    lines = _render_manifest(profile.manifest, "RE-1 Rule Relationships", validation_run)
    lines.append("## Boolean fact pairs")
    lines.append("")
    lines.append(
        "| fact A | fact B | n | P(A) | P(B) | P(A and B) | lift | correlation | "
        "P(A\\|B) - P(A) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for rel in profile.pairwise_relationships:
        if not rel.both_boolean:
            continue
        lines.append(
            f"| {rel.fact_a} | {rel.fact_b} | {rel.jointly_computable_count} | "
            f"{_pct(rel.p_a_true)} | {_pct(rel.p_b_true)} | {_pct(rel.p_both_true)} | "
            f"{_num(rel.lift)} | {_num(rel.correlation)} | {_num(rel.conditional_dependence)} |"
        )
    lines.append("")
    lines.append(
        "lift > 1 means the two facts co-occur more often than independence would predict; "
        "lift < 1 means less often. correlation is the Pearson coefficient over the two facts' "
        "0/1 series. Neither implies causation or a trading edge - purely descriptive association."
    )
    lines.append("")

    lines.append("## Pairs involving an enum fact (trend_5m, vwap_relationship)")
    lines.append("")
    lines.append(
        "No single lift/correlation number applies (no single 'positive' value) - reported as a "
        "joint frequency (contingency) table instead."
    )
    lines.append("")
    for rel in profile.pairwise_relationships:
        if rel.both_boolean or rel.category_joint_counts is None:
            continue
        lines.append(f"### {rel.fact_a} x {rel.fact_b} (n={rel.jointly_computable_count})")
        lines.append("")
        b_values = sorted({b for row in rel.category_joint_counts.values() for b in row})
        if b_values:
            lines.append(f"| {rel.fact_a} \\ {rel.fact_b} | " + " | ".join(b_values) + " |")
            lines.append("|---|" + "---|" * len(b_values))
            for a_value in sorted(rel.category_joint_counts):
                row = " | ".join(str(rel.category_joint_counts[a_value].get(b, 0)) for b in b_values)
                lines.append(f"| {a_value} | {row} |")
        lines.append("")
    return "\n".join(lines)


def render_conditional_probability_report(profile: StatisticalProfile, validation_run: bool = False) -> str:
    lines = _render_manifest(profile.manifest, "RE-1 Conditional Probability", validation_run)
    lines.append(
        "P(target = target_value | condition = condition_value), over bars where both facts are "
        "computable. Exhaustive over every ordered pair of distinct registered facts."
    )
    lines.append("")

    by_pair: dict[tuple[str, str], list] = {}
    for entry in profile.conditional_probabilities:
        by_pair.setdefault((entry.condition_fact, entry.target_fact), []).append(entry)

    for (condition_fact, target_fact), entries in by_pair.items():
        lines.append(f"## P({target_fact} | {condition_fact})")
        lines.append("")
        lines.append(f"| {condition_fact} = | {target_fact} = | probability | n (condition sample size) |")
        lines.append("|---|---|---|---|")
        for entry in entries:
            lines.append(
                f"| {entry.condition_value} | {entry.target_value} | "
                f"{_pct(entry.probability)} | {entry.condition_sample_size} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_time_distribution_report(profile: StatisticalProfile, validation_run: bool = False) -> str:
    lines = _render_manifest(profile.manifest, "RE-1 Time Distribution", validation_run)
    td = profile.time_distribution

    def _section(title: str, buckets) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not buckets:
            lines.append("(no data)")
            lines.append("")
            return
        boolean_facts = sorted(buckets[0].boolean_fact_true_rates.keys())
        lines.append("| bucket | bar count | " + " | ".join(f"P({f}=True)" for f in boolean_facts) + " |")
        lines.append("|---|---|" + "---|" * len(boolean_facts))
        for bucket in buckets:
            rates = " | ".join(_pct(bucket.boolean_fact_true_rates.get(f)) for f in boolean_facts)
            lines.append(f"| {bucket.bucket_key} | {bucket.bar_count} | {rates} |")
        lines.append("")
        enum_facts = sorted(buckets[0].enum_fact_value_counts.keys())
        for fact_name in enum_facts:
            lines.append(f"**{fact_name} value counts by bucket:**")
            lines.append("")
            values = sorted({v for bucket in buckets for v in bucket.enum_fact_value_counts[fact_name]})
            lines.append("| bucket | " + " | ".join(values) + " |")
            lines.append("|---|" + "---|" * len(values))
            for bucket in buckets:
                counts = bucket.enum_fact_value_counts[fact_name]
                row = " | ".join(str(counts.get(v, 0)) for v in values)
                lines.append(f"| {bucket.bucket_key} | {row} |")
            lines.append("")

    _section("By session", td.by_session)
    _section("By hour (America/Chicago)", td.by_hour_ct)
    _section("By weekday (America/Chicago)", td.by_weekday_ct)
    return "\n".join(lines)


def render_persistence_report(profile: StatisticalProfile, validation_run: bool = False) -> str:
    lines = _render_manifest(profile.manifest, "RE-1 Persistence", validation_run)
    lines.append(
        "Full run-length distributions per fact and value - how many consecutive bars a state "
        "typically holds before changing. A run never bridges a gap in computability or a data "
        "segment boundary."
    )
    lines.append("")
    for fact_name, fp in profile.fact_profiles.items():
        lines.append(f"## {fact_name}")
        lines.append("")
        for stats in fp.run_length_stats:
            lines.append(f"### value = {stats.value}")
            lines.append("")
            lines.append(
                f"- Runs: {stats.run_count}  Total bars covered: {stats.total_bars_in_runs}  "
                f"Mean length: {_num(stats.mean_length, 2)}  Median: {stats.median_length}  "
                f"p95: {stats.p95_length}  Max: {stats.max_length}"
            )
            lines.append("")
            if stats.length_histogram:
                lines.append("| run length (bars) | number of runs |")
                lines.append("|---|---|")
                for length in sorted(stats.length_histogram):
                    lines.append(f"| {length} | {stats.length_histogram[length]} |")
            else:
                lines.append("(no runs observed)")
            lines.append("")
    return "\n".join(lines)
