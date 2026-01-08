"""
Phase C.4: Cross-Bucket Cluster Merging

This module merges fragmented clusters across buckets into skill-ready clusters.
Uses a "rollup-first" strategy where clusters are grouped by domain, then AI
suggests whether to keep as one skill or split into sub-skills.

Usage:
    python phase_c4_merge_clusters.py --api-key YOUR_KEY
    python phase_c4_merge_clusters.py --rollup-first  # Aggressive merge
    python phase_c4_merge_clusters.py --dry-run       # Preview only
"""

import json
import os
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from itertools import combinations
from typing import Optional

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


# Default domain rollups - users should customize for their domain
DEFAULT_DOMAIN_ROLLUPS = {
    "pdf-processing": ["pdf-processing", "pdf-extraction", "document-processing", "text-extraction"],
    "data-analysis": ["data-analysis", "data-processing", "data-validation", "data-profiling", "excel"],
    "frontend": ["frontend", "ui", "dashboard", "html-generation", "forms"],
    "api-development": ["api-development", "backend", "api", "fastapi"],
    "deployment": ["deployment", "infrastructure", "devops", "ci-cd"],
    "ai-integration": ["ai-integration", "llm", "prompt-engineering", "machine-learning"],
    "monitoring": ["monitoring", "logging", "observability", "error-handling"],
}

SIMILARITY_THRESHOLD = 0.25


