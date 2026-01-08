"""
Phase D: Skill Synthesis Pipeline

Generates SKILL.md and supporting files from cluster representatives.
Uses AI to synthesize procedural skills from extraction JSONs.

Usage:
    python phase_d_skill_synthesis.py --api-key YOUR_KEY
    python phase_d_skill_synthesis.py --cluster data-analysis
    python phase_d_skill_synthesis.py --max-clusters 3  # Test mode
    python phase_d_skill_synthesis.py --dry-run         # Preview prompts
"""

import json
import os
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

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
        "extractions_dir": cwd / "extractions",
        "skills_output_dir": cwd / "skills_out",
    }


def load_json(path: Path) -> Optional[dict]:
    """Load JSON file safely."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARNING: Failed to load {path}: {e}")
        return None


class SkillSynthesisPipeline:
    """Generates skills from cluster representatives."""

    def __init__(
        self,
        clusters_dir: Path,
        extractions_dir: Path,
        output_dir: Path,
        api_key: str,
        model: str = "claude-opus-4-5-20251101",
    ):
        self.clusters_dir = clusters_dir
        self.final_dir = clusters_dir / "clusters_final"
        self.representatives_dir = clusters_dir / "representatives"
        self.extractions_dir = extractions_dir
        self.output_dir = output_dir
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_cluster_data(self, cluster_id: str) -> dict:
        """Load cluster manifest, representatives, and extraction JSONs."""
        # Load cluster manifest
        manifest_path = self.final_dir / f"{cluster_id}.json"
        manifest = load_json(manifest_path)
        if not manifest:
            raise ValueError(f"Cluster not found: {manifest_path}")

        # Load representatives
        reps_path = self.representatives_dir / f"{cluster_id}.json"
        reps_data = load_json(reps_path)
        if not reps_data:
            raise ValueError(f"Representatives not found: {reps_path}")

        # Load extractions
        extractions = []
        for doc_id in reps_data.get("representative_doc_ids", []):
            ext_path = self.extractions_dir / f"{doc_id}.json"
            extraction = load_json(ext_path)
            if extraction:
                extractions.append(extraction)

        return {
            "cluster_id": cluster_id,
            "manifest": manifest,
            "representatives": reps_data,
            "extractions": extractions,
        }

    def build_synthesis_prompt(self, cluster_data: dict) -> str:
        """Build the LLM prompt for skill synthesis."""
        manifest = cluster_data["manifest"]
        extractions = cluster_data["extractions"]

        # Summarize extractions
        summaries = []
        for ext in extractions:
            summary = {
                "doc_id": ext.get("doc_id", "unknown"),
                "trigger": ext.get("trigger", {}),
                "workflow": ext.get("workflow", {}),
                "code_written": ext.get("code_written", {}),
                "issues_and_fixes": ext.get("issues_and_fixes", {}),
                "skill_assessment": ext.get("skill_assessment", {}),
                "tags": ext.get("tags", {}),
                "raw_context": ext.get("raw_sections", {}).get("context", ""),
                "raw_workflow": ext.get("raw_sections", {}).get("workflow", ""),
            }
            summaries.append(summary)

        prompt = f"""You are a skill synthesis expert. Generate a complete Claude Code skill from the following cluster.

## CLUSTER INFORMATION

**Cluster ID**: {manifest.get('cluster_name', 'unknown')}
**Description**: {manifest.get('cluster_description', 'No description')}
**Member Count**: {manifest.get('member_count', 0)} documents

**Top Shared Tags**:
- Domains: {', '.join(manifest.get('top_tags', {}).get('domains', [])[:10])}
- Patterns: {', '.join(manifest.get('top_tags', {}).get('patterns', [])[:10])}
- Frameworks: {', '.join(manifest.get('top_tags', {}).get('frameworks', [])[:10])}

**Common Trigger Phrases**:
{chr(10).join('- ' + phrase for phrase in manifest.get('trigger_phrases', [])[:15])}

**Typical Outputs**:
{chr(10).join('- ' + out for out in manifest.get('typical_outputs', [])[:10])}

## REPRESENTATIVE DOCUMENTS

{json.dumps(summaries, indent=2, ensure_ascii=False)[:50000]}

## OUTPUT CONTRACT

Return a single JSON object:

```json
{{
  "skill_name": "kebab-case-name",
  "description": "One-line description for skill activation",
  "skill_md": "Full markdown content for SKILL.md",
  "references_files": [
    {{"path": "references/filename.md", "contents": "file contents"}}
  ],
  "scripts_files": [
    {{"path": "scripts/filename.py", "contents": "file contents"}}
  ],
  "assets_files": [
    {{"path": "assets/filename.ext", "contents": "file contents"}}
  ],
  "traceability": {{
    "source_doc_ids": ["list of doc_ids used"],
    "section_sources": {{
      "workflow": ["doc_id_1"],
      "issues": ["doc_id_2"],
      "scripts": ["doc_id_1"]
    }}
  }}
}}
```

## SKILL.MD FORMAT

```markdown
---
name: skill-name
description: Brief description for matching
version: 1.0.0
---

# Skill Title

## Purpose
What this skill does and why.

## Triggers
- "trigger phrase 1"
- "trigger phrase 2"

## Prerequisites
### Required Libraries
```bash
pip install package1 package2
```

---

## Workflow Overview

### High-Level Steps
1. Step one
2. Step two

---

## Core Implementation

### Pattern 1
Code and explanation.

---

## Common Issues & Solutions

### Issue 1
**Symptoms**: What you see
**Cause**: Root cause
**Solution**: How to fix

---

## Verification
- [ ] Checklist item 1

---

## References
- Scripts: [script.py](scripts/script.py)
```

## SYNTHESIS RULES

1. Include what Claude can't know (your specifics)
2. Exclude generic knowledge
3. Match specificity to risk
4. Keep SKILL.md lean - push deep content to references/scripts/assets
5. No emojis

