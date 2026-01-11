#!/usr/bin/env python3
"""
Generate Skills From Claude Code Logs

This script provides a user-friendly way to:
1. Set up API key configuration
2. Parse Claude Code conversation logs
3. Convert logs to SR-PTD documentation format
4. Run the full skills extraction pipeline
5. Generate reusable Claude Skills

QUICK START:
    # First-time setup (interactive)
    python generate_skills_from_logs.py --setup

    # Generate skills from your Claude Code logs
    python generate_skills_from_logs.py

    # Specify custom logs path
    python generate_skills_from_logs.py --logs "C:/Users/you/.claude/projects"

    # Full pipeline with all options
    python generate_skills_from_logs.py --logs ~/.claude/projects --output ./my_skills --days 30

REQUIREMENTS:
    - Python 3.10+
    - Anthropic API key (for AI phases)
    - Claude Code logs (~/.claude/projects/*.jsonl)

Author: Skills From Docs Toolkit
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_DIR = SCRIPT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import our modules
try:
    from scripts.logging_setup import (
        get_logger, configure_logging, LogCategory,
        log_performance, create_logging_config_template
    )
    from scripts.claude_logs_parser import ClaudeLogsParser, list_available_sessions
    from scripts.log_to_srptd_converter import LogToSRPTDConverter
    from scripts.config import PipelineConfig, get_project_root
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from the toolkit directory.")
    sys.exit(1)


# =============================================================================
# Configuration Management
# =============================================================================

class SkillsGenerator:
    """
    Main orchestrator for generating skills from Claude Code logs.

    Handles:
    - Configuration and setup
    - Log parsing
    - Conversion to SR-PTD
    - Pipeline execution
    """

    DEFAULT_PROJECT_DIR = Path.cwd()

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        logs_path: Optional[Path] = None,
        api_key: Optional[str] = None,
        log_level: str = "INFO"
    ):
        """
        Initialize the skills generator.

        Args:
            project_dir: Project directory for output
            logs_path: Path to Claude Code logs
            api_key: Anthropic API key
            log_level: Logging level
        """
        self.project_dir = Path(project_dir) if project_dir else self.DEFAULT_PROJECT_DIR
        self.logs_path = Path(logs_path).expanduser() if logs_path else None
        self.api_key = api_key

        # Setup logging
        log_file = self.project_dir / "logs" / f"skills_gen_{datetime.now():%Y%m%d_%H%M%S}.log"
        self.logger = configure_logging(
            log_level=log_level,
            log_file=str(log_file),
            console=True,
            json_output=False
        )

        # Initialize components
        self.parser = None
        self.converter = None
        self.config = None

    def setup(self, interactive: bool = True) -> bool:
        """
        Perform initial setup including API key configuration.

        Args:
            interactive: Whether to prompt for user input

        Returns:
            True if setup successful
        """
        self.logger.info(f"{LogCategory.CONFIG} Starting setup...")

        print("\n" + "=" * 60)
        print("  Skills From Logs - Setup Wizard")
        print("=" * 60)

        # 1. Create directory structure
        self._create_directories()

        # 2. Configure API key
        if interactive:
            self._setup_api_key_interactive()
        else:
            self._setup_api_key_file()

        # 3. Create config files
        self._create_config_files()

        # 4. Verify logs path
        self._verify_logs_path(interactive)

        print("\n" + "=" * 60)
        print("  Setup Complete!")
        print("=" * 60)
        print(f"""
Your project is ready at: {self.project_dir}

Next steps:
  1. Run: python generate_skills_from_logs.py
  2. Or with options: python generate_skills_from_logs.py --days 30

