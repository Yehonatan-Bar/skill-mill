# Skills From Docs Toolkit

A pipeline for extracting reusable Claude Code Skills from SR-PTD (Skill-Ready Post-Task Documentation) files.

---

## IMPORTANT: Prerequisites

Before running this toolkit, you MUST have:

1. **Anthropic API Key** - Required for AI-powered phases (C.2, C.3, D)
   - Get your key from: https://console.anthropic.com/
   - The key looks like: `sk-ant-api03-...`
   - Without this key, the pipeline will fail at AI phases

2. **Python 3.10+** with the `anthropic` package:
   ```bash
   pip install anthropic
   ```

3. **SR-PTD Documentation Files** - Your task documentation in markdown format
   - Must follow the SR-PTD format (sections A-J) or Quick Capture format
   - See `docs/SR-PTD_DOCUMENTATION_GUIDE.md` for format details

---

## Quick Start (3 Steps)

### 1. Setup
```bash
# Create a new project directory
mkdir my_skills_project && cd my_skills_project

# Run the setup script
python /path/to/skills_from_docs_toolkit/setup_project.py .
```

### 2. Configure

**CRITICAL: Set your API key in the `.env` file:**
```bash
# Open .env file and replace the placeholder with your real key
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-REAL-KEY-HERE
```

The `.env` file was created by setup_project.py. You MUST edit it with your actual Anthropic API key.

**Then copy your documentation:**
```bash
# Copy your SR-PTD markdown files to the input folder
cp /path/to/your/docs/*.md srptd_raw/
```

### 3. Run
```bash
python run_pipeline.py
```

**Done!** Your generated skills will be in `skills_out/`

### Options
```bash
python run_pipeline.py                   # Full pipeline
python run_pipeline.py --test            # Test mode (3 clusters only)
python run_pipeline.py --dry-run         # Preview without API calls
python run_pipeline.py --resume          # Resume from last checkpoint
python run_pipeline.py --skip-synthesis  # Clustering only (no Phase D)
```

---

## What This Does

Converts task documentation into Claude Code Skills through a two-layer pipeline:

```
SR-PTD Docs  -->  JSON Extractions  -->  Clusters  -->  Claude Skills
   (raw)           (structured)         (grouped)        (final)
```

**Layer 1 (Deterministic)**: Parsing, extraction, and clustering - no AI required
**Layer 2 (AI-Assisted)**: Tag enrichment, semantic clustering, and skill synthesis

---

## Pipeline Phases

| Phase | Script | Description | AI? |
|-------|--------|-------------|-----|
| B | `layer1_extractor.py` | Parse SR-PTD to JSON | No |
| C.0-C.1 | `phase_c_clustering.py` | Doc cards + coarse buckets | No |
| C.2 | `phase_c_tag_enrichment.py` | Fill missing tags | Yes |
| C.3 | `phase_c_incremental_clustering.py` | Semantic clustering | Yes |
| C.4 | `phase_c4_merge_clusters.py` | Cross-bucket merging | No |
| C.5 | `phase_c5_representatives.py` | Select best docs | No |
| Sanity | `sanity_check.py` | Validate data | No |
| D | `phase_d_skill_synthesis.py` | Generate skills | Yes |

---

## Directory Structure

```
my_skills_project/
|-- srptd_raw/              # Input: Your SR-PTD markdown files
|-- extractions/            # Phase B: JSON extractions
|-- clusters/
|   |-- doc_cards/          # C.0: Compact summaries
|   |-- buckets/            # C.1: Domain/pattern groups
|   |-- buckets_enriched/   # C.2: With filled tags
|   |-- clusters_incremental/  # C.3: Semantic clusters
|   |-- clusters_final/     # C.4: Merged clusters
|   |-- representatives/    # C.5: Selected docs
|-- skills_out/             # Phase D: Generated skills
|   |-- skill-name/
|       |-- SKILL.md
|       |-- references/
|       |-- scripts/
|       |-- assets/
|       |-- traceability.json
|-- .env                    # API key
|-- config.json             # Optional customization
|-- run_pipeline.py         # One-click runner
```