class ClusterMergePipeline:
    """Merges fragmented clusters into skill-ready clusters."""

    def __init__(
        self,
        clusters_dir: Path,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        domain_rollups: Optional[dict] = None,
    ):
        self.clusters_dir = clusters_dir
        self.incremental_dir = clusters_dir / "clusters_incremental"
        self.final_dir = clusters_dir / "clusters_final"
        self.enriched_cards_dir = clusters_dir / "doc_cards_enriched"
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.domain_rollups = domain_rollups or DEFAULT_DOMAIN_ROLLUPS

        # Fallback to non-enriched cards
        if not self.enriched_cards_dir.exists():
            self.enriched_cards_dir = clusters_dir / "doc_cards"

        self.final_dir.mkdir(parents=True, exist_ok=True)

    def load_all_incremental_clusters(self) -> list:
        """Load all clusters from incremental clustering."""
        clusters = []

        for cluster_file in sorted(self.incremental_dir.glob("*.json")):
            try:
                with open(cluster_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    bucket_key = data.get("bucket_key", cluster_file.stem)

                    for cluster in data.get("clusters", []):
                        cluster["source_bucket"] = bucket_key
                        cluster["source_file"] = cluster_file.name
                        clusters.append(cluster)
            except Exception as e:
                print(f"  WARNING: Failed to load {cluster_file}: {e}")

        return clusters

    def load_doc_card(self, doc_id: str) -> Optional[dict]:
        """Load a doc card."""
        path = self.enriched_cards_dir / f"{doc_id}.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def get_domain_rollup(self, domains: list) -> str:
        """Map domains to a rollup category."""
        if not domains:
            return "misc"

        for rollup, members in self.domain_rollups.items():
            for domain in domains:
                domain_lower = domain.lower()
                if domain_lower in members or any(m in domain_lower for m in members):
                    return rollup

        return "misc"

    def compute_cluster_signature(self, cluster: dict) -> dict:
        """Compute a signature for similarity comparison."""
        member_ids = cluster.get("member_doc_ids", [])
        tags = cluster.get("top_tags", {})
        domains = tags.get("domains", [])
        patterns = tags.get("patterns", [])
        frameworks = tags.get("frameworks", [])

        return {
            "cluster_name": cluster.get("cluster_name", "unknown"),
            "cluster_description": cluster.get("cluster_description", "")[:200],
            "member_doc_ids": member_ids,
            "member_count": len(member_ids),
            "is_singleton": cluster.get("singleton", False),
            "source_bucket": cluster.get("source_bucket", ""),
            "domains": domains,
            "patterns": patterns,
            "frameworks": frameworks,
            "trigger_phrases": cluster.get("trigger_phrases", [])[:10],
            "typical_outputs": cluster.get("typical_outputs", [])[:10],
            "domain_rollup": self.get_domain_rollup(domains),
        }

    def build_rollup_groups(self, signatures: list) -> list:
        """Group clusters by domain rollup."""
        rollup_groups = defaultdict(list)

        for sig in signatures:
            rollup = sig.get("domain_rollup", "misc")
            rollup_groups[rollup].append(sig)

        result = []
        for rollup, sigs in sorted(rollup_groups.items(), key=lambda x: -len(x[1])):
            total_docs = sum(s["member_count"] for s in sigs)
            all_domains = set()
            all_patterns = set()
            all_triggers = set()
            all_outputs = set()

            for s in sigs:
                all_domains.update(s.get("domains", []))
                all_patterns.update(s.get("patterns", []))
                all_triggers.update(s.get("trigger_phrases", []))
                all_outputs.update(s.get("typical_outputs", []))

            result.append({
                "rollup": rollup,
                "cluster_names": [s["cluster_name"] for s in sigs],
                "member_count": len(sigs),
                "total_docs": total_docs,
                "domains": sorted(all_domains),
                "patterns": sorted(all_patterns),
                "trigger_phrases": sorted(all_triggers)[:20],
                "typical_outputs": sorted(all_outputs)[:20],
            })

        return sorted(result, key=lambda x: -x["total_docs"])

    def build_rollup_prompt(self, group: dict, sig_map: dict) -> str:
        """Build prompt for AI to name and optionally split a rollup group."""
        cluster_details = []
        for name in group["cluster_names"][:15]:
            sig = sig_map.get(name, {})
            if sig:
                cluster_details.append({
                    "name": name,
                    "docs": sig.get("member_count", 0),
                    "description": sig.get("cluster_description", "")[:100],
                    "triggers": sig.get("trigger_phrases", [])[:3],
                })

        prompt = f"""You are consolidating development task clusters into Skills.

ROLLUP DOMAIN: {group['rollup']}
TOTAL CLUSTERS: {group['member_count']}
TOTAL DOCUMENTS: {group['total_docs']}

SAMPLE CLUSTERS:
{json.dumps(cluster_details, indent=2, ensure_ascii=False)}

AGGREGATE INFO:
- Domains: {group['domains'][:10]}
- Patterns: {group['patterns'][:10]}
- Trigger phrases: {group['trigger_phrases'][:10]}
- Output types: {group['typical_outputs'][:10]}

TASK: Create a unified Skill definition for this domain.

Consider:
1. Should this be ONE skill or split into 2-3 sub-skills?
2. Only split if there are CLEARLY distinct use cases
3. When in doubt, keep as ONE skill (fewer = better)

RESPOND WITH ONLY JSON:
{{
  "recommendation": "merge_all" | "split",
  "skills": [
    {{
      "skill_name": "kebab-case-name",
      "skill_description": "2-3 sentences: what this skill does and when to activate",
      "activation_triggers": ["trigger1", "trigger2", "trigger3"],
      "cluster_names": ["list of cluster names for this skill"],
      "estimated_doc_count": 10
    }}
  ],
  "rationale": "Brief explanation"
}}

If "merge_all", skills array has 1 item with ALL cluster_names.
If "split", skills array has 2-3 items with subsets.

JSON:"""

        return prompt

    def create_skill_cluster(self, skill_def: dict, group: dict, sig_map: dict) -> dict:
        """Create a final skill cluster from AI definition."""
        all_doc_ids = []
        all_domains = set()
        all_patterns = set()
        all_frameworks = set()
        all_triggers = set()
        all_outputs = set()
        source_buckets = set()

        for name in skill_def.get("cluster_names", []):
            if name in sig_map:
                sig = sig_map[name]
                all_doc_ids.extend(sig.get("member_doc_ids", []))
                all_domains.update(sig.get("domains", []))
                all_patterns.update(sig.get("patterns", []))
                all_frameworks.update(sig.get("frameworks", []))
                all_triggers.update(sig.get("trigger_phrases", []))
                all_outputs.update(sig.get("typical_outputs", []))
                source_buckets.add(sig.get("source_bucket", ""))

        all_doc_ids = sorted(set(all_doc_ids))

        return {
            "cluster_name": skill_def.get("skill_name", f"{group['rollup']}-skill"),
            "cluster_description": skill_def.get("skill_description", ""),
            "member_doc_ids": all_doc_ids,
            "member_count": len(all_doc_ids),
            "top_tags": {
                "domains": sorted(all_domains),
                "patterns": sorted(all_patterns),
                "frameworks": sorted(all_frameworks),
            },
            "trigger_phrases": skill_def.get("activation_triggers", []) + list(all_triggers)[:10],
            "typical_outputs": sorted(all_outputs)[:15],
            "source_clusters": skill_def.get("cluster_names", []),
            "source_buckets": sorted(source_buckets),
            "domain_rollup": group["rollup"],
            "created_at": datetime.now().isoformat(),
            "is_merged": True,
        }

    def run(self, dry_run: bool = False) -> dict:
        """Run the merge pipeline."""
        results = {
            "input_clusters": 0,
            "output_clusters": 0,
            "merge_decisions": [],
        }

        print("\n  Loading incremental clusters...")
        clusters = self.load_all_incremental_clusters()
        results["input_clusters"] = len(clusters)
        print(f"  Loaded {len(clusters)} clusters")

        print("\n  Computing signatures...")
        signatures = [self.compute_cluster_signature(c) for c in clusters]
        sig_map = {s["cluster_name"]: s for s in signatures}

        print("\n  Building rollup groups...")
        rollup_groups = self.build_rollup_groups(signatures)
        print(f"  Created {len(rollup_groups)} rollup groups:")
        for group in rollup_groups:
            print(f"    {group['rollup']}: {group['member_count']} clusters, {group['total_docs']} docs")

        if dry_run:
            print("\n  DRY RUN - skipping AI merge decisions")
            return results

        # Process each rollup group
        print("\n  Processing rollup groups with AI...")
        final_clusters = []
        merged_names = set()

        for i, group in enumerate(rollup_groups, 1):
            print(f"\n  [{i}/{len(rollup_groups)}] {group['rollup']} ({group['total_docs']} docs)")

            prompt = self.build_rollup_prompt(group, sig_map)

            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1000,
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

                ai_result = json.loads(response_text)
                recommendation = ai_result.get("recommendation", "merge_all")
                skills = ai_result.get("skills", [])

                print(f"    AI recommends: {recommendation}")

                # If merge_all with 1 skill, use all cluster names
                if recommendation == "merge_all" and len(skills) == 1:
                    skills[0]["cluster_names"] = group["cluster_names"]

                for skill_def in skills:
                    if not skill_def.get("cluster_names"):
                        skill_def["cluster_names"] = group["cluster_names"]

                    cluster = self.create_skill_cluster(skill_def, group, sig_map)
                    final_clusters.append(cluster)
                    merged_names.update(skill_def.get("cluster_names", []))

                    print(f"    -> {cluster['cluster_name']} ({cluster['member_count']} docs)")

                results["merge_decisions"].append({
                    "rollup": group["rollup"],
                    "source_clusters": group["cluster_names"],
                    "recommendation": recommendation,
                    "skills_created": [s.get("skill_name") for s in skills],
                    "rationale": ai_result.get("rationale"),
                })

            except Exception as e:
                print(f"    ERROR: {e}")
                # Fallback: create one cluster per rollup
                fallback_skill = {
                    "skill_name": f"{group['rollup']}-skill",
                    "skill_description": f"Skills related to {group['rollup']}.",
                    "activation_triggers": group.get("trigger_phrases", [])[:5],
                    "cluster_names": group["cluster_names"],
                }
                cluster = self.create_skill_cluster(fallback_skill, group, sig_map)
                final_clusters.append(cluster)
                merged_names.update(group["cluster_names"])

        # Save final clusters
        print("\n  Saving final clusters...")
        for cluster in final_clusters:
            safe_name = cluster["cluster_name"].replace("/", "-").replace("\\", "-")
            path = self.final_dir / f"{safe_name}.json"
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cluster, f, indent=2, ensure_ascii=False)

        # Create doc-to-cluster map
        doc_to_cluster = {}
        for cluster in final_clusters:
            for doc_id in cluster.get("member_doc_ids", []):
                doc_to_cluster[doc_id] = cluster["cluster_name"]

        map_path = self.clusters_dir / "doc_to_cluster_map_final.json"
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump(doc_to_cluster, f, indent=2, ensure_ascii=False)

        # Save summary
        results["output_clusters"] = len(final_clusters)
        summary = {
            "generated_at": datetime.now().isoformat(),
            "statistics": {
                "input_clusters": results["input_clusters"],
                "output_clusters": results["output_clusters"],
                "reduction_percent": (1 - results["output_clusters"] / max(results["input_clusters"], 1)) * 100,
            },
            "merge_decisions": results["merge_decisions"],
        }

        summary_path = self.clusters_dir / "_merge_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Phase C.4: Cross-Bucket Cluster Merging"
    )

    defaults = get_default_paths()

    parser.add_argument("--api-key", type=str, help="Anthropic API key")
    parser.add_argument("--clusters-dir", type=str, default=str(defaults["clusters_dir"]))
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-20250514")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: No API key. Use --api-key or set ANTHROPIC_API_KEY")
        exit(1)

    print("=" * 60)
    print("Phase C.4: Cross-Bucket Cluster Merging")
    print("=" * 60)

    pipeline = ClusterMergePipeline(
        clusters_dir=Path(args.clusters_dir),
        api_key=api_key or "",
        model=args.model,
    )

    results = pipeline.run(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("Merge Summary")
    print("=" * 60)
    print(f"  Input clusters: {results['input_clusters']}")
    print(f"  Output clusters: {results['output_clusters']}")

    if results['input_clusters'] > 0:
        reduction = (1 - results['output_clusters'] / results['input_clusters']) * 100
        print(f"  Reduction: {reduction:.1f}%")

    print("\n" + "=" * 60)
    print("Phase C.4 Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