Generated skills will be in: {self.project_dir / 'skills_out'}
""")

        return True

    def _create_directories(self):
        """Create required project directories."""
        dirs = [
            "srptd_raw",
            "extractions",
            "clusters",
            "skills_out",
            "logs",
        ]

        for d in dirs:
            path = self.project_dir / d
            path.mkdir(parents=True, exist_ok=True)
            print(f"  [+] Created: {d}/")

    def _setup_api_key_interactive(self):
        """Interactive API key setup."""
        print("\n-- API Key Configuration --")

        # Check existing
        env_file = self.project_dir / ".env"
        existing_key = None

        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith("ANTHROPIC_API_KEY="):
                        existing_key = line.split("=", 1)[1].strip()
                        if existing_key and not existing_key.startswith("sk-ant-your"):
                            print(f"  Found existing API key: {existing_key[:10]}...{existing_key[-4:]}")
                            keep = input("  Keep this key? [Y/n]: ").strip().lower()
                            if keep != 'n':
                                self.api_key = existing_key
                                return

        # Check environment
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            print(f"  Found API key in environment: {env_key[:10]}...{env_key[-4:]}")
            use_env = input("  Use this key? [Y/n]: ").strip().lower()
            if use_env != 'n':
                self.api_key = env_key
                self._save_env_file()
                return

        # Prompt for new key
        print("\n  Enter your Anthropic API key")
        print("  (Get one at: https://console.anthropic.com/)")
        api_key = input("  API Key: ").strip()

        if api_key and api_key.startswith("sk-ant-"):
            self.api_key = api_key
            self._save_env_file()
            print("  [+] API key saved to .env")
        else:
            print("  [!] Invalid or empty API key. You can add it later to .env")

    def _setup_api_key_file(self):
        """Non-interactive API key setup."""
        # Check multiple sources
        sources = [
            os.environ.get("ANTHROPIC_API_KEY"),
            self._read_env_file(),
            self._read_home_key_file(),
        ]

        for key in sources:
            if key and key.startswith("sk-ant-"):
                self.api_key = key
                self._save_env_file()
                self.logger.info(f"{LogCategory.CONFIG} Found API key")
                return

        self.logger.warning(f"{LogCategory.CONFIG} No API key found")

    def _read_env_file(self) -> Optional[str]:
        """Read API key from .env file."""
        env_file = self.project_dir / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        if key and not key.startswith("sk-ant-your"):
                            return key
        return None

    def _read_home_key_file(self) -> Optional[str]:
        """Read API key from ~/.anthropic/api_key."""
        key_file = Path.home() / ".anthropic" / "api_key"
        if key_file.exists():
            return key_file.read_text().strip()
        return None

    def _save_env_file(self):
        """Save API key to .env file."""
        if not self.api_key:
            return

        env_file = self.project_dir / ".env"

        # Read existing content
        content = {}
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        content[key.strip()] = value.strip()

        # Update API key
        content["ANTHROPIC_API_KEY"] = self.api_key

        # Write back
        with open(env_file, 'w') as f:
            for key, value in content.items():
                f.write(f"{key}={value}\n")

    def _create_config_files(self):
        """Create configuration files."""
        # config.json
        config_file = self.project_dir / "config.json"
        if not config_file.exists():
            config = {
                "project_root": ".",
                "srptd_raw_dir": "srptd_raw",
                "extractions_dir": "extractions",
                "clusters_dir": "clusters",
                "skills_output_dir": "skills_out",
                "model_for_enrichment": "claude-sonnet-4-20250514",
                "model_for_clustering": "claude-sonnet-4-20250514",
                "model_for_synthesis": "claude-opus-4-5-20251101",
                "domain_vocabulary": [
                    "api-development", "data-analysis", "pdf-processing",
                    "frontend", "deployment", "ai-integration", "testing"
                ],
                "pattern_vocabulary": [
                    "feature-implementation", "bug-fix", "refactor",
                    "configuration", "integration", "optimization"
                ]
            }
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"  [+] Created: config.json")

        # logging_config.json
        log_config_file = self.project_dir / "logging_config.json"
        if not log_config_file.exists():
            create_logging_config_template(log_config_file)

        # .gitignore
        gitignore_file = self.project_dir / ".gitignore"
        if not gitignore_file.exists():
            gitignore_file.write_text(""".env
*.pyc
__pycache__/
.pipeline_progress.json
logs/
""")
            print(f"  [+] Created: .gitignore")

    def _verify_logs_path(self, interactive: bool = True):
        """Verify Claude Code logs path."""
        print("\n-- Claude Code Logs --")

        # Try to find logs
        parser = ClaudeLogsParser(self.logs_path)

        if parser.log_path and parser.log_path.exists():
            files = parser.find_log_files()
            print(f"  Found logs at: {parser.log_path}")
            print(f"  Available sessions: {len(files)}")
            self.logs_path = parser.log_path
        else:
            print("  [!] Could not find Claude Code logs")
            print("  Default location: ~/.claude/projects/")

            if interactive:
                custom = input("  Enter custom logs path (or press Enter to skip): ").strip()
                if custom:
                    custom_path = Path(custom).expanduser()
                    if custom_path.exists():
                        self.logs_path = custom_path
                        print(f"  [+] Using: {custom_path}")
                    else:
                        print(f"  [!] Path not found: {custom_path}")

    @log_performance("Generate skills from logs")
    def generate(
        self,
        days: int = 30,
        max_conversations: int = 50,
        skip_synthesis: bool = False,
        dry_run: bool = False
    ) -> bool:
        """
        Run the full skills generation pipeline.

        Args:
            days: Number of days of logs to process
            max_conversations: Maximum conversations to process
            skip_synthesis: Skip the final synthesis phase
            dry_run: Preview without making API calls

        Returns:
            True if successful
        """
        self.logger.info(f"{LogCategory.PIPELINE} Starting skills generation")
        print("\n" + "=" * 60)
        print("  Generating Skills from Claude Code Logs")
        print("=" * 60)

        # Phase 1: Parse logs
        print("\n[Phase 1] Parsing Claude Code logs...")
        conversations = self._parse_logs(days, max_conversations)
        if not conversations:
            print("  No conversations found. Run with --setup to configure.")
            return False
        print(f"  Found {len(conversations)} conversations")

        # Phase 2: Convert to SR-PTD
        print("\n[Phase 2] Converting to SR-PTD format...")
        srptd_files = self._convert_to_srptd(conversations)
        if not srptd_files:
            print("  Conversion failed.")
            return False
        print(f"  Generated {len(srptd_files)} SR-PTD files")

        # Phase 3: Run pipeline
        print("\n[Phase 3] Running skills extraction pipeline...")
        success = self._run_pipeline(skip_synthesis=skip_synthesis, dry_run=dry_run)

        if success:
            skills_dir = self.project_dir / "skills_out"
            skills = list(skills_dir.glob("*/SKILL.md")) if skills_dir.exists() else []

            print("\n" + "=" * 60)
            print("  Generation Complete!")
            print("=" * 60)
            print(f"""
  Conversations processed: {len(conversations)}
  SR-PTD files created: {len(srptd_files)}
  Skills generated: {len(skills)}

  Output location: {skills_dir}
