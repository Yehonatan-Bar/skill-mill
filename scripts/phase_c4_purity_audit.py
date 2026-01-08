"""
Phase C.4: Cluster Purity Audit

Analyzes large clusters for internal consistency and recommends splits
where documents have distinctly different triggers, outputs, or workflows.

This is typically run AFTER the merge step to verify cluster quality.

Usage:
    python phase_c4_purity_audit.py --api-key YOUR_KEY
    python phase_c4_purity_audit.py --min-cluster-size 15
    python phase_c4_purity_audit.py --cluster pdf-processing
"""

import json
import os
import re
import random
import argparse
from pathlib import Path
from datetime import datetime
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


class PurityAuditPipeline:
    """Audits cluster purity and recommends splits."""

    def __init__(
        self,
        clusters_dir: Path,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        min_cluster_size: int = 10,
    ):
        self.clusters_dir = clusters_dir
        self.final_dir = clusters_dir / "clusters_final"
        self.enriched_cards_dir = clusters_dir / "doc_cards_enriched"
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.min_cluster_size = min_cluster_size

        if not self.enriched_cards_dir.exists():
            self.enriched_cards_dir = clusters_dir / "doc_cards"

    def load_cluster(self, path: Path) -> Optional[dict]:
        """Load a cluster manifest."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  WARNING: Failed to load {path}: {e}")
            return None

    def load_doc_card(self, doc_id: str) -> Optional[dict]:
        """Load a doc card."""
        path = self.enriched_cards_dir / f"{doc_id}.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def sample_doc_cards(self, cluster: dict, sample_size: int = 10) -> list:
        """Sample diverse doc cards from a cluster."""
        doc_ids = cluster.get("member_doc_ids", [])
        cards = []

        for doc_id in doc_ids:
            card = self.load_doc_card(doc_id)
            if card:
                cards.append(card)

        if len(cards) <= sample_size:
            return cards

        # Ensure diversity in sample
        high_priority = []
        with_issues = []
        with_artifacts = []
        others = []

        for card in cards:
            scores = card.get("scores", {})
            priority = scores.get("extraction_priority", "")

            if priority == "high":
                high_priority.append(card)
            elif card.get("issues"):
                with_issues.append(card)
            elif card.get("artifacts"):
                with_artifacts.append(card)
            else:
                others.append(card)

        sample = []
        sample.extend(high_priority[:3])
        sample.extend(with_issues[:2])
        sample.extend(with_artifacts[:2])

        remaining = sample_size - len(sample)
        if remaining > 0:
            available = [c for c in cards if c not in sample]
            random.shuffle(available)
            sample.extend(available[:remaining])

        return sample[:sample_size]

    def format_card_for_prompt(self, card: dict) -> str:
        """Format a doc card for the audit prompt."""
        lines = []

        lines.append(f"DOC_ID: {card.get('doc_id', 'unknown')}")

        trigger = card.get("trigger", {})
        if trigger.get("what_triggered"):
            text = trigger["what_triggered"][:300]
            lines.append(f"TRIGGER: {text}")
        if trigger.get("keywords"):
            lines.append(f"KEYWORDS: {', '.join(trigger['keywords'][:5])}")

        tags = card.get("tags", {})
        if tags.get("domains"):
            lines.append(f"DOMAINS: {', '.join(tags['domains'][:5])}")
        if tags.get("patterns"):
            lines.append(f"PATTERNS: {', '.join(tags['patterns'][:5])}")

        steps = card.get("workflow_steps", [])
        if steps:
            lines.append(f"WORKFLOW: {' -> '.join(steps[:3])}")

        artifacts = card.get("artifacts", [])
        if artifacts:
            lines.append(f"ARTIFACTS: {', '.join(artifacts[:3])}")

        issues = card.get("issues", [])
        if issues:
            lines.append(f"ISSUES: {', '.join(issues[:3])}")

        return "\n".join(lines)

    def build_audit_prompt(self, cluster: dict, sample_cards: list) -> str:
        """Build the purity audit prompt."""
        cluster_name = cluster.get("cluster_name", "unknown")
        cluster_desc = cluster.get("cluster_description", "")
        member_count = cluster.get("member_count", len(sample_cards))

        cards_text = "\n\n---\n\n".join([
            self.format_card_for_prompt(card) for card in sample_cards
        ])

        prompt = f"""Analyze this cluster for purity. Determine if it should be SPLIT.

CLUSTER: {cluster_name}
DESCRIPTION: {cluster_desc}
TOTAL DOCS: {member_count}
SAMPLE SIZE: {len(sample_cards)}

SAMPLE DOCUMENTS:
{cards_text}

SPLIT CRITERIA - Split if ANY are true:
1. TRIGGERS differ significantly (e.g., "extract PDF" vs "generate HTML")
2. OUTPUTS differ (e.g., Python scripts vs HTML templates)
3. WORKFLOWS differ (e.g., ETL vs UI building vs deployment)
4. Contains multiple distinct "end products"

DO NOT SPLIT if:
- Documents are different implementations of the same pattern
- Differences are only in complexity (simple vs complex)
- Bug fixes vs features for the same system

