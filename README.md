# Skills From Docs Toolkit

A pipeline for extracting reusable Claude Code Skills from SR-PTD (Skill-Ready Post-Task Documentation) files.

## Overview

This toolkit implements a two-layer pipeline that converts task documentation into structured, reusable Skills:

- **Layer 1 (Deterministic)**: Parsing, extraction, normalization, and clustering - no AI required
- **Layer 2 (AI-Assisted)**: Tag enrichment, cluster refinement, and skill synthesis

## Pipeline Phases

```
Phase A: Setup
    |
    v
Phase B: Layer 1 Extraction (layer1_extractor.py)
    | - Parses SR-PTD markdown files
    | - Outputs: extractions/<doc_id>.json
    v
Phase C.0-C.1: Doc Cards & Bucketing (phase_c_clustering.py)
    | - Creates compact doc cards
    | - Groups by domain/pattern
    | - Outputs: clusters/doc_cards/, clusters/buckets/
    v
Phase C.2: AI Tag Enrichment (phase_c_tag_enrichment.py)  [Optional]
    | - Fills missing domain/pattern tags using AI
    | - Reduces "unknown" buckets
    | - Outputs: clusters/doc_cards_enriched/, clusters/buckets_enriched/
    v
Phase C.3: Incremental Clustering (phase_c_incremental_clustering.py)
    | - AI-assisted clustering within buckets
    | - Outputs: clusters/clusters_incremental/
    v
Phase C.4: Cross-Bucket Merging (phase_c4_merge_clusters.py)
    | - Consolidates fragmented clusters
    | - Outputs: clusters/clusters_final/
    v
Phase C.4b: Purity Audit (phase_c4_purity_audit.py)  [Optional]
    | - Checks large clusters for splits
    v
Phase C.5: Representative Selection (phase_c5_representatives.py)
    | - Selects best docs for synthesis
    | - Outputs: clusters/representatives/
    v
Sanity Check (sanity_check.py)
    | - Validates data integrity
    v
Phase D: Skill Synthesis (phase_d_skill_synthesis.py)
    | - Generates SKILL.md and supporting files
    | - Outputs: skills_out/<skill_name>/
```

## Quick Start

### 1. Setup

```bash
# Create project structure
mkdir my_skills_project
cd my_skills_project
mkdir srptd_raw extractions clusters skills_out

# Copy your SR-PTD markdown files to srptd_raw/
cp /path/to/your/SR-PTD*.md srptd_raw/

# Set API key
export ANTHROPIC_API_KEY="your-key-here"
```

### 2. Run the Pipeline

```bash
# Phase B: Extract documents
python scripts/layer1_extractor.py srptd_raw/ -o extractions/

# Phase C.0-C.1: Create doc cards and buckets
python scripts/phase_c_clustering.py

# Phase C.2: Enrich missing tags (optional but recommended)
python scripts/phase_c_tag_enrichment.py

# Phase C.3: Incremental clustering
python scripts/phase_c_incremental_clustering.py

# Phase C.4: Merge clusters
python scripts/phase_c4_merge_clusters.py

# Phase C.5: Select representatives
python scripts/phase_c5_representatives.py

# Sanity check
python scripts/sanity_check.py

# Phase D: Generate skills
python scripts/phase_d_skill_synthesis.py
```

### 3. Test Mode

Start with a small subset to verify the pipeline works:

```bash
# Process just 3 clusters
python scripts/phase_d_skill_synthesis.py --max-clusters 3

# Dry run to preview without API calls
python scripts/phase_d_skill_synthesis.py --dry-run
```

## Usage for New Users

If you're starting fresh with your own documentation, follow these steps:

### Step 1: Copy the Toolkit

```bash
# Copy the toolkit to your project location
cp -r skills_from_docs_toolkit/ /path/to/my_skills_project/
cd /path/to/my_skills_project/
```

### Step 2: Configure for Your Domain

```bash
# Copy the configuration template
cp templates/config_template.json config.json
```

Edit `config.json` to customize:
- **domain_vocabulary**: Add domains relevant to your work (e.g., "web-scraping", "database-admin", "devops")
- **pattern_vocabulary**: Add patterns you commonly use (e.g., "migration", "automation", "api-wrapper")
- **domain_rollups**: Group related domains for better clustering

### Step 3: Prepare Your Documentation

```bash
# Create required directories
mkdir -p srptd_raw extractions clusters skills_out

# Copy your SR-PTD markdown files
cp /path/to/your/documentation/*.md srptd_raw/
```

Your documentation should follow the SR-PTD format (see `docs/SR-PTD_DOCUMENTATION_GUIDE.md`).

### Step 4: Set Your API Key

```bash
# Option 1: Environment variable
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Option 2: Create .env file
echo 'ANTHROPIC_API_KEY=sk-ant-your-key-here' > .env
```

