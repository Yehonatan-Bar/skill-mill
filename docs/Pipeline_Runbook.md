# Two-Layer Pipeline Runbook: Structured Extraction First, LLM Second

This runbook tells a developer exactly how to implement a pipeline that converts a large SR-PTD documentation corpus into Claude Skills, without ever needing to send the whole corpus to a model at once.

---

## Principles to Follow

### Progressive Disclosure
- Keep always-loaded content small
- Put deep material in `references/`, `scripts/`, `assets/`
- Retrieve deep material only when needed

### Deterministic First, Model Second
- Parsing, splitting, normalization, tagging, clustering should be done without an LLM
- Use the LLM only for synthesis tasks that benefit from judgment and compression

### Traceability
- Every generated Skill must record which SR-PTDs contributed to which outputs

---

## Outputs You Will Produce

- A structured extraction JSON per SR-PTD
- Cluster manifests that group SR-PTDs into candidate Skills
- A Skill folder per accepted cluster, with:
  - `SKILL.md`
  - `references/`
  - `scripts/`
  - `assets/`
  - `traceability.json`

---

## Repository Layout

Create a repo (or root folder) with:

- `srptd_raw/` - All SR-PTD source files (Markdown)
- `extractions/` - One JSON per SR-PTD after deterministic parsing
- `clusters/` - Cluster manifests and representative doc selections
- `skills_out/` - Generated Skill folders
- `logs/` - Pipeline logs and parse warnings

---

## Phase A: Ingestion

- Copy SR-PTD docs into `srptd_raw/`
- Maintain a manifest file `srptd_manifest.json` with:
  - `doc_id`
  - `path`
  - `last_modified`
  - `hash` (content hash for change detection)

---

## Phase B: Layer 1 Extraction (Deterministic, No LLM)

### Goal

Convert each SR-PTD into a stable, machine-friendly JSON object with predictable fields.

### Build the Parser

- Detect SR-PTD structure by section headings (A-J)
  - Support full SR-PTD
  - Support Quick Capture format (if present)
- Extract each section as:
  - Raw text
  - Best-effort structured lists where possible

### Extraction JSON Schema (Minimum)

For each SR-PTD, output `extractions/<doc_id>.json` with:

- `doc_id`
- `source_path`
- `metadata` - date, task_id, domain, complexity, time_spent
- `trigger` - what_triggered, keywords_phrases, context_markers, draft_skill_trigger
- `context_inputs` - problem_statement, starting_state, environment, constraints
- `workflow` - workflow_type, high_level_steps, detailed_step_log, decision_points
- `knowledge_accessed` - sources, notes
- `code_written` - blocks (list of {language, code, heading, reuse_flag, notes})
- `outputs_produced` - artifacts (list of {name, type, path_hint, template_potential, notes})
- `issues_and_fixes` - items (list of {issue, cause, fix, prevention, references})
- `verification` - checks, expected_results
- `skill_assessment` - reusability_score, notes
- `tags` - languages, frameworks, tools, domains, patterns, safety_risk
- `parse_warnings` (list)

### Parsing Robustness Requirements

- If a section is missing, do not fail the whole document
  - Store `null` or empty list
  - Add a `parse_warnings` entry
- Keep both structured extraction and raw section text (avoids data loss)

---

## Phase C: Layer 1.5 Clustering (Still No LLM)

### Goal

Group SR-PTDs into candidate Skills using cheap signals first, embeddings second.

### Steps

1. **Build a feature string per document** - Concatenate:
   - Trigger text + keywords + context markers
   - Tags
   - Workflow high-level steps
   - Workflow type

2. **Create doc cards** - Compact summaries for clustering

3. **Coarse bucketing** - Group by primary_domain__primary_pattern

4. **AI tag enrichment** (optional) - Fill missing tags

5. **Incremental clustering** - Within-bucket clustering

6. **Cross-bucket merging** - Consolidate fragmented clusters

7. **Purity audit** - Check large clusters for splits

8. **Representative selection** - Choose best docs for synthesis

### Produce Cluster Manifests

For each cluster, write `clusters/<cluster_id>.json`:

- `cluster_id`
- `member_doc_ids`
- `top_shared_tags`
- `top_shared_trigger_phrases`
- `representatives` - Pick a small subset (center-most by embedding distance)
- `cluster_confidence` - Based on cohesion, tag overlap, and size

---

## Phase D: Layer 2 Synthesis (LLM)

### Goal

Create a Skill package per cluster, using only the extraction JSON for the representative SR-PTDs.

### Build the LLM Input

For each cluster:
- Provide:
  - Cluster manifest
  - Representative extraction JSONs
- Do not provide:
  - Entire raw SR-PTD corpus
  - Unbounded logs

### Enforce an Output Contract (Model Must Return JSON)

Require the LLM to return a single JSON object:

- `skill_name` (kebab-case)
- `description` - Activation criteria derived from triggers, clear scope boundaries
- `skill_md` - The complete `SKILL.md` text
- `references_files` - Array of `{path, contents}`
- `scripts_files` - Array of `{path, contents}`
- `assets_files` - Array of `{path, contents}`
- `traceability` - List mapping output parts to `doc_id`s

### Skill Folder Assembly

Write outputs to:
- `skills_out/<skill_name>/SKILL.md`
- `skills_out/<skill_name>/references/...`
- `skills_out/<skill_name>/scripts/...`
- `skills_out/<skill_name>/assets/...`
- `skills_out/<skill_name>/traceability.json`

### Progressive Disclosure Rules

- `SKILL.md` must be short enough to act as an onboarding guide
- Heavy material goes into:
  - `references/` for background knowledge and constraints
  - `scripts/` for reusable code and tooling
  - `assets/` for templates and output artifacts
- `SKILL.md` should link to those files rather than duplicating them

---

## Phase E: Automated Quality Gates (Pre-Merge Checks)

Implement a validator that fails the build if any of these are violated:

- **Skill activation is vague** - Description doesn't match likely user phrasing
- **Progressive disclosure violated** - SKILL.md contains large reference dumps
- **Generic filler** - Content is mostly general knowledge
- **Risk specificity missing** - High-risk steps lack explicit checks
- **Traceability missing** - No mapping from outputs to source SR-PTDs

Write validation results to `logs/quality/<skill_name>.json`.

---

## Phase F: Incremental Updates (Don't Regenerate Everything)

### Change Detection

- On each run, compute hash of each SR-PTD file
- If unchanged: Skip extraction and downstream processing
- If changed: Re-extract JSON, re-run clustering for affected docs

### Update Policy

For each new or changed SR-PTD:
- Decide:
  - Add to existing cluster and update existing Skill
  - Or create new cluster and new Skill
- Apply a triage policy:
  - Fix: Small corrections to existing Skill
  - Expand: Add meaningful new capability
  - Skip: One-off tasks that are not reusable

---

## Operational Checklist

- [ ] Confirm corpus ingestion works and produces `srptd_manifest.json`
- [ ] Confirm deterministic extraction works for all formats
- [ ] Confirm clustering produces stable clusters
- [ ] Confirm LLM synthesis runs only on representatives and returns valid JSON
- [ ] Confirm Skill assembly writes correct folder structure
- [ ] Confirm quality gates catch bad outputs
- [ ] Confirm incremental updates work (hash-based)

---

## Definition of Done

You are done when:

- `skills_out/` contains multiple Skill folders
- Each Skill has:
  - A usable `SKILL.md`
  - Supporting `references/`, `scripts/`, `assets/`
  - `traceability.json`
- Running the pipeline again with no changes produces no diffs
- Adding one new SR-PTD updates only the impacted cluster/skill