RESPOND WITH ONLY JSON:
{{
    "is_pure": boolean,
    "sub_topics": [
        {{
            "name": "short-name",
            "description": "1-2 sentences",
            "distinguishing_triggers": ["trigger1", "trigger2"],
            "distinguishing_outputs": ["output1", "output2"],
            "doc_ids": ["doc_ids from sample"]
        }}
    ],
    "recommendation": "keep_as_is" or "split",
    "split_into": [
        {{
            "skill_name": "kebab-case",
            "description": "2-3 sentences",
            "doc_ids_from_sample": ["doc_ids"]
        }}
    ],
    "confidence": 0.0-1.0,
    "reasoning": "explanation"
}}

If is_pure=true, split_into should be empty.
If recommending split, provide 2-4 distinct skills."""

        return prompt

    def audit_cluster(self, cluster: dict, sample_cards: list) -> dict:
        """Run the purity audit on a cluster."""
        prompt = self.build_audit_prompt(cluster, sample_cards)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
                response_text = re.sub(r'\s*```$', '', response_text)

            return json.loads(response_text)

        except Exception as e:
            print(f"    ERROR: {e}")
            return {
                "is_pure": True,
                "sub_topics": [],
                "recommendation": "keep_as_is",
                "split_into": [],
                "confidence": 0.0,
                "reasoning": f"Error: {e}"
            }

    def run(self, cluster_name: Optional[str] = None, dry_run: bool = False) -> dict:
        """Run the purity audit pipeline."""
        results = {
            "clusters_audited": [],
            "splits_recommended": [],
            "clusters_kept": [],
        }

        # Find clusters to audit
        cluster_files = list(self.final_dir.glob("*.json"))
        clusters_to_audit = []

        for cf in cluster_files:
            cluster = self.load_cluster(cf)
            if not cluster:
                continue

            name = cluster.get("cluster_name", cf.stem)
            count = cluster.get("member_count", 0)

            if cluster_name:
                if name == cluster_name:
                    clusters_to_audit.append((cf, cluster))
            elif count >= self.min_cluster_size:
                clusters_to_audit.append((cf, cluster))

        print(f"\n  Found {len(clusters_to_audit)} clusters to audit (>= {self.min_cluster_size} docs)")

        if not clusters_to_audit:
            return results

        for i, (cf, cluster) in enumerate(clusters_to_audit, 1):
            name = cluster.get("cluster_name", cf.stem)
            count = cluster.get("member_count", 0)

            print(f"\n  [{i}/{len(clusters_to_audit)}] Auditing {name} ({count} docs)")

            sample_size = min(12, max(8, count // 4))
            sample_cards = self.sample_doc_cards(cluster, sample_size)
            print(f"    Sampled {len(sample_cards)} docs")

            if dry_run:
                results["clusters_audited"].append({
                    "cluster_name": name,
                    "member_count": count,
                    "dry_run": True
                })
                continue

            audit_result = self.audit_cluster(cluster, sample_cards)

            results["clusters_audited"].append({
                "cluster_name": name,
                "member_count": count,
                "is_pure": audit_result.get("is_pure", True),
                "recommendation": audit_result.get("recommendation", "keep_as_is"),
                "confidence": audit_result.get("confidence", 0.0),
            })

            if audit_result.get("recommendation") == "split":
                splits = audit_result.get("split_into", [])
                print(f"    SPLIT recommended into {len(splits)} skills")

                results["splits_recommended"].append({
                    "original_cluster": name,
                    "new_skills": splits,
                    "confidence": audit_result.get("confidence", 0.0),
                    "reasoning": audit_result.get("reasoning", ""),
                })
            else:
                print(f"    KEEP as-is (confidence: {audit_result.get('confidence', 0):.2f})")
                results["clusters_kept"].append(name)

        # Save results
        output_path = self.clusters_dir / "_c4_purity_audit.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "min_cluster_size": self.min_cluster_size,
                **results
            }, f, indent=2, ensure_ascii=False)

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Phase C.4: Cluster Purity Audit"
    )

    defaults = get_default_paths()

    parser.add_argument("--api-key", type=str, help="Anthropic API key")
    parser.add_argument("--clusters-dir", type=str, default=str(defaults["clusters_dir"]))
    parser.add_argument("--min-cluster-size", type=int, default=10)
    parser.add_argument("--cluster", type=str, help="Audit specific cluster")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-20250514")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: No API key")
        exit(1)

    print("=" * 60)
    print("Phase C.4: Cluster Purity Audit")
    print("=" * 60)

    pipeline = PurityAuditPipeline(
        clusters_dir=Path(args.clusters_dir),
        api_key=api_key or "",
        model=args.model,
        min_cluster_size=args.min_cluster_size,
    )

    results = pipeline.run(cluster_name=args.cluster, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("Audit Summary")
    print("=" * 60)
    print(f"  Clusters audited: {len(results['clusters_audited'])}")
    print(f"  Splits recommended: {len(results['splits_recommended'])}")
    print(f"  Clusters kept: {len(results['clusters_kept'])}")

    print("\n" + "=" * 60)
    print("Phase C.4 Purity Audit Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
