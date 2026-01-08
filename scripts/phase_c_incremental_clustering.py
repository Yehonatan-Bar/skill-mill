"""
Phase C.3: Incremental Clustering

This module performs online clustering within each bucket using AI-assisted
"incremental assignment". For each document in a bucket, the AI decides whether
to assign it to an existing cluster or create a new one.

This avoids expensive pairwise comparisons and scales well with large buckets.

Usage:
    python phase_c_incremental_clustering.py --api-key YOUR_KEY
    python phase_c_incremental_clustering.py --min-bucket-size 3
    python phase_c_incremental_clustering.py --max-buckets 10  # Test mode
"""

import json
import os
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    exit(1)


def get_default_paths():
    """Get default paths based on working directory."""
    cwd = Path.cwd()
    return {
        "clusters_dir": cwd / "clusters",
    }


class IncrementalClusteringPipeline:
    """AI-assisted incremental clustering within buckets."""

    def __init__(
        self,
        clusters_dir: Path,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        min_bucket_size: int = 1,
        max_clusters_per_prompt: int = 10,
    ):
        self.clusters_dir = clusters_dir
        self.enriched_cards_dir = clusters_dir / "doc_cards_enriched"
        self.enriched_buckets_dir = clusters_dir / "buckets_enriched"
        self.output_dir = clusters_dir / "clusters_incremental"
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.min_bucket_size = min_bucket_size
        self.max_clusters_per_prompt = max_clusters_per_prompt

        # Fallback to non-enriched if enriched doesn't exist
        if not self.enriched_cards_dir.exists():
            self.enriched_cards_dir = clusters_dir / "doc_cards"
        if not self.enriched_buckets_dir.exists():
            self.enriched_buckets_dir = clusters_dir / "buckets"

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_bucket(self, bucket_path: Path) -> Optional[dict]:
        """Load a bucket file."""
        try:
            with open(bucket_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  WARNING: Failed to load {bucket_path}: {e}")
            return None

    def load_doc_card(self, doc_id: str) -> Optional[dict]:
        """Load a doc card by ID."""
        path = self.enriched_cards_dir / f"{doc_id}.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def build_cluster_signature(self, cluster: dict) -> str:
        """Build a compact signature for a cluster."""
        sig_parts = []

        sig_parts.append(f"Name: {cluster.get('cluster_name', 'unnamed')}")
        sig_parts.append(f"Description: {cluster.get('cluster_description', '')[:200]}")

        tags = cluster.get('top_tags', {})
        if tags.get('domains'):
            sig_parts.append(f"Domains: {', '.join(tags['domains'][:5])}")
        if tags.get('patterns'):
            sig_parts.append(f"Patterns: {', '.join(tags['patterns'][:5])}")

        triggers = cluster.get('trigger_phrases', [])
        if triggers:
            sig_parts.append(f"Triggers: {', '.join(triggers[:5])}")

        outputs = cluster.get('typical_outputs', [])
        if outputs:
            sig_parts.append(f"Outputs: {', '.join(outputs[:5])}")

        sig_parts.append(f"Member count: {cluster.get('member_count', 0)}")

        return '\n'.join(sig_parts)

    def build_doc_card_summary(self, card: dict) -> str:
        """Build a compact summary of a doc card for the prompt."""
        parts = []

        parts.append(f"Doc ID: {card.get('doc_id', 'unknown')}")

        trigger = card.get('trigger', {})
        if trigger.get('what_triggered'):
            parts.append(f"Trigger: {trigger['what_triggered'][:200]}")
        if trigger.get('keywords'):
            parts.append(f"Keywords: {', '.join(trigger['keywords'][:5])}")

        tags = card.get('tags', {})
        if tags.get('domains'):
            parts.append(f"Domains: {', '.join(tags['domains'][:3])}")
        if tags.get('patterns'):
            parts.append(f"Patterns: {', '.join(tags['patterns'][:3])}")

        steps = card.get('workflow_steps', [])
        if steps:
            parts.append(f"Workflow: {' -> '.join(steps[:3])}")

        artifacts = card.get('artifacts', [])
        if artifacts:
            parts.append(f"Artifacts: {', '.join(artifacts[:3])}")

        return '\n'.join(parts)

    def build_assignment_prompt(self, card: dict, clusters: list) -> str:
        """Build the prompt for cluster assignment."""
        card_summary = self.build_doc_card_summary(card)

        if not clusters:
            prompt = f"""This is the first document in a new bucket. Create an initial cluster for it.

DOCUMENT:
{card_summary}

Create a cluster that could potentially group similar documents.

RESPOND WITH ONLY THIS JSON:
{{
    "decision": "new_cluster",
    "cluster_name": "kebab-case-name",
    "cluster_description": "2-3 sentences describing what this cluster captures",
    "confidence": 0.8,
    "reason": "Brief explanation"
}}

Use kebab-case for cluster_name. Make the description specific enough to distinguish from other potential clusters."""

        else:
            cluster_summaries = []
            for i, cluster in enumerate(clusters[:self.max_clusters_per_prompt]):
                sig = self.build_cluster_signature(cluster)
                cluster_summaries.append(f"CLUSTER {i + 1}: {cluster.get('cluster_name', 'unnamed')}\n{sig}")

            clusters_text = "\n\n---\n\n".join(cluster_summaries)

            prompt = f"""Decide whether this document belongs to an existing cluster or needs a new cluster.

DOCUMENT:
{card_summary}

EXISTING CLUSTERS:
{clusters_text}

DECISION CRITERIA:
- ASSIGN if the document clearly fits an existing cluster (same trigger type, similar workflow, similar outputs)
- NEW_CLUSTER if the document represents a distinctly different task type

RESPOND WITH ONLY THIS JSON:
{{
    "decision": "assign" or "new_cluster",
    "cluster_name": "name of existing cluster to assign to, or new kebab-case name if creating",
    "cluster_description": "only needed if decision is new_cluster",
    "confidence": 0.0-1.0,
    "reason": "Brief explanation of decision",
    "updated_signature": {{
        "trigger_phrases": ["if decision is assign, list any new trigger phrases to add"],
        "typical_outputs": ["if decision is assign, list any new outputs to add"]
    }}
}}

Be conservative - prefer assigning to existing clusters unless the document is truly different."""

        return prompt

    def process_bucket(self, bucket: dict) -> dict:
        """Process a single bucket with incremental clustering."""
        bucket_key = bucket.get('bucket_key', 'unknown')
        doc_ids = bucket.get('doc_ids', [])

        result = {
            "bucket_key": bucket_key,
            "total_docs": len(doc_ids),
            "clusters": [],
            "assignments": [],
        }

        if not doc_ids:
            return result

        clusters = []  # Active clusters in this bucket

        for i, doc_id in enumerate(doc_ids):
            card = self.load_doc_card(doc_id)
            if not card:
                print(f"    WARNING: Card not found for {doc_id}")
                continue

            # Build and send prompt
            prompt = self.build_assignment_prompt(card, clusters)

            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=800,
                    messages=[{"role": "user", "content": prompt}]
                )

                response_text = response.content[0].text.strip()

                # Handle markdown code fences
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    json_lines = []
                    in_block = False
                    for line in lines:
                        if line.startswith("```") and not in_block:
                            in_block = True
                            continue
                        elif line.startswith("```") and in_block:
                            break
                        elif in_block:
                            json_lines.append(line)
                    response_text = "\n".join(json_lines)

                decision = json.loads(response_text)

                if decision.get('decision') == 'new_cluster':
                    # Create new cluster
                    new_cluster = {
                        "cluster_name": decision.get('cluster_name', f'cluster-{len(clusters) + 1}'),
                        "cluster_description": decision.get('cluster_description', ''),
                        "member_doc_ids": [doc_id],
                        "member_count": 1,
                        "top_tags": card.get('tags', {}),
                        "trigger_phrases": card.get('trigger', {}).get('keywords', []),
                        "typical_outputs": card.get('artifacts', []),
                        "singleton": len(doc_ids) == 1,
                    }
                    clusters.append(new_cluster)

                    result["assignments"].append({
                        "doc_id": doc_id,
                        "decision": "new_cluster",
                        "cluster_name": new_cluster["cluster_name"],
                        "confidence": decision.get('confidence', 0),
                    })

                else:
                    # Assign to existing cluster
                    target_name = decision.get('cluster_name', '')
                    target_cluster = None

                    for cluster in clusters:
                        if cluster['cluster_name'] == target_name:
                            target_cluster = cluster
                            break

                    if target_cluster:
                        target_cluster['member_doc_ids'].append(doc_id)
                        target_cluster['member_count'] += 1
                        target_cluster['singleton'] = False

                        # Update signature
                        updated_sig = decision.get('updated_signature', {})
                        if updated_sig.get('trigger_phrases'):
                            existing = set(target_cluster.get('trigger_phrases', []))
                            for phrase in updated_sig['trigger_phrases']:
                                if phrase and phrase not in existing:
                                    target_cluster['trigger_phrases'].append(phrase)

                        if updated_sig.get('typical_outputs'):
                            existing = set(target_cluster.get('typical_outputs', []))
                            for output in updated_sig['typical_outputs']:
                                if output and output not in existing:
                                    target_cluster['typical_outputs'].append(output)

                        result["assignments"].append({
                            "doc_id": doc_id,
                            "decision": "assign",
                            "cluster_name": target_name,
                            "confidence": decision.get('confidence', 0),
                        })
                    else:
                        # Fallback: create new cluster if target not found
                        print(f"    WARNING: Target cluster '{target_name}' not found, creating new")
                        new_cluster = {
                            "cluster_name": decision.get('cluster_name', f'cluster-{len(clusters) + 1}'),
                            "cluster_description": decision.get('cluster_description', ''),
                            "member_doc_ids": [doc_id],
                            "member_count": 1,
                            "top_tags": card.get('tags', {}),
                            "trigger_phrases": card.get('trigger', {}).get('keywords', []),
                            "typical_outputs": card.get('artifacts', []),
                            "singleton": False,
                        }
                        clusters.append(new_cluster)

            except Exception as e:
                print(f"    ERROR processing {doc_id}: {e}")
                # Fallback: create singleton cluster
                new_cluster = {
                    "cluster_name": f'singleton-{doc_id[:20]}',
                    "cluster_description": 'Auto-created singleton cluster',
                    "member_doc_ids": [doc_id],
                    "member_count": 1,
                    "top_tags": card.get('tags', {}) if card else {},
                    "trigger_phrases": [],
                    "typical_outputs": [],
                    "singleton": True,
                }
                clusters.append(new_cluster)

        result["clusters"] = clusters
        return result

    def run(self, max_buckets: Optional[int] = None) -> dict:
        """Run the incremental clustering pipeline."""
        results = {
            "total_buckets": 0,
            "processed_buckets": 0,
            "total_clusters": 0,
            "total_documents": 0,
            "bucket_results": [],
        }

        # Find all buckets
        bucket_files = list(self.enriched_buckets_dir.glob("*.json"))
        results["total_buckets"] = len(bucket_files)

        # Filter by size
        buckets_to_process = []
        for bf in bucket_files:
            bucket = self.load_bucket(bf)
            if bucket and len(bucket.get('doc_ids', [])) >= self.min_bucket_size:
                buckets_to_process.append((bf, bucket))

        if max_buckets:
            buckets_to_process = buckets_to_process[:max_buckets]

        print(f"\n  Processing {len(buckets_to_process)} buckets (>= {self.min_bucket_size} docs)")

        for i, (bucket_file, bucket) in enumerate(buckets_to_process, 1):
            bucket_key = bucket.get('bucket_key', bucket_file.stem)
            doc_count = len(bucket.get('doc_ids', []))

            print(f"\n  [{i}/{len(buckets_to_process)}] {bucket_key} ({doc_count} docs)")

            bucket_result = self.process_bucket(bucket)

            # Save result
            safe_key = bucket_key.replace('/', '-').replace('\\', '-')
            output_path = self.output_dir / f"{safe_key}.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(bucket_result, f, indent=2, ensure_ascii=False)

            results["processed_buckets"] += 1
            results["total_clusters"] += len(bucket_result["clusters"])
            results["total_documents"] += bucket_result["total_docs"]
            results["bucket_results"].append({
                "bucket_key": bucket_key,
                "docs": bucket_result["total_docs"],
                "clusters": len(bucket_result["clusters"]),
            })

            print(f"    -> Created {len(bucket_result['clusters'])} clusters")

        # Save summary
        summary = {
            "generated_at": datetime.now().isoformat(),
            "results": results,
        }
        summary_path = self.clusters_dir / "_incremental_clustering_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Phase C.3: Incremental Clustering"
    )

    defaults = get_default_paths()

    parser.add_argument(
        "--api-key",
        type=str,
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )

    parser.add_argument(
        "--clusters-dir",
        type=str,
        default=str(defaults["clusters_dir"]),
        help="Clusters directory"
    )

    parser.add_argument(
        "--min-bucket-size",
        type=int,
        default=1,
        help="Minimum bucket size to process"
    )

    parser.add_argument(
        "--max-buckets",
        type=int,
        help="Maximum buckets to process (for testing)"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Model to use"
    )

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No API key provided. Use --api-key or set ANTHROPIC_API_KEY")
        exit(1)

    clusters_dir = Path(args.clusters_dir)

    print("=" * 60)
    print("Phase C.3: Incremental Clustering")
    print("=" * 60)

    pipeline = IncrementalClusteringPipeline(
        clusters_dir=clusters_dir,
        api_key=api_key,
        model=args.model,
        min_bucket_size=args.min_bucket_size,
    )

    results = pipeline.run(max_buckets=args.max_buckets)

    print("\n" + "=" * 60)
    print("Incremental Clustering Summary")
    print("=" * 60)
    print(f"  Buckets processed: {results['processed_buckets']}/{results['total_buckets']}")
    print(f"  Total clusters: {results['total_clusters']}")
    print(f"  Total documents: {results['total_documents']}")

    if results['bucket_results']:
        print(f"\n  Top 10 buckets by cluster count:")
        sorted_results = sorted(results['bucket_results'], key=lambda x: -x['clusters'])
        for br in sorted_results[:10]:
            print(f"    {br['bucket_key']}: {br['clusters']} clusters, {br['docs']} docs")

    print("\n" + "=" * 60)
    print("Phase C.3 Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
