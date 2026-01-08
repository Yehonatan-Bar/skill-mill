"""
Phase C: Document Cards and Coarse Bucketing

This module implements Steps C.0 and C.1 of the clustering pipeline:
- C.0: Create compact "doc cards" from extraction JSONs
- C.1: Group doc cards into coarse buckets using primary_domain__primary_pattern keys

The bucketing is deterministic (no AI) and creates the foundation for later
AI-assisted clustering and merging.

Usage:
    python phase_c_clustering.py
    python phase_c_clustering.py --input-dir extractions --output-dir clusters
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional, Any

# Import config if available
try:
    from config import PipelineConfig
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False


def get_default_paths():
    """Get default paths based on working directory."""
    cwd = Path.cwd()
    return {
        "extractions_dir": cwd / "extractions",
        "clusters_dir": cwd / "clusters",
    }


class DocCardGenerator:
    """Generates compact doc cards from extraction JSONs."""

    def __init__(self, extractions_dir: Path, output_dir: Path):
        self.extractions_dir = extractions_dir
        self.doc_cards_dir = output_dir / "doc_cards"
        self.doc_cards_dir.mkdir(parents=True, exist_ok=True)

    def load_extraction(self, path: Path) -> Optional[dict]:
        """Load an extraction JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  WARNING: Failed to load {path}: {e}")
            return None

    def generate_card(self, extraction: dict) -> dict:
        """Generate a compact doc card from an extraction."""
        doc_id = extraction.get('doc_id', 'unknown')

        # Extract scores
        skill_assessment = extraction.get('skill_assessment', {})
        scores = {
            "reusability_total": skill_assessment.get('reusability_score'),
            "frequency_score": skill_assessment.get('frequency_score'),
            "consistency_score": skill_assessment.get('consistency_score'),
            "complexity_score": skill_assessment.get('complexity_score'),
            "codifiability_score": skill_assessment.get('codifiability_score'),
            "toolability_score": skill_assessment.get('toolability_score'),
            "extraction_priority": skill_assessment.get('extraction_priority'),
        }

        # Normalize tags
        raw_tags = extraction.get('tags', {})
        tags = {
            "domains": self._normalize_tags(raw_tags.get('domains', [])),
            "patterns": self._normalize_tags(raw_tags.get('patterns', [])),
            "frameworks": self._normalize_tags(raw_tags.get('frameworks', [])),
            "languages": self._normalize_tags(raw_tags.get('languages', [])),
            "tools": self._normalize_tags(raw_tags.get('tools', [])),
        }

        # Extract trigger info
        trigger_data = extraction.get('trigger', {})
        trigger = {
            "what_triggered": trigger_data.get('what_triggered', ''),
            "keywords": trigger_data.get('keywords_phrases', [])[:10],
            "draft_trigger": trigger_data.get('draft_skill_trigger', ''),
        }

        # Extract workflow steps (top 5)
        workflow = extraction.get('workflow', {})
        steps = workflow.get('high_level_steps', [])[:5]

        # Extract artifact names
        outputs = extraction.get('outputs_produced', {})
        artifacts = [a.get('name', '') for a in outputs.get('artifacts', [])[:5]]

        # Extract issue titles
        issues_data = extraction.get('issues_and_fixes', {})
        issues = [i.get('issue', '')[:80] for i in issues_data.get('items', [])[:5]]

        # Create bucket key
        primary_domain = tags['domains'][0] if tags['domains'] else 'unknown'
        primary_pattern = tags['patterns'][0] if tags['patterns'] else 'unknown'
        bucket_key = f"{primary_domain}__{primary_pattern}"

        return {
            "doc_id": doc_id,
            "format_detected": extraction.get('format_detected', 'unknown'),
            "scores": scores,
            "tags": tags,
            "trigger": trigger,
            "workflow_steps": steps,
            "artifacts": artifacts,
            "issues": issues,
            "bucket_key": bucket_key,
            "created_at": datetime.now().isoformat(),
        }

    def _normalize_tags(self, tags: list) -> list:
        """Normalize a list of tags."""
        normalized = []
        seen = set()
        for tag in tags:
            if not tag:
                continue
            tag_lower = tag.lower().strip().replace(' ', '-')
            if tag_lower not in seen and tag_lower != 'unknown':
                seen.add(tag_lower)
                normalized.append(tag_lower)
        return normalized

    def process_all(self) -> dict:
        """Process all extractions and generate doc cards."""
        results = {
            "processed": 0,
            "failed": 0,
            "cards": [],
        }

        for ext_file in sorted(self.extractions_dir.glob("*.json")):
            if ext_file.name.startswith('_'):
                continue  # Skip summary files

            extraction = self.load_extraction(ext_file)
            if not extraction:
                results["failed"] += 1
                continue

            card = self.generate_card(extraction)

            # Save card
            card_path = self.doc_cards_dir / f"{card['doc_id']}.json"
            with open(card_path, 'w', encoding='utf-8') as f:
                json.dump(card, f, indent=2, ensure_ascii=False)

            results["cards"].append(card)
            results["processed"] += 1

        return results