---

## Configuration (Optional)

Edit `config.json` to customize for your domain:

```json
{
  "domain_vocabulary": [
    "web-development",
    "data-processing",
    "api-integration"
  ],
  "pattern_vocabulary": [
    "implementation",
    "debugging",
    "migration"
  ],
  "domain_rollups": {
    "development": ["web-development", "backend", "frontend"],
    "data": ["data-processing", "etl", "analytics"]
  }
}
```

---

## SR-PTD Document Format

The toolkit expects markdown files with sections A-J:

| Section | Content |
|---------|---------|
| A | Trigger Profile - what initiated the task |
| B | Context & Inputs - environment, constraints |
| C | Workflow - step-by-step process |
| D | Knowledge Accessed |
| E | Code Written |
| F | Outputs Produced |
| G | Issues & Fixes |
| H | Verification |
| I | Skill Assessment (reusability scores) |
| J | Tags (domains, patterns, languages) |

Also supports: Quick Capture format, Legacy task_doc format

See `docs/SR-PTD_DOCUMENTATION_GUIDE.md` for detailed format guide.

---

## Output: Skill Structure

Each generated skill contains:

```
skill-name/
|-- SKILL.md              # Main documentation (triggers, workflow)
|-- references/           # Deep knowledge, troubleshooting
|-- scripts/              # Reusable code templates
|-- assets/               # Config files, test data
|-- traceability.json     # Links to source SR-PTD documents
```

---

## Requirements

```bash
pip install anthropic
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Too many "unknown" buckets | Run Phase C.2 (tag enrichment) |
| Clusters too fragmented | Check domain_rollups in config.json |
| Clusters too large | Run `phase_c4_purity_audit.py` |
| Phase D fails | Run `sanity_check.py` first |
| API errors | Check .env file has valid ANTHROPIC_API_KEY |

---

## Running Individual Phases

For manual control, run phases separately:

```bash
# Phase B: Extract
python scripts/layer1_extractor.py srptd_raw/ -o extractions/

# Phase C.0-C.1: Doc cards and buckets
python scripts/phase_c_clustering.py

# Phase C.2: Tag enrichment
python scripts/phase_c_tag_enrichment.py

# Phase C.3: Clustering
python scripts/phase_c_incremental_clustering.py

# Phase C.4: Merge
python scripts/phase_c4_merge_clusters.py

# Phase C.5: Representatives
python scripts/phase_c5_representatives.py

# Sanity check
python scripts/sanity_check.py

# Phase D: Synthesis
python scripts/phase_d_skill_synthesis.py
```

---

## Documentation

- `docs/Skills_Extraction_Process.md` - Process overview
- `docs/SR-PTD_DOCUMENTATION_GUIDE.md` - Input format guide
- `docs/Pipeline_Runbook.md` - Detailed methodology

---

## For Claude Code: Helping Users Run This Toolkit

When a user asks you to help them run this toolkit, follow these steps:

### Step 1: Check Prerequisites
Ask the user:
1. "Do you have an Anthropic API key? You'll need one from https://console.anthropic.com/"
2. "Do you have SR-PTD documentation files ready?"

### Step 2: Setup Project
Run:
```bash
python /path/to/skills_from_docs_toolkit/setup_project.py /path/to/user/project
```

### Step 3: Remind User to Set API Key
Tell the user:
"Please edit the `.env` file in your project folder and add your Anthropic API key:
`ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE`"

**Do NOT proceed until the user confirms they have set their API key.**

### Step 4: Copy User's Documentation
Help the user copy their SR-PTD files to `srptd_raw/` folder.

### Step 5: Run Pipeline
```bash
cd /path/to/user/project
python run_pipeline.py --test  # Start with test mode
```

### Common Issues to Watch For
- **"No API key found"** - User forgot to edit .env file
- **"No markdown files found"** - User didn't copy files to srptd_raw/
- **Phase fails** - Use `--resume` to continue from last checkpoint

---

## License

MIT License
