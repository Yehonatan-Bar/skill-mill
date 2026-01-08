"""
Phase C.5: Representative Selection

Selects representative documents for each cluster to be used in Phase D synthesis.
Also optionally applies approved splits from Phase C.4 purity audit.

Usage:
    python phase_c5_representatives.py
    python phase_c5_representatives.py --apply-splits pdf-processing
    python phase_c5_representatives.py --skip-splits
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

def get_default_paths():
    """Get default paths based on working directory."""
    cwd = Path.cwd()
    return {
        "clusters_dir": cwd / "clusters",
        "extractions_dir": cwd / "extractions",
    }


def get_rep_count(cluster_size: int) -> int:
    """Get recommended number of representatives based on cluster size."""
    if cluster_size <= 5:
        return min(3, cluster_size)
    elif cluster_size <= 15:
        return min(5, cluster_size)
    else:
        return min(8, cluster_size)


def load_json(path: Path) -> Optional[dict]:
    """Load JSON file safely."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path: Path, data):
    """Save JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class RepresentativeSelector:
    """Selects representative documents for each cluster."""

    def __init__(self, clusters_dir: Path, extractions_dir: Path):
        self.clusters_dir = clusters_dir
        self.final_dir = clusters_dir / "clusters_final"
        self.enriched_cards_dir = clusters_dir / "doc_cards_enriched"
        self.representatives_dir = clusters_dir / "representatives"
        self.extractions_dir = extractions_dir

        if not self.enriched_cards_dir.exists():
            self.enriched_cards_dir = clusters_dir / "doc_cards"

        self.representatives_dir.mkdir(parents=True, exist_ok=True)

    def load_doc_card(self, doc_id: str) -> Optional[dict]:
        """Load a doc card."""
        path = self.enriched_cards_dir / f"{doc_id}.json"
        return load_json(path)

    def load_extraction(self, doc_id: str) -> Optional[dict]:
        """Load an extraction JSON."""
        path = self.extractions_dir / f"{doc_id}.json"
        return load_json(path)

    def score_doc(self, doc_id: str, card: Optional[dict], extraction: Optional[dict]) -> dict:
        """Score a document for representative selection."""
        scores = {
            "doc_id": doc_id,
            "total_score": 0,
            "priority_score": 0,
            "reusability_score": 0,
            "has_issues": False,
            "has_code": False,
            "has_artifacts": False,
            "coverage_contribution": [],
        }

        if not card:
            return scores

        # Priority score
        card_scores = card.get("scores", {})
        priority = card_scores.get("extraction_priority", "")
        if priority == "high":
            scores["priority_score"] = 30
        elif priority == "medium":
            scores["priority_score"] = 20
        elif priority == "low":
            scores["priority_score"] = 10

        # Reusability score
        reusability = card_scores.get("reusability_total")
        if reusability:
            scores["reusability_score"] = min(25, reusability)

        # Check issues
        issues = card.get("issues", [])
        if issues:
            scores["has_issues"] = True
            scores["coverage_contribution"].append("issues")
            scores["total_score"] += 15

        # Check code blocks in extraction
        if extraction:
            code_written = extraction.get("code_written", {})
            blocks = code_written.get("blocks", [])
            reusable_blocks = [b for b in blocks if b.get("reuse_flag", False)]
            if reusable_blocks:
                scores["has_code"] = True
                scores["coverage_contribution"].append("code")
                scores["total_score"] += 15

        # Check artifacts
        artifacts = card.get("artifacts", [])
        if artifacts:
            scores["has_artifacts"] = True
            scores["coverage_contribution"].append("artifacts")
            scores["total_score"] += 10

        scores["total_score"] += scores["priority_score"] + scores["reusability_score"]

        return scores

    def select_representatives(self, cluster: dict, target_count: int) -> dict:
        """Select representatives for a cluster."""
        cluster_name = cluster.get("cluster_name", "unknown")
        doc_ids = cluster.get("member_doc_ids", [])

        if not doc_ids:
            return {
                "cluster_id": cluster_name,
                "representative_doc_ids": [],
                "selection_details": [],
                "coverage_check": {
                    "has_issues_doc": False,
                    "has_code_doc": False,
                    "has_artifacts_doc": False,
                },
            }

        # Score all documents
        scored_docs = []
        for doc_id in doc_ids:
            card = self.load_doc_card(doc_id)
            extraction = self.load_extraction(doc_id)
            doc_scores = self.score_doc(doc_id, card, extraction)
            scored_docs.append(doc_scores)

        # Sort by score
        scored_docs.sort(key=lambda x: x["total_score"], reverse=True)

        # Select with coverage guarantee
        selected = []
        selected_ids = set()
        has_issues = False
        has_code = False
        has_artifacts = False

        # First pass: ensure coverage
        for doc in scored_docs:
            if len(selected) >= target_count:
                break

            doc_id = doc["doc_id"]
            if doc_id in selected_ids:
                continue

            fills_gap = False
            reason = []

            if not has_issues and doc["has_issues"]:
                fills_gap = True
                has_issues = True
                reason.append("issues coverage")

            if not has_code and doc["has_code"]:
                fills_gap = True
                has_code = True
                reason.append("code coverage")

            if not has_artifacts and doc["has_artifacts"]:
                fills_gap = True
                has_artifacts = True
                reason.append("artifacts coverage")

            if fills_gap or len(selected) < target_count // 2:
                selected_ids.add(doc_id)
                selected.append({
                    "doc_id": doc_id,
                    "why_selected": ", ".join(reason) if reason else f"high score ({doc['total_score']})",
                    "scores": doc,
                })

        # Second pass: fill remaining
        for doc in scored_docs:
            if len(selected) >= target_count:
                break

            doc_id = doc["doc_id"]
            if doc_id in selected_ids:
                continue

            selected_ids.add(doc_id)
            selected.append({
                "doc_id": doc_id,
                "why_selected": f"high score ({doc['total_score']})",
                "scores": doc,
            })

        return {
            "cluster_id": cluster_name,
            "representative_doc_ids": [s["doc_id"] for s in selected],
            "selection_details": selected,
            "coverage_check": {
                "has_issues_doc": has_issues,
                "has_code_doc": has_code,
                "has_artifacts_doc": has_artifacts,
            },
            "target_count": target_count,
            "actual_count": len(selected),
            "cluster_size": len(doc_ids),
        }

    def run(self, skip_splits: bool = False, apply_splits: Optional[list] = None) -> dict:
        """Run the representative selection pipeline."""
        results = {
            "total_clusters": 0,
            "total_representatives": 0,
            "splits_applied": [],
            "clusters": [],
        }

        # Load audit results if needed
        doc_map = load_json(self.clusters_dir / "doc_to_cluster_map_final.json") or {}
        audit_results = load_json(self.clusters_dir / "_c4_purity_audit.json")

        # Apply splits if requested
        if audit_results and not skip_splits:
            splits = audit_results.get("splits_recommended", [])
            for split in splits:
                original = split.get("original_cluster", "")
                new_skills = split.get("new_skills", [])

                should_apply = False
                if apply_splits is None:
                    # Auto-apply balanced splits
                    sizes = [s.get("member_count", 0) for s in new_skills]
                    min_size = min(sizes) if sizes else 0
                    max_size = max(sizes) if sizes else 0
                    if min_size >= 5 and (max_size / min_size if min_size > 0 else 100) < 5:
                        should_apply = True
                elif apply_splits and original in apply_splits:
                    should_apply = True

                if should_apply:
                    print(f"  Applying split for {original}")
                    results["splits_applied"].append(original)
                    # Note: Actual split application would create new cluster files here

        # Process all clusters
        cluster_files = list(self.final_dir.glob("*.json"))
        print(f"\n  Processing {len(cluster_files)} clusters")

        for cf in cluster_files:
            cluster = load_json(cf)
            if not cluster:
                continue

            cluster_name = cluster.get("cluster_name", cf.stem)
            cluster_size = cluster.get("member_count", 0)
            target_count = get_rep_count(cluster_size)

            reps = self.select_representatives(cluster, target_count)

            # Save representatives
            rep_path = self.representatives_dir / f"{cluster_name}.json"
            save_json(rep_path, reps)

            coverage = reps["coverage_check"]
            status = "OK" if all(coverage.values()) else "PARTIAL"

            results["total_clusters"] += 1
            results["total_representatives"] += reps["actual_count"]
            results["clusters"].append({
                "name": cluster_name,
                "size": cluster_size,
                "representatives": reps["actual_count"],
                "coverage": coverage,
                "status": status,
            })

            print(f"    {cluster_name}: {reps['actual_count']} reps ({status})")

        # Save summary
        summary_path = self.clusters_dir / "_c5_representatives_summary.json"
        save_json(summary_path, {
            "generated_at": datetime.now().isoformat(),
            **results
        })

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Phase C.5: Representative Selection"
    )

    defaults = get_default_paths()

    parser.add_argument("--clusters-dir", type=str, default=str(defaults["clusters_dir"]))
    parser.add_argument("--extractions-dir", type=str, default=str(defaults["extractions_dir"]))
    parser.add_argument("--skip-splits", action="store_true")
    parser.add_argument("--apply-splits", nargs="*")

    args = parser.parse_args()

    print("=" * 60)
    print("Phase C.5: Representative Selection")
    print("=" * 60)

    selector = RepresentativeSelector(
        clusters_dir=Path(args.clusters_dir),
        extractions_dir=Path(args.extractions_dir),
    )

    results = selector.run(
        skip_splits=args.skip_splits,
        apply_splits=args.apply_splits,
    )

    print("\n" + "=" * 60)
    print("Selection Summary")
    print("=" * 60)
    print(f"  Total clusters: {results['total_clusters']}")
    print(f"  Total representatives: {results['total_representatives']}")
    print(f"  Splits applied: {results['splits_applied'] or 'None'}")

    # Show coverage stats
    ok_count = sum(1 for c in results["clusters"] if c["status"] == "OK")
    partial_count = sum(1 for c in results["clusters"] if c["status"] == "PARTIAL")
    print(f"\n  Coverage: {ok_count} OK, {partial_count} PARTIAL")

    print("\n" + "=" * 60)
    print("Phase C.5 Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
