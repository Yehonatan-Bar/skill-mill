#!/usr/bin/env python3
"""
Skills From Docs - One-Click Pipeline Runner

This script runs the entire SR-PTD to Skills pipeline with a single command.

QUICK START:
    1. Put your SR-PTD markdown files in srptd_raw/
    2. Create .env file with: ANTHROPIC_API_KEY=sk-ant-your-key
    3. Run: python run_pipeline.py

OPTIONS:
    python run_pipeline.py                    # Full pipeline
    python run_pipeline.py --test             # Test with 3 clusters only
    python run_pipeline.py --dry-run          # Preview without API calls
    python run_pipeline.py --skip-synthesis   # Run clustering only (no Phase D)
    python run_pipeline.py --resume           # Resume from last successful phase
"""

import os
import sys
import json
import argparse
import subprocess
import time
from pathlib import Path
from datetime import datetime


# =============================================================================
# Configuration
# =============================================================================

SCRIPTS_DIR = Path(__file__).parent / "scripts"

PHASES = [
    {
        "id": "B",
        "name": "Layer 1 Extraction",
        "script": "layer1_extractor.py",
        "args": lambda cfg: [cfg["srptd_raw_dir"], "-o", cfg["extractions_dir"]],
        "requires_api": False,
        "check_output": lambda cfg: len(list(Path(cfg["extractions_dir"]).glob("*.json"))) > 0,
    },
    {
        "id": "C.0-C.1",
        "name": "Doc Cards & Bucketing",
        "script": "phase_c_clustering.py",
        "args": lambda cfg: ["--input-dir", cfg["extractions_dir"], "--output-dir", cfg["clusters_dir"]],
        "requires_api": False,
        "check_output": lambda cfg: (Path(cfg["clusters_dir"]) / "doc_cards").exists(),
    },
    {
        "id": "C.2",
        "name": "AI Tag Enrichment",
        "script": "phase_c_tag_enrichment.py",
        "args": lambda cfg: [],
        "requires_api": True,
        "check_output": lambda cfg: (Path(cfg["clusters_dir"]) / "buckets_enriched").exists(),
    },
    {
        "id": "C.3",
        "name": "Incremental Clustering",
        "script": "phase_c_incremental_clustering.py",
        "args": lambda cfg: [],
        "requires_api": True,
        "check_output": lambda cfg: (Path(cfg["clusters_dir"]) / "clusters_incremental").exists(),
    },
    {
        "id": "C.4",
        "name": "Cross-Bucket Merging",
        "script": "phase_c4_merge_clusters.py",
        "args": lambda cfg: [],
        "requires_api": False,
        "check_output": lambda cfg: (Path(cfg["clusters_dir"]) / "clusters_final").exists(),
    },
    {
        "id": "C.5",
        "name": "Representative Selection",
        "script": "phase_c5_representatives.py",
        "args": lambda cfg: [],
        "requires_api": False,
        "check_output": lambda cfg: (Path(cfg["clusters_dir"]) / "representatives").exists(),
    },
    {
        "id": "sanity",
        "name": "Sanity Check",
        "script": "sanity_check.py",
        "args": lambda cfg: [],
        "requires_api": False,
        "check_output": lambda cfg: True,  # Always passes if script succeeds
    },
    {
        "id": "D",
        "name": "Skill Synthesis",
        "script": "phase_d_skill_synthesis.py",
        "args": lambda cfg: cfg.get("synthesis_args", []),
        "requires_api": True,
        "check_output": lambda cfg: (Path(cfg["skills_output_dir"])).exists(),
        "is_synthesis": True,
    },
]


# =============================================================================
# Utilities
# =============================================================================

def print_header(text: str):
    """Print a formatted header."""
    width = 70
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def print_phase(phase_id: str, phase_name: str, status: str = "RUNNING"):
    """Print phase status."""
    status_colors = {
        "RUNNING": "\033[33m",  # Yellow
        "SUCCESS": "\033[32m",  # Green
        "FAILED": "\033[31m",   # Red
        "SKIPPED": "\033[36m",  # Cyan
    }
    reset = "\033[0m"
    color = status_colors.get(status, "")

    print(f"\n[Phase {phase_id}] {phase_name} ... {color}{status}{reset}")