""")
        else:
            print("\n  Pipeline completed with issues. Check logs for details.")

        return success

    def _parse_logs(self, days: int, max_conversations: int) -> List[Any]:
        """Parse Claude Code logs."""
        self.parser = ClaudeLogsParser(self.logs_path)

        if not self.parser.log_path:
            self.logger.error(f"{LogCategory.ERROR} No logs path configured")
            return []

        return self.parser.parse_recent(days=days, max_conversations=max_conversations)

    def _convert_to_srptd(self, conversations: List[Any]) -> List[Path]:
        """Convert conversations to SR-PTD format."""
        output_dir = self.project_dir / "srptd_raw"
        self.converter = LogToSRPTDConverter(output_dir)

        return self.converter.batch_convert(conversations, output_dir)

    def _run_pipeline(self, skip_synthesis: bool = False, dry_run: bool = False) -> bool:
        """Run the skills extraction pipeline."""
        # Find run_pipeline.py
        pipeline_script = SCRIPT_DIR / "run_pipeline.py"

        if not pipeline_script.exists():
            self.logger.error(f"{LogCategory.ERROR} Pipeline script not found: {pipeline_script}")
            return False

        # Build command
        cmd = [sys.executable, str(pipeline_script), "--project", str(self.project_dir)]

        if skip_synthesis:
            cmd.append("--skip-synthesis")
        if dry_run:
            cmd.append("--dry-run")

        # Set up environment
        env = os.environ.copy()
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key

        # Load .env
        env_file = self.project_dir / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        env[key.strip()] = value.strip()

        self.logger.info(f"{LogCategory.PIPELINE} Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                env=env,
                capture_output=False
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"{LogCategory.ERROR} Pipeline execution failed: {e}")
            return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List available Claude Code sessions."""
        return list_available_sessions(self.logs_path)


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Claude Skills from Claude Code conversation logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_skills_from_logs.py --setup          Interactive setup
  python generate_skills_from_logs.py                  Generate skills
  python generate_skills_from_logs.py --days 7         Last 7 days only
  python generate_skills_from_logs.py --list           List available sessions
  python generate_skills_from_logs.py --dry-run        Preview without API calls

API Key Sources (in priority order):
  1. --api-key command line argument
  2. ANTHROPIC_API_KEY environment variable
  3. .env file in project directory
  4. ~/.anthropic/api_key file
        """
    )

    # Setup options
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup wizard"
    )

    # Input options
    parser.add_argument(
        "--logs", "-l",
        type=str,
        metavar="PATH",
        help="Path to Claude Code logs (default: ~/.claude/projects)"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Number of days of logs to process (default: 30)"
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=50,
        help="Maximum conversations to process (default: 50)"
    )

    # Output options
    parser.add_argument(
        "--output", "-o",
        type=str,
        metavar="DIR",
        help="Output directory (default: current directory)"
    )

    # API options
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        metavar="KEY",
        help="Anthropic API key"
    )

    # Processing options
    parser.add_argument(
        "--skip-synthesis",
        action="store_true",
        help="Skip Phase D skill synthesis"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without API calls"
    )

    # Utility options
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available Claude Code sessions"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Initialize generator
    generator = SkillsGenerator(
        project_dir=Path(args.output) if args.output else None,
        logs_path=Path(args.logs) if args.logs else None,
        api_key=args.api_key,
        log_level="DEBUG" if args.verbose else "INFO"
    )

    # Handle commands
    if args.setup:
        success = generator.setup(interactive=True)
        sys.exit(0 if success else 1)

    if args.list:
        sessions = generator.list_sessions()
        print(f"\nFound {len(sessions)} Claude Code sessions:\n")
        for s in sessions[:30]:
            print(f"  {s['session_id'][:40]:40} {s['modified_time'][:10]} {s['size_kb']:.1f}KB")
        if len(sessions) > 30:
            print(f"  ... and {len(sessions) - 30} more")
        sys.exit(0)

    # Run generation
    success = generator.generate(
        days=args.days,
        max_conversations=args.max,
        skip_synthesis=args.skip_synthesis,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
