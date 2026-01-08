"""
Phase C.2: AI Tag Enrichment

This module uses AI to enrich doc cards that have missing domain/pattern tags.
It reduces the "unknown__unknown" bucket by inferring appropriate tags from
the document content.

Usage:
    python phase_c_tag_enrichment.py --api-key YOUR_KEY
    python phase_c_tag_enrichment.py  # Uses ANTHROPIC_API_KEY env var
"""

import json
import os
import re
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
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


# Default vocabularies - users should customize these for their domain
DEFAULT_DOMAIN_VOCABULARY = [
    "data-analysis", "data-processing", "data-validation", "data-profiling",
    "pdf-processing", "pdf-extraction", "document-processing", "text-extraction",
    "api-development", "backend", "frontend", "ui", "dashboard",
    "deployment", "infrastructure", "devops", "ci-cd",
    "ai-integration", "llm", "prompt-engineering", "machine-learning",
    "database", "sql", "nosql", "data-modeling",
    "testing", "qa", "automation", "scripting",
    "logging", "monitoring", "observability", "error-handling",
    "authentication", "security", "authorization",
    "file-processing", "image-processing", "audio-processing", "video-processing",
    "web-scraping", "etl", "data-pipeline", "workflow-automation",
    "cli-tools", "utilities", "configuration", "settings",
]

DEFAULT_PATTERN_VOCABULARY = [
    "feature-implementation", "bug-fix", "refactor", "optimization",
    "integration", "migration", "upgrade", "configuration",
    "extraction", "transformation", "loading", "etl",
    "api-wrapper", "client-library", "sdk-integration",
    "ui-component", "form-handling", "data-visualization",
    "error-handling", "retry-logic", "fallback",
    "caching", "performance", "scaling",
    "validation", "sanitization", "normalization",
    "report-generation", "export", "import",
    "scheduled-task", "batch-processing", "async-processing",
    "template-creation", "code-generation", "scaffolding",
]


