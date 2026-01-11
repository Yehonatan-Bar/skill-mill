# Generate Skills from Claude Code Logs

This guide explains how to automatically generate reusable Claude Skills from your Claude Code CLI conversation history.

## Overview

The skills generation pipeline converts your Claude Code conversations into structured skill packages that Claude can use to assist with similar tasks in the future.

```
Claude Code Logs  -->  SR-PTD Docs  -->  Clusters  -->  Skills
  (~/.claude/)         (markdown)        (grouped)      (SKILL.md)
```

## Quick Start

### 1. First-Time Setup

Run the interactive setup wizard:

```bash
cd C:\projects\Skills\Dev_doc_for_skills\used\skills_from_docs_toolkit
python generate_skills_from_logs.py --setup
```

This will:
- Create the project directory structure
- Prompt for your Anthropic API key
- Locate your Claude Code logs
- Create configuration files

### 2. Generate Skills

After setup, generate skills from your recent conversations:

```bash
python generate_skills_from_logs.py
```

Or with options:

```bash
# Process last 7 days only
python generate_skills_from_logs.py --days 7

# Limit to 20 conversations
python generate_skills_from_logs.py --max 20

# Preview without API calls
python generate_skills_from_logs.py --dry-run

# Custom logs location
python generate_skills_from_logs.py --logs "C:/Users/you/.claude/projects"
```

### 3. Find Your Skills

Generated skills are saved to:
```
skills_out/
  skill-name/
    SKILL.md           # Main skill documentation
    references/        # Additional knowledge
    scripts/           # Reusable code templates
    assets/            # Configuration templates
```

## Command Reference

```bash
# Setup
python generate_skills_from_logs.py --setup

# Generate skills
python generate_skills_from_logs.py [options]

# List available sessions
python generate_skills_from_logs.py --list

# Options:
  --logs PATH      Path to Claude Code logs
  --days N         Process logs from last N days (default: 30)
  --max N          Maximum conversations to process (default: 50)
  --output DIR     Output directory
  --api-key KEY    Anthropic API key
  --skip-synthesis Skip Phase D (skill synthesis)
  --dry-run        Preview without API calls
  --verbose        Enable debug logging
```

## API Key Configuration

The script looks for your Anthropic API key in this order:

1. `--api-key` command line argument
2. `ANTHROPIC_API_KEY` environment variable
3. `.env` file in project directory
4. `~/.anthropic/api_key` file

### Creating a .env file

```bash
# In your project directory
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

### Using environment variable

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"

# Windows CMD
set ANTHROPIC_API_KEY=sk-ant-your-key-here

# Linux/macOS
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## Claude Code Logs Location

Claude Code stores conversation logs at:

| Platform | Location |
|----------|----------|
| Windows | `%USERPROFILE%\.claude\projects\` |
| macOS/Linux | `~/.claude/projects/` |

Each project has its own subdirectory with JSONL session files.

## Pipeline Phases

The generation process has several phases:

| Phase | Description | API Required |
|-------|-------------|--------------|
| Parse | Read Claude Code JSONL logs | No |
| Convert | Transform to SR-PTD markdown | No |
| Extract | Parse SR-PTD to JSON | No |
| Cluster | Group similar documents | Yes (Sonnet) |
| Synthesize | Generate skill packages | Yes (Opus) |

Use `--skip-synthesis` to run only the free phases.

## Logging

The script includes comprehensive logging:

### Log File Location
```
logs/skills_gen_YYYYMMDD_HHMMSS.log
```

### Log Categories

| Category | Description |
|----------|-------------|
| PARSER | Log file parsing |
| CONVERTER | SR-PTD conversion |
| PIPELINE | Orchestration |
| API_CALL | API usage tracking |
| PERF | Performance metrics |
| ERROR | Error conditions |

### Configure Logging

Edit `logging_config.json` to enable/disable categories:

```json
{
  "global_settings": {
    "log_level": "INFO"
  },
  "log_categories": {
    "PARSER": {"enabled": true},
    "DEBUG": {"enabled": false}
  }
}
```

## Troubleshooting

### "No conversations found"

1. Check logs path: `python generate_skills_from_logs.py --list`
2. Verify logs exist at `~/.claude/projects/`
3. Specify custom path: `--logs "your/path"`

### "API key not found"

1. Run setup: `python generate_skills_from_logs.py --setup`
2. Or create `.env` file with `ANTHROPIC_API_KEY=sk-ant-...`

### "Pipeline failed at Phase X"

1. Check logs in `logs/` directory
2. Use `--verbose` for debug output
3. Run with `--dry-run` to validate without API calls

### Import errors

Ensure you're running from the toolkit directory:
```bash
cd C:\projects\Skills\Dev_doc_for_skills\used\skills_from_docs_toolkit
python generate_skills_from_logs.py --setup
```

## Module Structure

```
skills_from_docs_toolkit/
  generate_skills_from_logs.py   # Main entry point
  run_pipeline.py                # Pipeline orchestrator
  scripts/
    logging_setup.py             # Logging configuration
    claude_logs_parser.py        # JSONL log parser
    log_to_srptd_converter.py    # Log to SR-PTD converter
    layer1_extractor.py          # SR-PTD to JSON
    phase_c_*.py                 # Clustering phases
    phase_d_skill_synthesis.py   # Skill generation
    config.py                    # Configuration management
```

## Example Workflow

```bash
# 1. Setup (first time only)
python generate_skills_from_logs.py --setup

# 2. Preview what will be processed
python generate_skills_from_logs.py --list

# 3. Dry run to test (no API costs)
python generate_skills_from_logs.py --days 7 --dry-run

# 4. Full generation
python generate_skills_from_logs.py --days 7

# 5. Check output
dir skills_out\
```

## Cost Estimation

The AI phases use:
- **Phase C.2-C.3**: Claude Sonnet (~$0.003/1K input, $0.015/1K output)
- **Phase D**: Claude Opus (~$0.015/1K input, $0.075/1K output)

For 50 conversations, expect approximately $2-5 in API costs.

Use `--dry-run` and `--skip-synthesis` to minimize costs during testing.
