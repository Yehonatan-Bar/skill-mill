#!/usr/bin/env python3
"""
Skills From Docs - Project Setup Script

Sets up a new project directory with all required structure and files.

Usage:
    python setup_project.py                    # Setup in current directory
    python setup_project.py /path/to/project   # Setup in specific directory
    python setup_project.py --with-examples    # Include example SR-PTD files
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path


EXAMPLE_SRPTD = '''# SR-PTD: Example Task Documentation

## A. Trigger Profile

### What Triggered This Task
User requested help with implementing a feature

### Keywords/Phrases That Would Activate This Skill
- "implement feature"
- "add functionality"
- "create new"

### Context Markers
- Working on a Python project
- Need to add new capability

### Draft Skill Trigger
"When user asks to implement a new feature in a Python project"

---

## B. Context & Inputs

### Problem Statement
Need to add a new feature to an existing codebase

### Starting State
- Existing Python project
- Clear requirements provided

### Environment
- Python 3.10+
- Standard library

### Key Constraints
- Must be backward compatible
- Follow existing code style

---

## C. Workflow

### Workflow Type
Feature Implementation

### High-Level Steps
1. Understand requirements
2. Design solution
3. Implement code
4. Test functionality
5. Document changes

---

## D. Knowledge Accessed

- Python best practices
- Project conventions
- API documentation

---

## E. Code Written

```python
def example_function():
    """Example function demonstrating the feature."""
    return "Hello, World!"
```

**Reusable?** Yes - template for similar features

---

## F. Outputs Produced

| Output | Type | Template Potential |
|--------|------|-------------------|
| feature.py | Source code | Yes |
| tests/test_feature.py | Test file | Yes |

---

## G. Issues & Fixes

### Issue 1: Import Error
- **Cause**: Missing dependency
- **Fix**: Added to requirements.txt
- **Prevention**: Check imports early

---

## H. Verification

- [x] Feature works as expected
- [x] Tests pass
- [x] Code follows style guide

---

## I. Skill Assessment

| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| Reusability | 4 | Common pattern |
| Frequency | 4 | Often needed |
| Consistency | 4 | Standard approach |
| Complexity | 2 | Straightforward |
| Codifiability | 5 | Clear steps |

**Extraction Priority**: HIGH

---

## J. Tags

- **Domains**: python-development, feature-implementation
- **Patterns**: implementation, coding
- **Languages**: python
- **Frameworks**: none
- **Tools**: pytest
'''


CONFIG_TEMPLATE = {
    "project_root": ".",
    "srptd_raw_dir": "srptd_raw",
    "extractions_dir": "extractions",
    "clusters_dir": "clusters",
    "skills_output_dir": "skills_out",

    "model_for_enrichment": "claude-sonnet-4-20250514",
    "model_for_clustering": "claude-sonnet-4-20250514",
    "model_for_synthesis": "claude-opus-4-5-20251101",

    "domain_vocabulary": [
        "web-development",
        "api-integration",
        "data-processing",
        "automation",
        "deployment",
        "testing",
        "documentation",
    ],

    "pattern_vocabulary": [
        "implementation",
        "debugging",
        "refactoring",
        "migration",
        "configuration",
        "optimization",
    ],

    "domain_rollups": {
        "development": ["web-development", "api-integration", "backend"],
        "data": ["data-processing", "data-analysis", "etl"],
        "ops": ["deployment", "automation", "monitoring"],
    }
}


def setup_project(project_dir: Path, with_examples: bool = False):
    """Set up project structure."""

    print(f"\nSetting up Skills From Docs project at: {project_dir}\n")

    # Create directories
    dirs = [
        "srptd_raw",
        "extractions",
        "clusters",
        "skills_out",
        "logs",
    ]

    for d in dirs:
        dir_path = project_dir / d
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}/")

    # Create .env template if it doesn't exist
    env_file = project_dir / ".env"
    if not env_file.exists():
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-your-api-key-here\n")
        print(f"  Created: .env (UPDATE WITH YOUR API KEY!)")
    else:
        print(f"  Exists:  .env")

    # Create config.json
    config_file = project_dir / "config.json"
    if not config_file.exists():
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(CONFIG_TEMPLATE, f, indent=2, ensure_ascii=False)
        print(f"  Created: config.json")
    else:
        print(f"  Exists:  config.json")

    # Create .gitignore
    gitignore_file = project_dir / ".gitignore"
    if not gitignore_file.exists():
        gitignore_content = """# Skills From Docs
.env
*.pyc
__pycache__/
.pipeline_progress.json

# Output directories (optional - uncomment if you don't want to track)
# extractions/
# clusters/
# skills_out/
# logs/
"""
        gitignore_file.write_text(gitignore_content)
        print(f"  Created: .gitignore")

    # Copy scripts if not present
    scripts_src = Path(__file__).parent / "scripts"
    scripts_dst = project_dir / "scripts"

    if scripts_src.exists() and scripts_src != scripts_dst:
        if not scripts_dst.exists():
            shutil.copytree(scripts_src, scripts_dst)
            print(f"  Copied:  scripts/")
        else:
            print(f"  Exists:  scripts/")

    # Copy run_pipeline.py if not present
    runner_src = Path(__file__).parent / "run_pipeline.py"
    runner_dst = project_dir / "run_pipeline.py"

    if runner_src.exists() and runner_src != runner_dst:
        if not runner_dst.exists():
            shutil.copy(runner_src, runner_dst)
            print(f"  Copied:  run_pipeline.py")
        else:
            print(f"  Exists:  run_pipeline.py")

    # Add example SR-PTD if requested
    if with_examples:
        example_file = project_dir / "srptd_raw" / "SR-PTD_example_task.md"
        if not example_file.exists():
            example_file.write_text(EXAMPLE_SRPTD, encoding='utf-8')
            print(f"  Created: srptd_raw/SR-PTD_example_task.md")

    # Summary
    print("\n" + "=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print("""
Next Steps:

  1. UPDATE YOUR API KEY:
     Edit .env and replace 'sk-ant-your-api-key-here' with your actual key

  2. ADD YOUR DOCUMENTATION:
     Copy your SR-PTD markdown files to srptd_raw/

  3. (OPTIONAL) CUSTOMIZE CONFIG:
     Edit config.json to add your domain-specific vocabularies

  4. RUN THE PIPELINE:
     python run_pipeline.py

  For test mode (3 clusters only):
     python run_pipeline.py --test
""")


def main():
    parser = argparse.ArgumentParser(
        description="Set up a new Skills From Docs project"
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory (default: current directory)"
    )
    parser.add_argument(
        "--with-examples",
        action="store_true",
        help="Include example SR-PTD files"
    )

    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    setup_project(project_dir, with_examples=args.with_examples)


if __name__ == "__main__":
    main()
