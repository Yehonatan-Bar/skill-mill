# Skills Extraction Process

## Overview

This pipeline converts task documentation (SR-PTD files) into reusable Claude Skills through a two-layer architecture:

- **Layer 1 (Deterministic)**: Parsing, extraction, and clustering - no AI required
- **Layer 2 (AI-Assisted)**: Tag enrichment, semantic clustering, and skill synthesis

```
SR-PTD Docs  -->  JSON Extractions  -->  Clusters  -->  Claude Skills
  (raw)            (structured)         (grouped)       (final)
```

---

## The Four Phases

### Phase B: Extraction
**What**: Parse markdown documentation into structured JSON
**How**: Deterministic regex-based parsing (no AI)
**Handles**: Full SR-PTD (sections A-J), Quick Capture, and legacy formats

Extracts: metadata, triggers, workflow steps, code blocks, issues, tags, reusability scores

### Phase C: Clustering (5 steps)

| Step | Name | Purpose |
|------|------|---------|
| C.0 | Doc Cards | Create compact summaries for efficient processing |
| C.1 | Coarse Bucketing | Group by `domain__pattern` (deterministic) |
| C.2 | Tag Enrichment | AI fills missing domain/pattern tags |
| C.3 | Incremental Clustering | AI groups similar docs within buckets |
| C.4 | Merge & Purity | Consolidate related clusters, split large impure ones |
| C.5 | Representatives | Select best docs from each cluster for synthesis |

### Phase D: Skill Synthesis
**What**: Generate complete skill packages using Claude Opus
**Input**: Cluster manifest + representative extraction JSONs
**Output**: Skill folder with SKILL.md, references/, scripts/, assets/

---

## Key Concepts

### SR-PTD (Skill-Ready Post-Task Documentation)
Structured documentation format with sections:
- **A**: Trigger Profile (what initiated the task)
- **B**: Context & Inputs
- **C**: Workflow (step-by-step process)
- **D-F**: Knowledge, Code, Outputs
- **G**: Issues & Fixes
- **H-I**: Verification, Skill Assessment
- **J**: Tags

### Doc Cards
Compact (~2KB) summaries of full extractions (~20KB) containing only what's needed for clustering: scores, tags, triggers, top workflow steps.

### Incremental Clustering Algorithm
Avoids expensive O(n^2) pairwise comparisons:
1. Maintain cluster signatures (name, description, top tags)
2. For each doc: "Assign to existing cluster or create new?"
3. Use tag overlap scoring to prioritize relevant clusters

### Representative Selection
Scoring based on:
- Priority score (extraction priority)
- Reusability score (assessment dimensions)
- Coverage contribution (issues, code, artifacts)

Goal: Select 3-8 docs that collectively cover the cluster's knowledge.

---

## Data Flow

```
srptd_raw/           Phase B extractions/       Phase C clusters/
    |                     |                          |
    v                     v                          v
*.md files  ------>  *.json files  ------>  doc_cards/
(93 raw)             (140 extracted)         buckets/
                                             buckets_enriched/
                                             clusters_incremental/
                                             clusters_final/  (15 clusters)
                                             representatives/  (69 reps)
                                                  |
                                                  v
                                           Phase D skills_out/
                                                  |
                                                  v
                                           skill-name/
                                             SKILL.md
                                             references/
                                             scripts/
                                             assets/
                                             traceability.json
```

---

## Why Two Layers?

**Layer 1 (Deterministic)**:
- 100% reproducible
- Fast execution
- No API costs
- Handles format variations

**Layer 2 (AI-Assisted)**:
- Semantic understanding for clustering
- Natural language synthesis
- Bounded scope (only used where needed)

---

## Quality Gates

1. **Tag Enrichment**: Reduces "unknown" bucket to 0
2. **Purity Audit**: Ensures clusters are cohesive, splits large impure ones
3. **Sanity Check**: Validates all representatives resolve, coverage exists
4. **Traceability**: Every skill element traces back to source documents

---

## Output: Claude Skill Structure

```
skill-name/
  SKILL.md              # Main documentation (triggers, workflow, examples)
  references/           # Deep knowledge, troubleshooting guides
  scripts/              # Reusable code templates
  assets/               # Config templates, test data
  traceability.json     # Links to source SR-PTD documents
```

Each skill is designed for Claude Code to use when matching triggers are detected in user requests.