def load_env_file(env_path: Path) -> dict:
    """Load environment variables from .env file."""
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def check_api_key(project_root: Path) -> str:
    """Check for API key in environment or .env file."""
    # Check environment first
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    # Check .env file
    env_file = project_root / ".env"
    if env_file.exists():
        env_vars = load_env_file(env_file)
        api_key = env_vars.get("ANTHROPIC_API_KEY")
        if api_key:
            return api_key

    return ""


def ensure_directories(cfg: dict):
    """Create required directories."""
    dirs = [
        cfg["srptd_raw_dir"],
        cfg["extractions_dir"],
        cfg["clusters_dir"],
        cfg["skills_output_dir"],
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


def count_input_files(srptd_dir: str) -> int:
    """Count markdown files in input directory."""
    srptd_path = Path(srptd_dir)
    if not srptd_path.exists():
        return 0
    return len(list(srptd_path.glob("*.md"))) + len(list(srptd_path.glob("**/*.md")))


def save_progress(project_root: Path, phase_id: str, status: str):
    """Save progress to a checkpoint file."""
    checkpoint_file = project_root / ".pipeline_progress.json"
    progress = {}
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as f:
            progress = json.load(f)

    progress[phase_id] = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    progress["last_phase"] = phase_id
    progress["last_status"] = status

    with open(checkpoint_file, 'w') as f:
        json.dump(progress, f, indent=2)


def load_progress(project_root: Path) -> dict:
    """Load progress from checkpoint file."""
    checkpoint_file = project_root / ".pipeline_progress.json"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return {}


def run_phase(phase: dict, cfg: dict, project_root: Path) -> bool:
    """Run a single pipeline phase."""
    script_path = SCRIPTS_DIR / phase["script"]

    if not script_path.exists():
        print(f"  ERROR: Script not found: {script_path}")
        return False

    # Build command
    cmd = [sys.executable, str(script_path)] + phase["args"](cfg)

    # Set up environment
    env = os.environ.copy()

    # Load .env file
    env_vars = load_env_file(project_root / ".env")
    env.update(env_vars)

    # Set working directory context
    env["SRPTD_PROJECT_ROOT"] = str(project_root)

    try:
        # Run the script
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            env=env,
            capture_output=False,  # Show output in real-time
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


# =============================================================================
# Main Pipeline
# =============================================================================

def run_pipeline(
    project_root: Path,
    test_mode: bool = False,
    dry_run: bool = False,
    skip_synthesis: bool = False,
    resume: bool = False,
):
    """Run the complete pipeline."""

    print_header("Skills From Docs Pipeline")
    print(f"  Project: {project_root}")
    print(f"  Mode: {'TEST (3 clusters)' if test_mode else 'FULL'}")
    if dry_run:
        print(f"  Dry Run: Yes (no API calls)")

    # Configuration
    cfg = {
        "srptd_raw_dir": str(project_root / "srptd_raw"),
        "extractions_dir": str(project_root / "extractions"),
        "clusters_dir": str(project_root / "clusters"),
        "skills_output_dir": str(project_root / "skills_out"),
        "synthesis_args": [],
    }

    # Add synthesis arguments
    if test_mode:
        cfg["synthesis_args"].extend(["--max-clusters", "3"])
    if dry_run:
        cfg["synthesis_args"].append("--dry-run")

    # Ensure directories exist
    ensure_directories(cfg)

    # Check for input files
    input_count = count_input_files(cfg["srptd_raw_dir"])
    if input_count == 0:
        print(f"\n  ERROR: No markdown files found in {cfg['srptd_raw_dir']}")
        print(f"  Please copy your SR-PTD documentation files there first.")
        return False

    print(f"\n  Input files: {input_count} markdown files")

    # Check API key (needed for AI phases)
    api_key = check_api_key(project_root)
    if not api_key and not dry_run:
        print(f"\n  WARNING: No ANTHROPIC_API_KEY found!")
        print(f"  Create a .env file with: ANTHROPIC_API_KEY=sk-ant-your-key")
        print(f"  Or set the environment variable.")
        print(f"\n  AI phases (C.2, C.3, D) will fail without an API key.")
        response = input("  Continue anyway? [y/N]: ")
        if response.lower() != 'y':
            return False
    else:
        print(f"  API Key: {'[SET]' if api_key else '[NOT SET]'}")

    # Load progress if resuming
    progress = {}
    start_from_phase = 0
    if resume:
        progress = load_progress(project_root)
        if progress.get("last_status") == "SUCCESS":
            # Find next phase
            for i, phase in enumerate(PHASES):
                if progress.get(phase["id"], {}).get("status") != "SUCCESS":
                    start_from_phase = i
                    break
            if start_from_phase > 0:
                print(f"\n  Resuming from Phase {PHASES[start_from_phase]['id']}")

    # Run phases
    print_header("Running Pipeline Phases")

    start_time = time.time()
    results = {"success": [], "failed": [], "skipped": []}

    for i, phase in enumerate(PHASES):
        # Skip synthesis if requested
        if skip_synthesis and phase.get("is_synthesis"):
            print_phase(phase["id"], phase["name"], "SKIPPED")
            results["skipped"].append(phase["id"])
            continue

        # Skip already completed phases when resuming
        if resume and i < start_from_phase:
            print_phase(phase["id"], phase["name"], "SKIPPED")
            print("  (already completed)")
            results["skipped"].append(phase["id"])
            continue

        # Check if phase requires API and we don't have it
        if phase["requires_api"] and not api_key and not dry_run:
            print_phase(phase["id"], phase["name"], "SKIPPED")
            print("  (requires API key)")
            results["skipped"].append(phase["id"])
            continue

        print_phase(phase["id"], phase["name"], "RUNNING")

        success = run_phase(phase, cfg, project_root)

        if success:
            print_phase(phase["id"], phase["name"], "SUCCESS")
            save_progress(project_root, phase["id"], "SUCCESS")
            results["success"].append(phase["id"])
        else:
            print_phase(phase["id"], phase["name"], "FAILED")
            save_progress(project_root, phase["id"], "FAILED")
            results["failed"].append(phase["id"])
            print(f"\n  Pipeline stopped at Phase {phase['id']}")
            print(f"  Fix the issue and run again with --resume")
            break

    # Summary
    elapsed = time.time() - start_time
    print_header("Pipeline Complete")
    print(f"  Time: {elapsed:.1f} seconds")
    print(f"  Phases succeeded: {len(results['success'])}")
    print(f"  Phases failed: {len(results['failed'])}")
    print(f"  Phases skipped: {len(results['skipped'])}")

    if results["success"] and not results["failed"]:
        print(f"\n  Generated skills are in: {cfg['skills_output_dir']}")

        # Count generated skills
        skills_dir = Path(cfg["skills_output_dir"])
        if skills_dir.exists():
            skills = [d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
            print(f"  Skills generated: {len(skills)}")

    return len(results["failed"]) == 0


def main():
    parser = argparse.ArgumentParser(
        description="Run the Skills From Docs pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                    Run full pipeline
  python run_pipeline.py --test             Test with 3 clusters only
  python run_pipeline.py --dry-run          Preview without API calls
  python run_pipeline.py --skip-synthesis   Run clustering only
  python run_pipeline.py --resume           Resume from last checkpoint
  python run_pipeline.py --project /path    Use specific project directory
        """
    )

    parser.add_argument(
        "--project", "-p",
        type=str,
        default=str(Path.cwd()),
        help="Project directory (default: current directory)"
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Test mode: process only 3 clusters"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: skip API calls"
    )
    parser.add_argument(
        "--skip-synthesis",
        action="store_true",
        help="Skip Phase D (skill synthesis)"
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from last successful phase"
    )

    args = parser.parse_args()

    project_root = Path(args.project).resolve()

    success = run_pipeline(
        project_root=project_root,
        test_mode=args.test,
        dry_run=args.dry_run,
        skip_synthesis=args.skip_synthesis,
        resume=args.resume,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
