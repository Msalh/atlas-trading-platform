"""
UI v2. Thin CLI wrapping atlas.research_export.snapshot_builder - writes
the three checked-in live/research/snapshots/*.json files. Mirrors
run_statistical_profile.py's/run_setup_profile.py's own CLI shape.

No computation happens in this script - it calls the already-frozen
RE-1/RE-2 pipelines (via snapshot_builder, unchanged) and writes their
serialized, checksummed output to disk.

Production-hardening amendment 2: the default output directory is inside
live/ (resolved relative to this script's own location, not the caller's
cwd) so the snapshots always land where atlas/api/v1/research.py's
SNAPSHOTS_DIR expects them, regardless of which directory this script is
invoked from.

Usage:
    python scripts/export_research_snapshots.py
    python scripts/export_research_snapshots.py --out /some/other/dir
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas.research_export import snapshot_builder  # noqa: E402
from atlas.research_export.serialization import pretty_json  # noqa: E402


_DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "snapshots")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=_DEFAULT_OUT, help="Output directory for the *.v1.json snapshots")
    args = parser.parse_args()

    exported_at = datetime.now(timezone.utc)
    print(f"Building research snapshots (exported_at={exported_at.isoformat()})...")
    snapshots = snapshot_builder.build_all_snapshots(exported_at)

    os.makedirs(args.out, exist_ok=True)
    for filename, snapshot in snapshots.items():
        content = pretty_json(snapshot)
        path = os.path.join(args.out, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        checksum = snapshot["envelope"]["content_checksum"]
        source_version = snapshot["envelope"]["source_computation_version"]
        print(f"Wrote {path} ({len(content)} chars) "
              f"source_computation_version={source_version} content_checksum={checksum[:16]}...")

    print("\nDone. Commit these files alongside any regenerated research/RE1_*.md / RE2_*.md reports.")


if __name__ == "__main__":
    main()