### Step 5: Run the Full Pipeline

```bash
# Phase B: Extract structured data from your docs
python scripts/layer1_extractor.py srptd_raw/ -o extractions/

# Phase C.0-C.1: Create doc cards and initial buckets
python scripts/phase_c_clustering.py

# Phase C.2: Fill missing tags with AI (recommended)
python scripts/phase_c_tag_enrichment.py

# Phase C.3: Cluster documents within buckets
python scripts/phase_c_incremental_clustering.py

# Phase C.4: Merge related clusters across buckets
python scripts/phase_c4_merge_clusters.py

# Phase C.5: Select representative docs for each cluster
python scripts/phase_c5_representatives.py

# Validate before synthesis
python scripts/sanity_check.py

# Phase D: Generate skills (start with test mode)
python scripts/phase_d_skill_synthesis.py --max-clusters 3

# If successful, run full synthesis
python scripts/phase_d_skill_synthesis.py
```

### Step 6: Review Generated Skills

Your skills will be in `skills_out/`. Each skill folder contains:
- `SKILL.md` - Main skill documentation
- `references/` - Background knowledge
- `scripts/` - Reusable code
- `assets/` - Templates and configs
- `traceability.json` - Links back to source documents

## Directory Structure

```
my_skills_project/
+-- srptd_raw/               # Input: Your SR-PTD markdown files
+-- extractions/             # Phase B output: JSON extractions
+-- clusters/
|   +-- doc_cards/           # C.0: Compact document cards
|   +-- buckets/             # C.1: Coarse buckets
|   +-- doc_cards_enriched/  # C.2: Enriched cards (optional)
|   +-- buckets_enriched/    # C.2: Enriched buckets
|   +-- clusters_incremental/# C.3: Within-bucket clusters
|   +-- clusters_final/      # C.4: Final merged clusters
|   +-- representatives/     # C.5: Selected representatives
+-- skills_out/              # Phase D output: Generated skills
|   +-- skill-name/
|       +-- SKILL.md
|       +-- references/
|       +-- scripts/
|       +-- assets/
|       +-- traceability.json
+-- config.json              # Optional configuration
```

## Configuration

Create a `config.json` file to customize paths and vocabularies:

```json
{
  "project_root": ".",
  "srptd_raw_dir": "srptd_raw",
  "extractions_dir": "extractions",
  "clusters_dir": "clusters",
  "skills_output_dir": "skills_out",

  "model_for_enrichment": "claude-sonnet-4-20250514",
  "model_for_clustering": "claude-sonnet-4-20250514",
  "model_for_synthesis": "claude-opus-4-5-20251101",

  "domain_vocabulary": [
    "your-domain-1",
    "your-domain-2"
  ],

  "domain_rollups": {
    "domain-group-1": ["domain-1", "domain-1-variant"],
    "domain-group-2": ["domain-2", "domain-2-variant"]
  }
}
```

## Requirements

```bash
pip install anthropic
```

## SR-PTD Document Format

The toolkit expects SR-PTD markdown files with sections A-J:

- **Section A**: Trigger Profile (what initiated the task)
- **Section B**: Context & Inputs (environment, constraints)
- **Section C**: Workflow (step-by-step process)
- **Section D**: Knowledge Accessed
- **Section E**: Code Written
- **Section F**: Outputs Produced
- **Section G**: Issues & Fixes
- **Section H**: Verification
- **Section I**: Skill Assessment
- **Section J**: Tags

Also supports:
- Quick Capture format (simplified)
- Legacy task_doc format

## Output: Skill Structure

Each generated skill includes:

```
skill-name/
+-- SKILL.md              # Main skill documentation
+-- references/           # Background knowledge, constraints
+-- scripts/              # Reusable code patterns
+-- assets/               # Templates, configs
+-- traceability.json     # Links to source documents
```

## Customization

### Domain Vocabularies

Customize domain and pattern vocabularies in `phase_c_tag_enrichment.py`:

```python
DEFAULT_DOMAIN_VOCABULARY = [
    "your-domain-1",
    "your-domain-2",
    # Add your specific domains
]
```

### Domain Rollups

Customize how domains are grouped in `phase_c4_merge_clusters.py`:

```python
DEFAULT_DOMAIN_ROLLUPS = {
    "your-domain-group": ["domain-1", "domain-2", "domain-3"],
}
```

## Troubleshooting

### Too Many Unknown Buckets

Run Phase C.2 (tag enrichment) to fill missing tags.

### Clusters Too Fragmented

Run Phase C.4 with `--rollup-first` for aggressive merging.

### Clusters Too Large

Run Phase C.4b (purity audit) to identify splits.

### Phase D Fails

Run `sanity_check.py` to identify missing data.

## License

MIT License - See LICENSE file for details.
