# SR-PTD Documentation System: A Comprehensive Guide

## Table of Contents

1. [Overview](#overview)
2. [Core Purpose and Philosophy](#core-purpose-and-philosophy)
3. [Document Types](#document-types)
4. [Full Template Structure (Sections A-J)](#full-template-structure-sections-a-j)
5. [Quick Capture Template](#quick-capture-template)
6. [Naming Convention and Storage](#naming-convention-and-storage)
7. [How SR-PTD Maps to Claude Skills](#how-sr-ptd-maps-to-claude-skills)
8. [Skill Extraction Assessment](#skill-extraction-assessment)
9. [Skill Update Protocol](#skill-update-protocol)
10. [Best Practices](#best-practices)

---

## Overview

**SR-PTD** (Skill-Ready Post-Task Documentation) is a structured documentation framework designed to capture comprehensive knowledge from completed development tasks. Its primary purpose is to create a repository of reusable knowledge that can eventually be transformed into Claude Skills - automated workflows that Claude can execute when similar tasks arise.

The system operates on a fundamental principle: **Every task completed is a potential Skill waiting to be extracted.**

### Key Characteristics

| Aspect | Description |
|--------|-------------|
| **Mandatory** | Documentation is required after EVERY development task |
| **Structured** | Follows a consistent template with defined sections |
| **Skill-Oriented** | Designed to map directly to Claude Skill architecture |
| **Aggregatable** | Tags and structure enable clustering related tasks |
| **Living** | Documents are updated if the conversation continues |

---

## Core Purpose and Philosophy

### The Documentation-to-Skill Pipeline

```
Task Completed --> SR-PTD Document --> Pattern Recognition --> Skill Extraction
                        |                     |
                        v                     v
                   Knowledge Base       3-5 Similar Tasks
                        |                     |
                        v                     v
                   Future Reference      New Claude Skill
```

### Why This System Exists

1. **Knowledge Preservation**: Captures exact workflows, decisions, and code before they're forgotten
2. **Pattern Discovery**: Accumulating similar documents reveals reusable patterns
3. **Skill Building**: Provides raw material for creating automated Claude Skills
4. **Future Reference**: Serves as a searchable knowledge base for similar future tasks
5. **Quality Assurance**: Forces thorough reflection on work completed

---

## Document Types

### 1. Full SR-PTD (Sections A-J)

**Use for:**
- Complex, multi-step implementations
- Tasks likely to become skills (high reusability)
- New feature development
- System integrations
- Multi-file changes

**Structure:** 10 comprehensive sections covering every aspect of the task

### 2. Quick Capture Template

**Use for:**
- Simpler tasks
- Bug fixes
- Routine maintenance
- Quick configuration changes
- Tasks with low skill potential

**Structure:** Condensed single-page format with essential information

### Selection Criteria

| If the task... | Use... |
|----------------|--------|
| Takes > 1 hour | Full Template |
| Involves multiple files | Full Template |
| Creates reusable code | Full Template |
| Is a simple bug fix | Quick Capture |
| Is routine maintenance | Quick Capture |
| Has unclear skill potential | Start with Quick, expand if needed |

---

## Full Template Structure (Sections A-J)

### Section A: Header and Skill Trigger Profile

**Purpose:** Identify the task and capture what would trigger similar work in the future.

**Contents:**
- **Metadata**: Date, Task ID, Type, Domain/Module, Complexity, Time Spent
- **Skill Trigger Profile**: The exact request/problem that initiated the task
- **Keywords/Phrases**: Words that indicated this type of work was needed
- **Context Markers**: File types, systems touched, domain concepts
- **Draft Skill Trigger**: A proposed description for when this skill should activate

### Section B: Context and Inputs

**Purpose:** Document the starting state, requirements, and constraints.

**Contents:**
- **Problem Statement**: Objective, business value, success criteria
- **Starting State**: Files received, existing code, relevant tickets
- **Environment**: Runtime, tool versions, dependencies
- **Constraints and Dependencies**: Deadlines, external dependencies, blockers

### Section C: Workflow Executed

**Purpose:** Capture the exact steps taken to complete the task - this becomes the SKILL.md body.

**Contents:**
- **Workflow Type**: Sequential, Conditional, Iterative, or Hybrid
- **High-Level Steps**: Numbered list of major actions
- **Detailed Step Log**: For each step:
  - Action taken
  - Tool/Command used (with exact code)
  - Input received
  - Output produced
  - Decisions made
- **Decision Points**: Table of choices made with rationale

### Section D: Knowledge Accessed

**Purpose:** Document all knowledge required to complete the task - becomes references/ folder content.

**Contents:**
- **Database/Data Knowledge**: Tables queried, SQL written, schema knowledge
- **API Knowledge**: Endpoints called, request/response patterns
- **Codebase Knowledge**: Files read/modified, patterns followed
- **Documentation/External Knowledge**: Docs consulted, domain knowledge applied

### Section E: Code Written/Used

**Purpose:** Capture all code created - becomes scripts/ folder content.

**Contents:**
- **New Code Created**: For each script/function:
  - Purpose (one line)
  - Reusability assessment (One-time / Likely reusable / Definitely reusable)
  - Full code or key sections
  - "Should this become a skill script?" flag
- **Existing Code Reused**: Source, modifications made
- **Code That Should Be Extracted**: Functionality that deserves its own script

### Section F: Outputs Produced

**Purpose:** Document all artifacts created - becomes assets/ folder content.

**Contents:**
- **Files Created**: Filename, format, purpose, template potential
- **Output Patterns/Formats**: Structure of any standardized outputs
- **Generated Artifacts**: Reports, data files, configs

### Section G: Issues and Fixes

**Purpose:** Document problems encountered and how they were solved.

**Contents:**
- **Issues Encountered**: For each issue:
  - Symptom (what went wrong)
  - Root Cause (why it happened)
  - Fix Applied (what was done)
  - Prevention (how to avoid in future)

### Section H: Verification and Validation

**Purpose:** Document how the work was tested and validated.

**Contents:**
- **Tests Run**: Table of test types, results
- **Validation Evidence**: Screenshots, logs, metrics
- **Success Criteria Verification**: Each criterion with met/not-met status

### Section I: Skill Extraction Assessment

**Purpose:** Evaluate whether this task should become a Claude Skill.

**Contents:**
- **Reusability Score**: 5-dimension scoring system
- **Extraction Recommendation**: High/Medium/Low priority
- **Proposed Skill Structure**: Directory layout if extracting

### Section J: Tags and Storage

**Purpose:** Enable aggregation and future discovery.

**Contents:**
- **Tags**: Languages, Frameworks, Domains, Patterns
- **Related Documents**: Previous similar tasks
- **Storage**: Filename and location

---

## Quick Capture Template

```markdown
# SR-PTD - [Brief Description]

**Date**: YYYY-MM-DD | **Type**: Feature | Bug Fix | Maintenance | **Domain**: | **Complexity**: Low | Medium | High

## Trigger
> [What request/problem initiated this?]

## Workflow (numbered steps)
1.
2.
3.

## Key Decisions
- [Decision] -> [Choice] -> [Why]

## Knowledge Used
- **DB**:
- **API**:
- **Code patterns**:

## Code Written (if reusable)
```python
```

## Output Format (if templatable)
```
```

## Issues -> Fixes
- [Issue] -> [Fix]

## Skill Potential: Low | Medium | High
**Notes**:

## Tags
Languages: | Domain: | Services:
```

---

## Naming Convention and Storage

### File Naming Format

```
SR-PTD_YYYY-MM-DD_[task-id]_[brief-description].md
```

**Components:**
- `SR-PTD_` - Fixed prefix identifying the document type
- `YYYY-MM-DD` - Date of task completion
- `[task-id]` - Ticket number, request ID, or descriptive identifier
- `[brief-description]` - Kebab-case summary of the task

**Examples:**
```
SR-PTD_2025-12-21_excel-insights-overview-modal.md
SR-PTD_2025-12-18_claude-client-module_implement-anthropic-api-wrapper.md
```

---

## How SR-PTD Maps to Claude Skills

| SR-PTD Section | Skill Component | Extraction Value |
|----------------|-----------------|------------------|
| **Section A: Trigger Profile** | YAML `description` | What activates this skill? |
| **Section C: Workflow Executed** | SKILL.md body | Step-by-step process |
| **Section D: Knowledge Accessed** | `references/` | Schemas, APIs, docs |
| **Section E: Code Written** | `scripts/` | Reusable scripts |
| **Section F: Outputs Produced** | `assets/` | Templates, formats |

### Skill Directory Structure

```
[skill-name]/
+-- SKILL.md
|   +-- [Workflow from Section C]
+-- scripts/
|   +-- [Code from Section E marked as reusable]
+-- references/
|   +-- schema.md      <- [DB knowledge from Section D]
|   +-- api.md         <- [API knowledge from Section D]
+-- assets/
    +-- [Templates from Section F]
```

---

## Skill Extraction Assessment

### Reusability Scoring System

Rate each dimension from 1-5:

| Dimension | Question | Score Guide |
|-----------|----------|-------------|
| **Frequency** | How often will similar tasks occur? | 1=Rare, 5=Daily |
| **Consistency** | Is the workflow stable or variable? | 1=Variable, 5=Always the same |
| **Complexity** | Would Claude benefit from guidance? | 1=Simple, 5=Complex |
| **Codifiability** | Can steps be clearly documented? | 1=Hard, 5=Very clear |
| **Tool-ability** | Are there scripts worth bundling? | 1=No code, 5=Multiple scripts |

### Extraction Recommendations

| Total Score | Priority | Action |
|-------------|----------|--------|
| **20-25** | High Priority | Create skill soon |
| **12-19** | Medium Priority | Accumulate more examples |
| **< 12** | Low Priority | Keep as reference only |

---

## Skill Update Protocol

### Update Types

| Type | Trigger | Action |
|------|---------|--------|
| **Type A: Fix** | Script failed, edge case found | Update skill |
| **Type B: Expand** | New capability discovered | Add to skill |
| **Type C: Skip** | Skill worked as documented | No update |

---

## Best Practices

1. **Document Immediately**: Create SR-PTD right after task completion
2. **Be Specific**: Include exact commands and code snippets
3. **Capture Rationale**: Document not just what, but why
4. **Mark Reusability**: Use checkboxes to flag reusable components
5. **Use Consistent Tags**: Maintain vocabulary for aggregation
6. **Update Don't Duplicate**: One document per session
7. **Score Honestly**: Low scores are valuable information

---

**Document Version:** 1.0