Return ONLY the JSON object, no markdown code fences around it."""

        return prompt

    def synthesize_skill(self, cluster_data: dict) -> dict:
        """Call the LLM to synthesize a skill."""
        prompt = self.build_synthesis_prompt(cluster_data)

        print(f"  Calling {self.model} for synthesis...")

        response_text = ""
        with self.client.messages.stream(
            model=self.model,
            max_tokens=32000,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                if len(response_text) % 1000 == 0:
                    print(".", end="", flush=True)
        print()

        response_text = response_text.strip()

        # Handle markdown code fences
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            start_idx = 1 if lines[0].startswith("```") else 0
            end_idx = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            response_text = "\n".join(lines[start_idx:end_idx])

        return json.loads(response_text)

    def write_skill_folder(self, skill_result: dict) -> Path:
        """Write the synthesized skill to the output directory."""
        skill_name = skill_result.get("skill_name", "unknown-skill")
        skill_dir = self.output_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_md = skill_result.get("skill_md", "")
        skill_md_path = skill_dir / "SKILL.md"
        with open(skill_md_path, 'w', encoding='utf-8') as f:
            f.write(skill_md)
        print(f"  Created: {skill_md_path.name}")

        # Write references
        for ref in skill_result.get("references_files", []):
            ref_path = skill_dir / ref.get("path", "references/unknown.md")
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            with open(ref_path, 'w', encoding='utf-8') as f:
                f.write(ref.get("contents", ""))
            print(f"  Created: {ref_path.relative_to(skill_dir)}")

        # Write scripts
        for script in skill_result.get("scripts_files", []):
            script_path = skill_dir / script.get("path", "scripts/unknown.py")
            script_path.parent.mkdir(parents=True, exist_ok=True)
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script.get("contents", ""))
            print(f"  Created: {script_path.relative_to(skill_dir)}")

        # Write assets
        for asset in skill_result.get("assets_files", []):
            asset_path = skill_dir / asset.get("path", "assets/unknown.txt")
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            with open(asset_path, 'w', encoding='utf-8') as f:
                f.write(asset.get("contents", ""))
            print(f"  Created: {asset_path.relative_to(skill_dir)}")

        # Write traceability
        traceability = skill_result.get("traceability", {})
        trace_path = skill_dir / "traceability.json"
        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump(traceability, f, indent=2, ensure_ascii=False)
        print(f"  Created: traceability.json")

        return skill_dir

    def get_all_cluster_ids(self) -> List[str]:
        """Get all cluster IDs."""
        return sorted([f.stem for f in self.final_dir.glob("*.json")])

    def run(
        self,
        cluster_ids: Optional[List[str]] = None,
        max_clusters: Optional[int] = None,
        dry_run: bool = False,
    ) -> dict:
        """Run the synthesis pipeline."""
        results = {
            "processed": [],
            "failed": [],
            "skipped": [],
        }

        if cluster_ids is None:
            cluster_ids = self.get_all_cluster_ids()

        if max_clusters:
            cluster_ids = cluster_ids[:max_clusters]

        print(f"\n  Clusters to process: {len(cluster_ids)}")

        for i, cluster_id in enumerate(cluster_ids, 1):
            print(f"\n[{i}/{len(cluster_ids)}] Processing: {cluster_id}")
            print("-" * 50)

            try:
                cluster_data = self.load_cluster_data(cluster_id)

                if not cluster_data["extractions"]:
                    print("  SKIPPED: No extractions found")
                    results["skipped"].append({
                        "cluster_id": cluster_id,
                        "reason": "No extractions"
                    })
                    continue

                print(f"  Loaded {len(cluster_data['extractions'])} extraction(s)")

                if dry_run:
                    prompt = self.build_synthesis_prompt(cluster_data)
                    print(f"\n  DRY RUN - Prompt preview ({len(prompt)} chars):")
                    print(f"  {prompt[:1000]}...")
                    results["skipped"].append({
                        "cluster_id": cluster_id,
                        "reason": "Dry run"
                    })
                    continue

                skill_result = self.synthesize_skill(cluster_data)
                skill_dir = self.write_skill_folder(skill_result)

                results["processed"].append({
                    "cluster_id": cluster_id,
                    "skill_name": skill_result.get("skill_name"),
                    "skill_dir": str(skill_dir),
                    "description": skill_result.get("description", "")[:100],
                })

                print(f"\n  SUCCESS: Created '{skill_result.get('skill_name')}'")

            except Exception as e:
                print(f"  FAILED: {e}")
                results["failed"].append({
                    "cluster_id": cluster_id,
                    "error": str(e),
                })

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Phase D: Skill Synthesis Pipeline"
    )

    defaults = get_default_paths()

    parser.add_argument("--api-key", type=str, help="Anthropic API key")
    parser.add_argument("--clusters-dir", type=str, default=str(defaults["clusters_dir"]))
    parser.add_argument("--extractions-dir", type=str, default=str(defaults["extractions_dir"]))
    parser.add_argument("--output-dir", type=str, default=str(defaults["skills_output_dir"]))
    parser.add_argument("--cluster", type=str, help="Synthesize specific cluster")
    parser.add_argument("--clusters", nargs="+", help="Synthesize specific clusters")
    parser.add_argument("--max-clusters", type=int, help="Limit clusters to process")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", type=str, default="claude-opus-4-5-20251101")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: No API key. Use --api-key or set ANTHROPIC_API_KEY")
        exit(1)

    cluster_ids = None
    if args.cluster:
        cluster_ids = [args.cluster]
    elif args.clusters:
        cluster_ids = args.clusters

    print("=" * 60)
    print("Phase D: Skill Synthesis Pipeline")
    print("=" * 60)
    print(f"  Output: {args.output_dir}")

    pipeline = SkillSynthesisPipeline(
        clusters_dir=Path(args.clusters_dir),
        extractions_dir=Path(args.extractions_dir),
        output_dir=Path(args.output_dir),
        api_key=api_key or "",
        model=args.model,
    )

    results = pipeline.run(
        cluster_ids=cluster_ids,
        max_clusters=args.max_clusters,
        dry_run=args.dry_run,
    )

    # Summary
    print("\n" + "=" * 60)
    print("SYNTHESIS COMPLETE")
    print("=" * 60)
    print(f"  Processed: {len(results['processed'])}")
    print(f"  Failed: {len(results['failed'])}")
    print(f"  Skipped: {len(results['skipped'])}")

    if results["processed"]:
        print(f"\n  Generated Skills:")
        for r in results["processed"]:
            print(f"    - {r['skill_name']}: {r['description']}")

    if results["failed"]:
        print(f"\n  Failed Clusters:")
        for r in results["failed"]:
            print(f"    - {r['cluster_id']}: {r['error']}")

    # Save summary
    summary_path = Path(args.clusters_dir) / "_phase_d_synthesis_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "output_dir": args.output_dir,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