class BucketGenerator:
    """Groups doc cards into coarse buckets."""

    def __init__(self, doc_cards_dir: Path, output_dir: Path):
        self.doc_cards_dir = doc_cards_dir
        self.buckets_dir = output_dir / "buckets"
        self.buckets_dir.mkdir(parents=True, exist_ok=True)
        self.clusters_dir = output_dir

    def load_doc_cards(self) -> list[dict]:
        """Load all doc cards."""
        cards = []
        for card_file in sorted(self.doc_cards_dir.glob("*.json")):
            try:
                with open(card_file, 'r', encoding='utf-8') as f:
                    cards.append(json.load(f))
            except Exception as e:
                print(f"  WARNING: Failed to load {card_file}: {e}")
        return cards

    def create_buckets(self, cards: list[dict]) -> dict:
        """Create coarse buckets from doc cards."""
        buckets = defaultdict(lambda: {
            "doc_ids": [],
            "primary_domain": None,
            "primary_pattern": None,
            "doc_count": 0,
        })

        for card in cards:
            bucket_key = card.get('bucket_key', 'unknown__unknown')
            parts = bucket_key.split('__')

            bucket = buckets[bucket_key]
            bucket["doc_ids"].append(card["doc_id"])
            bucket["primary_domain"] = parts[0] if len(parts) > 0 else "unknown"
            bucket["primary_pattern"] = parts[1] if len(parts) > 1 else "unknown"
            bucket["doc_count"] = len(bucket["doc_ids"])

        return dict(buckets)

    def save_buckets(self, buckets: dict) -> dict:
        """Save bucket files and summary."""
        # Save individual bucket files
        for bucket_key, bucket_data in buckets.items():
            safe_key = bucket_key.replace('/', '-').replace('\\', '-')
            bucket_path = self.buckets_dir / f"{safe_key}.json"
            with open(bucket_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "bucket_key": bucket_key,
                    **bucket_data
                }, f, indent=2, ensure_ascii=False)

        # Calculate statistics
        bucket_sizes = [b["doc_count"] for b in buckets.values()]
        unknown_count = buckets.get('unknown__unknown', {}).get('doc_count', 0)

        stats = {
            "total_buckets": len(buckets),
            "total_documents": sum(bucket_sizes),
            "avg_bucket_size": sum(bucket_sizes) / len(buckets) if buckets else 0,
            "max_bucket_size": max(bucket_sizes) if bucket_sizes else 0,
            "min_bucket_size": min(bucket_sizes) if bucket_sizes else 0,
            "singleton_buckets": sum(1 for s in bucket_sizes if s == 1),
            "unknown_bucket_docs": unknown_count,
        }

        # Generate summary
        summary = {
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "buckets": buckets,
        }

        summary_path = self.clusters_dir / "_clustering_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return summary


def main():
    parser = argparse.ArgumentParser(
        description="Phase C: Document Cards and Coarse Bucketing"
    )

    defaults = get_default_paths()

    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(defaults["extractions_dir"]),
        help="Directory containing extraction JSONs"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(defaults["clusters_dir"]),
        help="Output directory for clusters"
    )

    args = parser.parse_args()

    extractions_dir = Path(args.input_dir)
    clusters_dir = Path(args.output_dir)

    print("=" * 60)
    print("Phase C: Document Cards and Coarse Bucketing")
    print("=" * 60)

    # Step C.0: Generate doc cards
    print("\nStep C.0: Generating doc cards...")
    card_generator = DocCardGenerator(extractions_dir, clusters_dir)
    card_results = card_generator.process_all()

    print(f"  Processed: {card_results['processed']}")
    print(f"  Failed: {card_results['failed']}")
    print(f"  Output: {card_generator.doc_cards_dir}")

    # Step C.1: Create coarse buckets
    print("\nStep C.1: Creating coarse buckets...")
    bucket_generator = BucketGenerator(card_generator.doc_cards_dir, clusters_dir)
    cards = bucket_generator.load_doc_cards()
    buckets = bucket_generator.create_buckets(cards)
    summary = bucket_generator.save_buckets(buckets)

    stats = summary["statistics"]
    print(f"\n  Statistics:")
    print(f"    Total buckets: {stats['total_buckets']}")
    print(f"    Total documents: {stats['total_documents']}")
    print(f"    Avg bucket size: {stats['avg_bucket_size']:.1f}")
    print(f"    Singleton buckets: {stats['singleton_buckets']}")
    print(f"    Unknown bucket docs: {stats['unknown_bucket_docs']}")

    # Show top buckets
    sorted_buckets = sorted(buckets.items(), key=lambda x: -x[1]["doc_count"])
    print(f"\n  Top 10 buckets:")
    for bucket_key, data in sorted_buckets[:10]:
        print(f"    {bucket_key}: {data['doc_count']} docs")

    print("\n" + "=" * 60)
    print("Phase C.0-C.1 Complete!")
    print("=" * 60)
    print(f"  Doc cards: {card_generator.doc_cards_dir}")
    print(f"  Buckets: {bucket_generator.buckets_dir}")
    print(f"  Summary: {clusters_dir / '_clustering_summary.json'}")

    # Return for programmatic use
    return {
        "cards": card_results,
        "buckets": summary,
    }


if __name__ == "__main__":
    main()