class TagEnrichmentPipeline:
    """AI-assisted tag enrichment for doc cards with missing tags."""

    def __init__(
        self,
        clusters_dir: Path,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        domain_vocab: Optional[list] = None,
        pattern_vocab: Optional[list] = None,
    ):
        self.clusters_dir = clusters_dir
        self.doc_cards_dir = clusters_dir / "doc_cards"
        self.enriched_cards_dir = clusters_dir / "doc_cards_enriched"
        self.enriched_buckets_dir = clusters_dir / "buckets_enriched"
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.domain_vocab = domain_vocab or DEFAULT_DOMAIN_VOCABULARY
        self.pattern_vocab = pattern_vocab or DEFAULT_PATTERN_VOCABULARY

        # Ensure output directories exist
        self.enriched_cards_dir.mkdir(parents=True, exist_ok=True)
        self.enriched_buckets_dir.mkdir(parents=True, exist_ok=True)

    def load_doc_card(self, doc_id: str) -> Optional[dict]:
        """Load a doc card by ID."""
        path = self.doc_cards_dir / f"{doc_id}.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def needs_enrichment(self, card: dict) -> bool:
        """Check if a card needs tag enrichment."""
        tags = card.get('tags', {})
        domains = tags.get('domains', [])
        patterns = tags.get('patterns', [])

        # Needs enrichment if both are empty or contain only 'unknown'
        has_valid_domain = any(d and d != 'unknown' for d in domains)
        has_valid_pattern = any(p and p != 'unknown' for p in patterns)

        return not has_valid_domain or not has_valid_pattern

    def build_enrichment_prompt(self, card: dict) -> str:
        """Build the prompt for AI tag enrichment."""
        prompt = f"""Analyze this document card and suggest appropriate domain and pattern tags.

DOCUMENT CARD:
{json.dumps(card, indent=2, ensure_ascii=False)}

ALLOWED DOMAIN VOCABULARY (use ONLY these terms):
{', '.join(self.domain_vocab)}

ALLOWED PATTERN VOCABULARY (use ONLY these terms):
{', '.join(self.pattern_vocab)}

TASK: Infer 1-3 domains and 1-3 patterns based on:
- The trigger/what_triggered text
- The workflow steps
- The artifacts produced
- Any issues encountered
- The existing tags (frameworks, languages, tools)

RESPOND WITH ONLY THIS JSON FORMAT:
{{
    "domains": ["domain1", "domain2"],
    "patterns": ["pattern1", "pattern2"],
    "confidence": 0.8,
    "reasoning": "Brief explanation of why these tags were chosen"
}}

Use ONLY terms from the allowed vocabularies. If nothing matches well, pick the closest term.
Do not invent new terms. Respond with ONLY the JSON, no markdown formatting."""

        return prompt

    def enrich_card(self, card: dict) -> dict:
        """Enrich a single doc card with AI-inferred tags."""
        prompt = self.build_enrichment_prompt(card)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
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

            enrichment = json.loads(response_text)

            # Validate and apply enrichment
            new_domains = [d for d in enrichment.get('domains', []) if d in self.domain_vocab]
            new_patterns = [p for p in enrichment.get('patterns', []) if p in self.pattern_vocab]

            # Update card
            enriched_card = dict(card)
            enriched_card['tags']['domains'] = new_domains if new_domains else card['tags'].get('domains', [])
            enriched_card['tags']['patterns'] = new_patterns if new_patterns else card['tags'].get('patterns', [])

            # Update bucket key
            primary_domain = enriched_card['tags']['domains'][0] if enriched_card['tags']['domains'] else 'unknown'
            primary_pattern = enriched_card['tags']['patterns'][0] if enriched_card['tags']['patterns'] else 'unknown'
            enriched_card['bucket_key'] = f"{primary_domain}__{primary_pattern}"

            # Add enrichment metadata
            enriched_card['_enrichment'] = {
                "enriched": True,
                "confidence": enrichment.get('confidence', 0),
                "reasoning": enrichment.get('reasoning', ''),
                "original_bucket_key": card.get('bucket_key', 'unknown__unknown'),
            }

            return enriched_card

        except Exception as e:
            print(f"  ERROR enriching {card.get('doc_id')}: {e}")
            # Return original card with enrichment flag
            enriched_card = dict(card)
            enriched_card['_enrichment'] = {
                "enriched": False,
                "error": str(e),
            }
            return enriched_card

    def run(self, max_cards: Optional[int] = None) -> dict:
        """Run the enrichment pipeline."""
        results = {
            "total_cards": 0,
            "needs_enrichment": 0,
            "enriched": 0,
            "failed": 0,
            "bucket_changes": [],
        }

        # Load all doc cards
        card_files = list(self.doc_cards_dir.glob("*.json"))
        results["total_cards"] = len(card_files)

        # Process cards
        cards_to_enrich = []
        all_cards = []

        for card_file in card_files:
            with open(card_file, 'r', encoding='utf-8') as f:
                card = json.load(f)

            if self.needs_enrichment(card):
                cards_to_enrich.append(card)
            all_cards.append(card)

        results["needs_enrichment"] = len(cards_to_enrich)

        if max_cards:
            cards_to_enrich = cards_to_enrich[:max_cards]

        print(f"\n  Found {results['needs_enrichment']} cards needing enrichment")
        print(f"  Processing {len(cards_to_enrich)} cards...")

        # Enrich cards
        enriched_cards = {}
        for i, card in enumerate(cards_to_enrich, 1):
            print(f"  [{i}/{len(cards_to_enrich)}] Enriching {card['doc_id'][:40]}...")
            enriched = self.enrich_card(card)
            enriched_cards[card['doc_id']] = enriched

            if enriched.get('_enrichment', {}).get('enriched'):
                results["enriched"] += 1
                old_key = card.get('bucket_key', 'unknown__unknown')
                new_key = enriched.get('bucket_key', 'unknown__unknown')
                if old_key != new_key:
                    results["bucket_changes"].append({
                        "doc_id": card['doc_id'],
                        "old_bucket": old_key,
                        "new_bucket": new_key,
                    })
            else:
                results["failed"] += 1

        # Save enriched cards (all cards, updated where enriched)
        print(f"\n  Saving enriched cards...")
        for card in all_cards:
            doc_id = card['doc_id']
            if doc_id in enriched_cards:
                save_card = enriched_cards[doc_id]
            else:
                save_card = card

            card_path = self.enriched_cards_dir / f"{doc_id}.json"
            with open(card_path, 'w', encoding='utf-8') as f:
                json.dump(save_card, f, indent=2, ensure_ascii=False)

        # Regenerate buckets with enriched cards
        print(f"  Regenerating buckets...")
        self._regenerate_buckets()

        # Save summary
        summary = {
            "generated_at": datetime.now().isoformat(),
            "results": results,
        }
        summary_path = self.clusters_dir / "_enrichment_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return results

    def _regenerate_buckets(self):
        """Regenerate buckets from enriched cards."""
        buckets = defaultdict(lambda: {
            "doc_ids": [],
            "primary_domain": None,
            "primary_pattern": None,
            "doc_count": 0,
        })

        for card_file in self.enriched_cards_dir.glob("*.json"):
            with open(card_file, 'r', encoding='utf-8') as f:
                card = json.load(f)

            bucket_key = card.get('bucket_key', 'unknown__unknown')
            parts = bucket_key.split('__')

            bucket = buckets[bucket_key]
            bucket["doc_ids"].append(card["doc_id"])
            bucket["primary_domain"] = parts[0] if len(parts) > 0 else "unknown"
            bucket["primary_pattern"] = parts[1] if len(parts) > 1 else "unknown"
            bucket["doc_count"] = len(bucket["doc_ids"])

        # Save bucket files
        for bucket_key, bucket_data in buckets.items():
            safe_key = bucket_key.replace('/', '-').replace('\\', '-')
            bucket_path = self.enriched_buckets_dir / f"{safe_key}.json"
            with open(bucket_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "bucket_key": bucket_key,
                    **bucket_data
                }, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Phase C.2: AI Tag Enrichment"
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
        help="Clusters directory containing doc_cards"
    )

    parser.add_argument(
        "--max-cards",
        type=int,
        help="Maximum number of cards to enrich (for testing)"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Model to use for enrichment"
    )

    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No API key provided. Use --api-key or set ANTHROPIC_API_KEY")
        exit(1)

    clusters_dir = Path(args.clusters_dir)

    print("=" * 60)
    print("Phase C.2: AI Tag Enrichment")
    print("=" * 60)

    pipeline = TagEnrichmentPipeline(
        clusters_dir=clusters_dir,
        api_key=api_key,
        model=args.model,
    )

    results = pipeline.run(max_cards=args.max_cards)

    print("\n" + "=" * 60)
    print("Enrichment Summary")
    print("=" * 60)
    print(f"  Total cards: {results['total_cards']}")
    print(f"  Needed enrichment: {results['needs_enrichment']}")
    print(f"  Successfully enriched: {results['enriched']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Bucket changes: {len(results['bucket_changes'])}")

    if results['bucket_changes']:
        print(f"\n  Sample bucket changes:")
        for change in results['bucket_changes'][:5]:
            print(f"    {change['doc_id'][:30]}: {change['old_bucket']} -> {change['new_bucket']}")

    print("\n" + "=" * 60)
    print("Phase C.2 Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
