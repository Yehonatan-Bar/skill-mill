"""
Skills From Docs Toolkit - Configuration Module

This module provides centralized configuration for the entire pipeline.
Users should set environment variables or modify the config.json file
to customize paths and settings for their environment.

Environment Variables (optional):
    SRPTD_PROJECT_ROOT: Base directory for the project
    SRPTD_RAW_DIR: Directory containing raw SR-PTD markdown files
    SRPTD_OUTPUT_DIR: Directory for generated skills
    ANTHROPIC_API_KEY: API key for Claude AI
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any


def get_project_root() -> Path:
    """
    Get the project root directory.

    Priority:
    1. SRPTD_PROJECT_ROOT environment variable
    2. Current working directory
    """
    env_root = os.environ.get("SRPTD_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    return Path.cwd()


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from config.json file.

    Args:
        config_path: Path to config file. Defaults to PROJECT_ROOT/config.json

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = get_project_root() / "config.json"

    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # Return defaults if no config file
    return get_default_config()


def get_default_config() -> Dict[str, Any]:
    """Get default configuration values."""
    project_root = get_project_root()

    return {
        # Directory Structure
        "project_root": str(project_root),
        "srptd_raw_dir": str(project_root / "srptd_raw"),
        "extractions_dir": str(project_root / "extractions"),
        "clusters_dir": str(project_root / "clusters"),
        "skills_output_dir": str(project_root / "skills_out"),

        # Clustering Configuration
        "doc_cards_subdir": "doc_cards",
        "buckets_subdir": "buckets",
        "enriched_cards_subdir": "doc_cards_enriched",
        "enriched_buckets_subdir": "buckets_enriched",
        "incremental_clusters_subdir": "clusters_incremental",
        "final_clusters_subdir": "clusters_final",
        "representatives_subdir": "representatives",
        "manifests_subdir": "manifests",

        # AI Model Configuration
        "model_for_enrichment": "claude-sonnet-4-20250514",
        "model_for_clustering": "claude-sonnet-4-20250514",
        "model_for_synthesis": "claude-opus-4-5-20251101",

        # Processing Parameters
        "min_bucket_size_for_clustering": 1,
        "max_clusters_per_prompt": 10,
        "similarity_threshold": 0.25,
        "min_cluster_size_for_audit": 10,

        # Tag Vocabularies (customizable per domain)
        "domain_vocabulary": [],
        "pattern_vocabulary": [],

        # Domain Rollups for Merging (customize for your domain)
        "domain_rollups": {},

        # Domain Affinity Groups for Manifests (customize for your domain)
        "domain_affinity": {},

        # Pattern Affinity Groups (customize for your domain)
        "pattern_affinity": {}
    }


def save_config(config: Dict[str, Any], config_path: Optional[Path] = None):
    """Save configuration to config.json file."""
    if config_path is None:
        config_path = get_project_root() / "config.json"

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class PipelineConfig:
    """
    Configuration class for the Skills From Docs pipeline.

    Usage:
        config = PipelineConfig()
        print(config.extractions_dir)

        # Or with custom config file:
        config = PipelineConfig(config_path="my_config.json")
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._config = load_config(config_path)
        self._project_root = Path(self._config.get("project_root", get_project_root()))

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def srptd_raw_dir(self) -> Path:
        return Path(self._config.get("srptd_raw_dir", self._project_root / "srptd_raw"))

    @property
    def extractions_dir(self) -> Path:
        return Path(self._config.get("extractions_dir", self._project_root / "extractions"))

    @property
    def clusters_dir(self) -> Path:
        return Path(self._config.get("clusters_dir", self._project_root / "clusters"))

    @property
    def skills_output_dir(self) -> Path:
        return Path(self._config.get("skills_output_dir", self._project_root / "skills_out"))

    @property
    def doc_cards_dir(self) -> Path:
        return self.clusters_dir / self._config.get("doc_cards_subdir", "doc_cards")

    @property
    def buckets_dir(self) -> Path:
        return self.clusters_dir / self._config.get("buckets_subdir", "buckets")

    @property
    def enriched_cards_dir(self) -> Path:
        return self.clusters_dir / self._config.get("enriched_cards_subdir", "doc_cards_enriched")

    @property
    def enriched_buckets_dir(self) -> Path:
        return self.clusters_dir / self._config.get("enriched_buckets_subdir", "buckets_enriched")

    @property
    def incremental_clusters_dir(self) -> Path:
        return self.clusters_dir / self._config.get("incremental_clusters_subdir", "clusters_incremental")

    @property
    def final_clusters_dir(self) -> Path:
        return self.clusters_dir / self._config.get("final_clusters_subdir", "clusters_final")

    @property
    def representatives_dir(self) -> Path:
        return self.clusters_dir / self._config.get("representatives_subdir", "representatives")

    @property
    def manifests_dir(self) -> Path:
        return self.clusters_dir / self._config.get("manifests_subdir", "manifests")

    # Model Configuration
    @property
    def model_for_enrichment(self) -> str:
        return self._config.get("model_for_enrichment", "claude-sonnet-4-20250514")

    @property
    def model_for_clustering(self) -> str:
        return self._config.get("model_for_clustering", "claude-sonnet-4-20250514")

    @property
    def model_for_synthesis(self) -> str:
        return self._config.get("model_for_synthesis", "claude-opus-4-5-20251101")

    # Processing Parameters
    @property
    def min_bucket_size(self) -> int:
        return self._config.get("min_bucket_size_for_clustering", 1)

    @property
    def max_clusters_per_prompt(self) -> int:
        return self._config.get("max_clusters_per_prompt", 10)

    @property
    def similarity_threshold(self) -> float:
        return self._config.get("similarity_threshold", 0.25)

    @property
    def min_cluster_size_for_audit(self) -> int:
        return self._config.get("min_cluster_size_for_audit", 10)

    # Vocabularies
    @property
    def domain_vocabulary(self) -> list:
        return self._config.get("domain_vocabulary", [])

    @property
    def pattern_vocabulary(self) -> list:
        return self._config.get("pattern_vocabulary", [])

    @property
    def domain_rollups(self) -> dict:
        return self._config.get("domain_rollups", {})

    @property
    def domain_affinity(self) -> dict:
        return self._config.get("domain_affinity", {})

    @property
    def pattern_affinity(self) -> dict:
        return self._config.get("pattern_affinity", {})

    def ensure_directories(self):
        """Create all required directories if they don't exist."""
        dirs = [
            self.srptd_raw_dir,
            self.extractions_dir,
            self.clusters_dir,
            self.skills_output_dir,
            self.doc_cards_dir,
            self.buckets_dir,
            self.enriched_cards_dir,
            self.enriched_buckets_dir,
            self.incremental_clusters_dir,
            self.final_clusters_dir,
            self.representatives_dir,
            self.manifests_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def get_api_key(self) -> Optional[str]:
        """
        Get Anthropic API key from various sources.

        Priority:
        1. ANTHROPIC_API_KEY environment variable
        2. .env file in project root
        3. ~/.anthropic/api_key file
        """
        # Check environment
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return api_key

        # Check .env file
        env_file = self.project_root / ".env"
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY="):
                        return line.split("=", 1)[1].strip()

        # Check home directory
        home_key = Path.home() / ".anthropic" / "api_key"
        if home_key.exists():
            return home_key.read_text().strip()

        return None
