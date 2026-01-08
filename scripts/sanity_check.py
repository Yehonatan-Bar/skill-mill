"""
Sanity Check Before Phase D

Validates data integrity before skill synthesis:
1. Every representative doc_id resolves to a real extraction JSON
2. clusters_final and representatives agree (reps are cluster members)
3. PARTIAL clusters have enough material for synthesis

Usage:
    python sanity_check.py
    python sanity_check.py --clusters-dir clusters --extractions-dir extractions
"""

import json
import argparse
from pathlib import Path
from typing import Optional


def get_default_paths():
    """Get default paths based on working directory."""
    cwd = Path.cwd()
    return {
        "clusters_dir": cwd / "clusters",
        "extractions_dir": cwd / "extractions",
    }


def load_json(path: Path) -> Optional[dict]:
    """Load JSON file safely."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


class SanityChecker:
    """Validates data integrity before Phase D."""

    def __init__(self, clusters_dir: Path, extractions_dir: Path):
        self.clusters_dir = clusters_dir
        self.final_dir = clusters_dir / "clusters_final"
        self.representatives_dir = clusters_dir / "representatives"
        self.extractions_dir = extractions_dir

    def get_all_extraction_ids(self) -> set:
        """Get all doc_ids from extraction files."""
        ids = set()
        for f in self.extractions_dir.glob("*.json"):
            data = load_json(f)
            if data:
                doc_id = data.get("doc_id") or f.stem
                ids.add(doc_id)
            ids.add(f.stem)  # Also add filename stem
        return ids

    def run(self) -> dict:
        """Run all sanity checks."""
        results = {
            "issues": [],
            "warnings": [],
            "clusters_checked": 0,
            "all_ok": True,
        }

        extraction_ids = self.get_all_extraction_ids()
        print(f"\n  Found {len(extraction_ids)} extraction IDs")

        # Check each cluster
        for cluster_file in sorted(self.final_dir.glob("*.json")):
            cluster_name = cluster_file.stem
            cluster_data = load_json(cluster_file)

            if not cluster_data:
                results["issues"].append(f"FAILED TO LOAD: {cluster_name}")
                continue

            results["clusters_checked"] += 1

            rep_file = self.representatives_dir / f"{cluster_name}.json"
            if not rep_file.exists():
                results["issues"].append(f"MISSING REP FILE: {cluster_name}")
                continue

            rep_data = load_json(rep_file)
            if not rep_data:
                results["issues"].append(f"FAILED TO LOAD REP: {cluster_name}")
                continue

            member_ids = set(cluster_data.get("member_doc_ids", []))
            rep_ids = rep_data.get("representative_doc_ids", [])

            print(f"\n  {cluster_name}")
            print(f"    Members: {len(member_ids)}, Reps: {len(rep_ids)}")

            # Check 1: Every rep resolves to extraction
            missing_extractions = []
            for doc_id in rep_ids:
                if doc_id not in extraction_ids:
                    missing_extractions.append(doc_id)

            if missing_extractions:
                results["issues"].append(
                    f"{cluster_name}: {len(missing_extractions)} reps missing extractions"
                )
                results["all_ok"] = False
            else:
                print(f"    [OK] All {len(rep_ids)} reps have extractions")

            # Check 2: Every rep is a cluster member
            orphan_reps = []
            for doc_id in rep_ids:
                if doc_id not in member_ids:
                    orphan_reps.append(doc_id)

            if orphan_reps:
                results["issues"].append(
                    f"{cluster_name}: {len(orphan_reps)} reps not in member_doc_ids"
                )
                results["all_ok"] = False
            else:
                print(f"    [OK] All reps are cluster members")

            # Check 3: Coverage quality
            coverage = rep_data.get("coverage_check", {})
            has_issues = coverage.get("has_issues_doc", False)
            has_code = coverage.get("has_code_doc", False)
            has_artifacts = coverage.get("has_artifacts_doc", False)

            coverage_str = f"issues={has_issues}, code={has_code}, artifacts={has_artifacts}"

            if not (has_issues or has_code or has_artifacts):
                results["warnings"].append(
                    f"{cluster_name}: THIN SKILL - no issues/code/artifacts"
                )
                print(f"    [WARN] Thin skill - {coverage_str}")
            elif not (has_issues and has_code):
                print(f"    [PARTIAL] {coverage_str}")
            else:
                print(f"    [OK] Good coverage - {coverage_str}")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Sanity Check Before Phase D"
    )

    defaults = get_default_paths()

    parser.add_argument("--clusters-dir", type=str, default=str(defaults["clusters_dir"]))
    parser.add_argument("--extractions-dir", type=str, default=str(defaults["extractions_dir"]))

    args = parser.parse_args()

    print("=" * 60)
    print("SANITY CHECK BEFORE PHASE D")
    print("=" * 60)

    checker = SanityChecker(
        clusters_dir=Path(args.clusters_dir),
        extractions_dir=Path(args.extractions_dir),
    )

    results = checker.run()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\n  Clusters checked: {results['clusters_checked']}")

    if results["issues"]:
        print(f"\n  [ERRORS] {len(results['issues'])} issues found:")
        for issue in results["issues"]:
            print(f"    - {issue}")
    else:
        print("\n  [OK] No critical issues found")

    if results["warnings"]:
        print(f"\n  [WARNINGS] {len(results['warnings'])} thin skills:")
        for warning in results["warnings"]:
            print(f"    - {warning}")

    print("\n" + "=" * 60)
    if results["issues"]:
        print("VERDICT: FIX ISSUES BEFORE PHASE D")
        return 1
    else:
        print("VERDICT: READY FOR PHASE D")
        return 0


if __name__ == "__main__":
    exit(main())
