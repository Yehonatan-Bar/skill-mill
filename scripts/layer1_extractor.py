"""
Layer 1 SR-PTD Extractor - Deterministic JSON extraction from SR-PTD markdown files.

This module parses SR-PTD (Skill-Ready Post-Task Documentation) files and extracts
structured JSON data without using any LLM. It supports:
- Full SR-PTD format (Sections A-J)
- Quick Capture format
- Legacy task_doc_ format

Output JSON schema is designed for downstream processing and skill extraction.

Usage:
    # Process single file
    python layer1_extractor.py path/to/file.md -o extractions/

    # Process directory
    python layer1_extractor.py path/to/srptd_raw/ -o extractions/

    # With pretty console output
    python layer1_extractor.py path/to/file.md --pretty
"""

import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

# Import config if available, otherwise use defaults
try:
    from config import PipelineConfig
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False


# =============================================================================
# Data Classes for Extraction Schema
# =============================================================================

@dataclass
class Metadata:
    date: Optional[str] = None
    task_id: Optional[str] = None
    task_type: Optional[str] = None
    domain: Optional[str] = None
    complexity: Optional[str] = None
    time_spent: Optional[str] = None
    repo_branch: Optional[str] = None


@dataclass
class Trigger:
    what_triggered: Optional[str] = None
    keywords_phrases: list[str] = field(default_factory=list)
    context_markers: list[str] = field(default_factory=list)
    draft_skill_trigger: Optional[str] = None


@dataclass
class ContextInputs:
    problem_statement: Optional[str] = None
    starting_state: Optional[str] = None
    environment: Optional[str] = None
    constraints: Optional[str] = None
    objective: Optional[str] = None
    requirements: Optional[str] = None
    success_criteria: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    workflow_type: Optional[str] = None
    high_level_steps: list[str] = field(default_factory=list)
    detailed_step_log: list[dict] = field(default_factory=list)
    decision_points: list[dict] = field(default_factory=list)


@dataclass
class CodeBlock:
    language: Optional[str] = None
    code: str = ""
    heading: Optional[str] = None
    reuse_flag: bool = False
    notes: Optional[str] = None


@dataclass
class Artifact:
    name: Optional[str] = None
    artifact_type: Optional[str] = None
    path_hint: Optional[str] = None
    template_potential: bool = False
    notes: Optional[str] = None


@dataclass
class IssueItem:
    issue: Optional[str] = None
    cause: Optional[str] = None
    fix: Optional[str] = None
    prevention: Optional[str] = None
    references: list[str] = field(default_factory=list)


@dataclass
class Tags:
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    safety_risk: Optional[str] = None


@dataclass
class SkillAssessment:
    reusability_score: Optional[int] = None
    frequency_score: Optional[int] = None
    consistency_score: Optional[int] = None
    complexity_score: Optional[int] = None
    codifiability_score: Optional[int] = None
    toolability_score: Optional[int] = None
    extraction_priority: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class SRPTDExtraction:
    """Complete extraction schema for an SR-PTD document."""
    doc_id: str
    source_path: str
    format_detected: str  # 'full', 'quick', 'legacy'
    metadata: Metadata = field(default_factory=Metadata)
    trigger: Trigger = field(default_factory=Trigger)
    context_inputs: ContextInputs = field(default_factory=ContextInputs)
    workflow: Workflow = field(default_factory=Workflow)
    knowledge_accessed: dict = field(default_factory=lambda: {"sources": [], "notes": None})
    code_written: dict = field(default_factory=lambda: {"blocks": []})
    outputs_produced: dict = field(default_factory=lambda: {"artifacts": []})
    issues_and_fixes: dict = field(default_factory=lambda: {"items": []})
    verification: dict = field(default_factory=lambda: {"checks": [], "expected_results": []})
    skill_assessment: SkillAssessment = field(default_factory=SkillAssessment)
    tags: Tags = field(default_factory=Tags)
    raw_sections: dict = field(default_factory=dict)
    parse_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert nested dataclass instances
        result['metadata'] = asdict(self.metadata)
        result['trigger'] = asdict(self.trigger)
        result['context_inputs'] = asdict(self.context_inputs)
        result['workflow'] = asdict(self.workflow)
        result['skill_assessment'] = asdict(self.skill_assessment)
        result['tags'] = asdict(self.tags)
        return result


# =============================================================================
# Normalization Utilities
# =============================================================================

def normalize_tag(tag: str) -> str:
    """Normalize a tag to lowercase with dashes."""
    tag = tag.strip().lower()
    tag = re.sub(r'\s+', '-', tag)
    tag = re.sub(r'[^\w\-]', '', tag)
    return tag


def deduplicate_list(items: list) -> list:
    """Remove duplicates while preserving order."""
    seen = set()
    result = []
    for item in items:
        normalized = item.lower().strip() if isinstance(item, str) else item
        if normalized not in seen:
            seen.add(normalized)
            result.append(item)
    return result


def generate_doc_id(source_path: str, content: str) -> str:
    """Generate a unique document ID from path and content hash."""
    filename = Path(source_path).stem
    content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"{filename}_{content_hash}"


# =============================================================================
# Section Detection and Parsing
# =============================================================================

class SectionParser:
    """Parser for detecting and extracting sections from SR-PTD documents."""

    # Section heading patterns for different formats
    FULL_SECTION_PATTERNS = {
        'header': r'^#\s*(?:Section\s*A[:.]?|SR-PTD|Task Doc).*?(?:Header|Skill Trigger)',
        'context': r'^(?:##\s*(?:Section\s*B[:.]?|Context|Inputs)|##\s*Problem Statement)',
        'workflow': r'^##\s*(?:Section\s*C[:.]?|Workflow|Work Performed)',
        'knowledge': r'^##\s*(?:Section\s*D[:.]?|Knowledge|Knowledge Used|Knowledge Accessed)',
        'code': r'^##\s*(?:Section\s*E[:.]?|Code|Code Written)',
        'outputs': r'^##\s*(?:Section\s*F[:.]?|Output|Artifacts|Files)',
        'issues': r'^##\s*(?:Section\s*G[:.]?|Issue|Issues|Problems)',
        'verification': r'^##\s*(?:Section\s*H[:.]?|Verification|Validation|Test)',
        'skill_assessment': r'^##\s*(?:Section\s*I[:.]?|Skill.*Assessment|Reusability)',
        'tags': r'^##\s*(?:Section\s*J[:.]?|Tags)',
    }

    # Quick capture has simpler headers
    QUICK_SECTION_PATTERNS = {
        'trigger': r'^##\s*Trigger',
        'workflow': r'^##\s*Workflow',
        'decisions': r'^##\s*Key Decisions',
        'knowledge': r'^##\s*Knowledge',
        'code': r'^##\s*Code',
        'outputs': r'^##\s*Output',
        'issues': r'^##\s*Issues',
        'skill_potential': r'^##\s*Skill Potential',
        'tags': r'^##\s*Tags',
    }

    def __init__(self, content: str):
        self.content = content
        self.lines = content.split('\n')
        self.sections = {}
        self.format = self._detect_format()

    def _detect_format(self) -> str:
        """Detect document format: 'full', 'quick', or 'legacy'."""
        content_lower = self.content.lower()

        # Check for full SR-PTD section markers
        if 'section a' in content_lower or 'skill trigger profile' in content_lower:
            return 'full'

        # Check for quick capture format indicators
        if '| **type**:' in content_lower or '**date**:' in self.content[:500]:
            # Quick capture has inline metadata header
            if '## trigger' in content_lower and '## workflow' in content_lower:
                return 'quick'

        # Check for legacy task_doc format
        if 'task doc' in content_lower or '- **date**:' in self.content[:200]:
            return 'legacy'

        # Default to quick if unclear
        return 'quick'

    def extract_sections(self) -> dict[str, str]:
        """Extract all sections with their raw text content."""
        sections = {}
        current_section = 'header'
        current_content = []

        for line in self.lines:
            # Check if line is a section header
            section_match = self._match_section_header(line)
            if section_match:
                # Save previous section
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = section_match
                current_content = [line]
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def _match_section_header(self, line: str) -> Optional[str]:
        """Match a line against section header patterns."""
        patterns = (self.FULL_SECTION_PATTERNS if self.format == 'full'
                   else self.QUICK_SECTION_PATTERNS)

        for section_name, pattern in patterns.items():
            if re.match(pattern, line, re.IGNORECASE):
                return section_name
        return None


# =============================================================================
# Content Extractors
# =============================================================================

class ContentExtractor:
    """Extracts structured data from section content."""

    @staticmethod
    def extract_metadata_from_header(content: str) -> Metadata:
        """Extract metadata from document header."""
        metadata = Metadata()

        # Pattern for inline header: **Date**: YYYY-MM-DD | **Type**: ... | **Domain**: ...
        inline_pattern = r'\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})'
        match = re.search(inline_pattern, content)
        if match:
            metadata.date = match.group(1)

        # Type extraction
        type_pattern = r'\*\*Type\*\*:\s*([^|*\n]+)'
        match = re.search(type_pattern, content)
        if match:
            metadata.task_type = match.group(1).strip()

        # Domain extraction
        domain_pattern = r'\*\*Domain(?:/Module)?\*\*:\s*([^|*\n]+)'
        match = re.search(domain_pattern, content)
        if match:
            metadata.domain = match.group(1).strip()

        # Complexity extraction
        complexity_pattern = r'\*\*Complexity\*\*:\s*(\w+)'
        match = re.search(complexity_pattern, content)
        if match:
            metadata.complexity = match.group(1).strip()

        # Time spent extraction
        time_pattern = r'\*\*Time Spent\*\*:\s*([^\n]+)'
        match = re.search(time_pattern, content)
        if match:
            metadata.time_spent = match.group(1).strip()

        # Legacy bullet point format: - **Date**: YYYY-MM-DD
        bullet_date_pattern = r'-\s*\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})'
        match = re.search(bullet_date_pattern, content)
        if match and not metadata.date:
            metadata.date = match.group(1)

        # Repo/Branch extraction
        repo_pattern = r'\*\*Repo/Branch(?:/PR/Commits)?\*\*:\s*([^\n]+)'
        match = re.search(repo_pattern, content)
        if match:
            metadata.repo_branch = match.group(1).strip()

        return metadata

    @staticmethod
    def extract_trigger(content: str) -> Trigger:
        """Extract trigger information from trigger section."""
        trigger = Trigger()

        # Blockquote trigger (> text)
        quote_pattern = r'>\s*(.+?)(?=\n(?!>)|$)'
        quotes = re.findall(quote_pattern, content, re.DOTALL)
        if quotes:
            trigger.what_triggered = ' '.join(q.strip() for q in quotes)

        # What triggered this task?
        triggered_pattern = r'\*\*What triggered[^*]*\*\*[:\s]*\n?>?\s*(.+?)(?=\n\n|\n\*\*|$)'
        match = re.search(triggered_pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            trigger.what_triggered = match.group(1).strip().lstrip('> ')

        # Keywords/Phrases extraction
        keywords_pattern = r'\*\*Keywords?[^*]*\*\*[:\s]*\n?((?:>?\s*-[^\n]+\n?)+|[^\n*]+)'
        match = re.search(keywords_pattern, content, re.IGNORECASE)
        if match:
            keywords_text = match.group(1)
            # Extract from bullet list or quoted items
            items = re.findall(r'[-*>]\s*"?([^"\n]+)"?', keywords_text)
            trigger.keywords_phrases = [k.strip(' "\'') for k in items if k.strip()]

        # Context markers extraction
        markers_pattern = r'\*\*Context Markers?\*\*[:\s]*\n?((?:>?\s*-[^\n]+\n?)+|[^\n*]+)'
        match = re.search(markers_pattern, content, re.IGNORECASE)
        if match:
            markers_text = match.group(1)
            items = re.findall(r'[-*>]\s*([^\n]+)', markers_text)
            trigger.context_markers = [m.strip() for m in items if m.strip()]

        # Draft skill trigger
        draft_pattern = r'\*\*Draft Skill Trigger\*\*[:\s]*\n?>?\s*(.+?)(?=\n\n|\n\*\*|$)'
        match = re.search(draft_pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            trigger.draft_skill_trigger = match.group(1).strip().lstrip('> ')

        return trigger

    @staticmethod
    def extract_context(content: str) -> ContextInputs:
        """Extract context and inputs information."""
        ctx = ContextInputs()

        # Objective extraction
        obj_pattern = r'\*\*Objective\*\*:\s*([^\n]+)'
        match = re.search(obj_pattern, content)
        if match:
            ctx.objective = match.group(1).strip()

        # Problem statement (can span multiple lines)
        problem_pattern = r'(?:Problem Statement|Requirements/Problem)[:\s]*\n?\*?\*?([^\n*]+(?:\n(?!\*\*)[^\n*]+)*)'
        match = re.search(problem_pattern, content, re.IGNORECASE)
        if match:
            ctx.problem_statement = match.group(1).strip()

        # Starting state
        state_pattern = r'\*\*Starting state\*\*:\s*\n?((?:\s*-[^\n]+\n?)+|[^\n*]+)'
        match = re.search(state_pattern, content, re.IGNORECASE)
        if match:
            ctx.starting_state = match.group(1).strip()

        # Environment
        env_pattern = r'\*\*Environment(?:/Versions?)?\*\*:\s*\n?((?:\s*-[^\n]+\n?)+|[^\n*]+)'
        match = re.search(env_pattern, content, re.IGNORECASE)
        if match:
            ctx.environment = match.group(1).strip()

        # Constraints
        const_pattern = r'\*\*Constraints?(?:/Dependencies)?\*\*:\s*\n?((?:\s*-[^\n]+\n?)+|[^\n*]+)'
        match = re.search(const_pattern, content, re.IGNORECASE)
        if match:
            ctx.constraints = match.group(1).strip()

        # Requirements (from Requirements/Problem field)
        req_pattern = r'\*\*Requirements?(?:/Problem)?\*\*:\s*([^\n]+)'
        match = re.search(req_pattern, content)
        if match:
            ctx.requirements = match.group(1).strip()

        return ctx

    @staticmethod
    def extract_workflow(content: str) -> Workflow:
        """Extract workflow steps and decisions."""
        wf = Workflow()

        # Workflow type
        type_pattern = r'\*\*Workflow Type\*\*:\s*(\w+)'
        match = re.search(type_pattern, content, re.IGNORECASE)
        if match:
            wf.workflow_type = match.group(1)

        # Extract numbered steps with multiple patterns
        steps = []

        # Pattern 1: Standard numbered list (1. text)
        pattern1 = re.findall(r'^\s*(\d+)\.\s+(.+?)(?=\n\s*\d+\.|$)', content, re.MULTILINE | re.DOTALL)
        for num, text in pattern1:
            # Clean up multi-line steps (keep first line or up to sub-bullet)
            clean_text = text.split('\n')[0].strip()
            if clean_text and not clean_text.startswith('-'):
                steps.append((int(num), clean_text))

        # Pattern 2: Simpler numbered pattern for single lines
        if not steps:
            pattern2 = re.findall(r'^(\d+)\.\s*(.+)$', content, re.MULTILINE)
            for num, text in pattern2:
                steps.append((int(num), text.strip()))

        # Sort by step number and deduplicate
        steps = sorted(set(steps), key=lambda x: x[0])

        for step_num, step_text in steps:
            if step_text:
                wf.high_level_steps.append(step_text)
                # Create detailed log entry
                wf.detailed_step_log.append({
                    "step_number": step_num,
                    "action": step_text,
                    "tool_command": None,
                    "input": None,
                    "output": None
                })

        # Extract decision points from tables or bullet lists
        # Pattern for table rows: | Decision | Options | Choice | Rationale |
        decision_table_pattern = r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
        decision_rows = re.findall(decision_table_pattern, content)

        for row in decision_rows:
            # Skip header rows
            if 'decision' in row[0].lower() or '---' in row[0]:
                continue
            wf.decision_points.append({
                "decision": row[0].strip(),
                "options": row[1].strip() if len(row) > 1 else None,
                "choice": row[2].strip() if len(row) > 2 else None,
                "rationale": row[3].strip() if len(row) > 3 else None
            })

        # Also extract key decisions in format: - **Decision** -> **Choice** -> **Why**
        key_decision_pattern = r'-\s*\*?\*?([^*\n]+)\*?\*?\s*->\s*([^->]+)\s*(?:->\s*(.+))?'
        key_decisions = re.findall(key_decision_pattern, content)
        for kd in key_decisions:
            wf.decision_points.append({
                "decision": kd[0].strip(),
                "choice": kd[1].strip() if len(kd) > 1 else None,
                "rationale": kd[2].strip() if len(kd) > 2 else None
            })

        return wf

    @staticmethod
    def extract_code_blocks(content: str) -> list[dict]:
        """Extract code blocks with metadata."""
        blocks = []

        # Pattern for fenced code blocks with optional language
        code_pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(code_pattern, content, re.DOTALL)

        # Track headings to associate with code blocks
        lines = content.split('\n')
        current_heading = None

        for i, line in enumerate(lines):
            if line.startswith('###'):
                current_heading = line.lstrip('#').strip()
            elif line.startswith('```'):
                # Find the matching code block
                for lang, code in matches:
                    if code.strip() in content[content.find(line):]:
                        # Check for reusability markers nearby
                        context_start = max(0, content.find(line) - 500)
                        context = content[context_start:content.find(line) + len(code) + 500]

                        reuse_flag = bool(re.search(
                            r'\[x\]\s*(?:Definitely|Likely)\s*reusable|'
                            r'reusable|'
                            r'should.*become.*skill.*\[x\]',
                            context, re.IGNORECASE
                        ))

                        blocks.append({
                            "language": lang if lang else None,
                            "code": code.strip(),
                            "heading": current_heading,
                            "reuse_flag": reuse_flag,
                            "notes": None
                        })
                        matches.remove((lang, code))
                        break

        return blocks

    @staticmethod
    def extract_artifacts(content: str) -> list[dict]:
        """Extract artifacts and outputs."""
        artifacts = []

        # Table format: | Filename | Format | Purpose | Template Potential |
        table_pattern = r'\|\s*`?([^|`]+)`?\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|(?:\s*([^|]+)\s*\|)?'
        rows = re.findall(table_pattern, content)

        for row in rows:
            name = row[0].strip()
            # Skip header rows
            if 'filename' in name.lower() or 'file' in name.lower() and 'change' in row[1].lower():
                continue
            if '---' in name:
                continue

            template_potential = False
            if len(row) > 3 and row[3]:
                template_potential = '[x]' in row[3].lower() or 'yes' in row[3].lower()

            artifacts.append({
                "name": name,
                "type": row[1].strip() if len(row) > 1 else None,
                "path_hint": None,
                "template_potential": template_potential,
                "notes": row[2].strip() if len(row) > 2 else None
            })

        # Also extract from Modified files section
        modified_pattern = r'-\s*`?([^`\n:]+(?:\.(?:py|js|ts|html|css|json|md|yaml|yml|xml))?)`?(?:\s*[-:]?\s*(.+))?'
        modified = re.findall(modified_pattern, content)

        for mod in modified:
            name = mod[0].strip()
            if name and '.' in name:  # Looks like a filename
                artifacts.append({
                    "name": name,
                    "type": "modified_file",
                    "path_hint": name,
                    "template_potential": False,
                    "notes": mod[1].strip() if len(mod) > 1 and mod[1] else None
                })

        return artifacts

    @staticmethod
    def extract_issues(content: str) -> list[dict]:
        """Extract issues and fixes."""
        issues = []

        # Skip words that indicate non-issue entries
        skip_words = [
            'tests', 'validation', 'success criteria', 'pr/diff', 'scripts',
            'snippets', 'configs', 'docs updated', 'template', 'utility',
            'storage', 'saved as', 'location', 'artifacts', 'modified files',
            'environment', 'starting state'
        ]

        def is_valid_issue(text: str) -> bool:
            """Check if text looks like a valid issue description."""
            text_lower = text.lower().strip()
            # Skip if starts with common non-issue patterns
            if text_lower.startswith('**'):
                return False
            for skip in skip_words:
                if skip in text_lower:
                    return False
            # Must have some meaningful content
            return len(text) > 5

        # Table format: | Issue | Root Cause | Fix |
        table_pattern = r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
        rows = re.findall(table_pattern, content)

        for row in rows:
            issue = row[0].strip()
            # Skip header rows and separator rows
            if 'issue' in issue.lower() or '---' in issue or 'symptom' in issue.lower():
                continue
            if not is_valid_issue(issue):
                continue

            issues.append({
                "issue": issue,
                "cause": row[1].strip() if len(row) > 1 else None,
                "fix": row[2].strip() if len(row) > 2 else None,
                "prevention": None,
                "references": []
            })

        # Also extract from bullet format within Issues section
        issues_section = re.search(
            r'##\s*Issues?[^#]*?(?=##|$)',
            content, re.IGNORECASE | re.DOTALL
        )
        if issues_section:
            issues_content = issues_section.group(0)
            bullet_pattern = r'-\s*([^->:\n]+)\s*(?:->|:)\s*([^->\n]+)(?:\s*->\s*(.+))?'
            bullets = re.findall(bullet_pattern, issues_content)

            for bullet in bullets:
                issue_text = bullet[0].strip()
                if is_valid_issue(issue_text):
                    issues.append({
                        "issue": issue_text,
                        "cause": None,
                        "fix": bullet[1].strip() if len(bullet) > 1 else None,
                        "prevention": bullet[2].strip() if len(bullet) > 2 and bullet[2] else None,
                        "references": []
                    })

        return issues

    @staticmethod
    def extract_verification(content: str) -> dict:
        """Extract verification and validation information."""
        verification = {
            "checks": [],
            "expected_results": [],
            "success_criteria_met": []
        }

        # Tests run pattern
        tests_pattern = r'-\s*([^:\n]+):\s*([^\n]+)'
        tests = re.findall(tests_pattern, content)
        for test in tests:
            verification["checks"].append({
                "test": test[0].strip(),
                "result": test[1].strip()
            })

        # Success criteria
        criteria_pattern = r'-\s*\[([x ])\]\s*(.+)'
        criteria = re.findall(criteria_pattern, content, re.IGNORECASE)
        for mark, criterion in criteria:
            verification["success_criteria_met"].append({
                "criterion": criterion.strip(),
                "met": mark.lower() == 'x'
            })

        # Expected results section
        expected_pattern = r'\*\*(?:After fix|Expected)\*\*:\s*\n?((?:-[^\n]+\n?)+)'
        match = re.search(expected_pattern, content, re.IGNORECASE)
        if match:
            results = re.findall(r'-\s*(.+)', match.group(1))
            verification["expected_results"] = [r.strip() for r in results]

        return verification

    @staticmethod
    def extract_skill_assessment(content: str) -> SkillAssessment:
        """Extract skill assessment and reusability scores."""
        assessment = SkillAssessment()

        # Extract individual scores from table
        score_patterns = {
            'frequency': r'Frequency[^|]*\|\s*(\d)',
            'consistency': r'Consistency[^|]*\|\s*(\d)',
            'complexity': r'Complexity[^|]*\|\s*(\d)',
            'codifiability': r'Codifiability[^|]*\|\s*(\d)',
            'toolability': r'Tool-?ability[^|]*\|\s*(\d)',
        }

        for field, pattern in score_patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                setattr(assessment, f'{field}_score', int(match.group(1)))

        # Total score
        total_pattern = r'(?:TOTAL|Total)[^|]*\|\s*(\d+)'
        match = re.search(total_pattern, content)
        if match:
            assessment.reusability_score = int(match.group(1))

        # Extraction priority
        priority_pattern = r'\[x\]\s*\*?\*?(\w+)\s*Priority'
        match = re.search(priority_pattern, content, re.IGNORECASE)
        if match:
            assessment.extraction_priority = match.group(1).lower()

        # Simple skill potential
        potential_pattern = r'Skill Potential:\s*(\w+)'
        match = re.search(potential_pattern, content, re.IGNORECASE)
        if match:
            potential = match.group(1).lower()
            if potential == 'high':
                assessment.extraction_priority = 'high'
            elif potential == 'medium':
                assessment.extraction_priority = 'medium'
            else:
                assessment.extraction_priority = 'low'

        # Notes
        notes_pattern = r'\*\*Notes?\*\*:\s*([^\n]+(?:\n(?!\*\*)[^\n]+)*)'
        match = re.search(notes_pattern, content, re.IGNORECASE)
        if match:
            assessment.notes = match.group(1).strip()

        return assessment

    @staticmethod
    def extract_tags(content: str) -> Tags:
        """Extract and normalize tags."""
        tags = Tags()

        # Pattern for tag lines: Languages: Python, JavaScript | Domain: ...
        # Or: **Languages**: Python, JavaScript

        # Languages
        lang_pattern = r'(?:\*\*)?Languages?(?:\*\*)?:\s*([^|\n]+)'
        match = re.search(lang_pattern, content, re.IGNORECASE)
        if match:
            raw_tags = re.split(r'[,;]', match.group(1))
            tags.languages = [normalize_tag(t) for t in raw_tags if t.strip()]

        # Frameworks
        fw_pattern = r'(?:\*\*)?Frameworks?(?:/Libs?)?(?:\*\*)?:\s*([^|\n]+)'
        match = re.search(fw_pattern, content, re.IGNORECASE)
        if match:
            raw_tags = re.split(r'[,;]', match.group(1))
            tags.frameworks = [normalize_tag(t) for t in raw_tags if t.strip()]

        # Domain
        domain_pattern = r'(?:\*\*)?Domains?(?:\*\*)?:\s*([^|\n]+)'
        match = re.search(domain_pattern, content, re.IGNORECASE)
        if match:
            raw_tags = re.split(r'[,;]', match.group(1))
            tags.domains = [normalize_tag(t) for t in raw_tags if t.strip()]

        # Services
        services_pattern = r'(?:\*\*)?(?:External\s*)?Services?(?:\*\*)?:\s*([^|\n]+)'
        match = re.search(services_pattern, content, re.IGNORECASE)
        if match:
            raw_tags = re.split(r'[,;]', match.group(1))
            tags.services = [normalize_tag(t) for t in raw_tags if t.strip() and t.strip().lower() != 'none']

        # Patterns
        pattern_pattern = r'(?:\*\*)?Patterns?(?:\*\*)?:\s*([^|\n]+)'
        match = re.search(pattern_pattern, content, re.IGNORECASE)
        if match:
            raw_tags = re.split(r'[,;]', match.group(1))
            tags.patterns = [normalize_tag(t) for t in raw_tags if t.strip()]

        # Tools (from Operational or Tools field)
        tools_pattern = r'(?:\*\*)?(?:Tools?|Operational)(?:\*\*)?:\s*([^|\n]+)'
        match = re.search(tools_pattern, content, re.IGNORECASE)
        if match:
            raw_tags = re.split(r'[,;]', match.group(1))
            tags.tools = [normalize_tag(t) for t in raw_tags if t.strip()]

        # Deduplicate all tag lists
        tags.languages = deduplicate_list(tags.languages)
        tags.frameworks = deduplicate_list(tags.frameworks)
        tags.domains = deduplicate_list(tags.domains)
        tags.services = deduplicate_list(tags.services)
        tags.patterns = deduplicate_list(tags.patterns)
        tags.tools = deduplicate_list(tags.tools)

        return tags

    @staticmethod
    def extract_knowledge(content: str) -> dict:
        """Extract knowledge accessed section."""
        knowledge = {
            "sources": [],
            "db_knowledge": None,
            "api_knowledge": None,
            "codebase_knowledge": None,
            "notes": None
        }

        # Database knowledge
        db_pattern = r'\*\*(?:DB|Database)[^*]*\*\*:\s*([^\n]+(?:\n(?!\*\*)[^\n]+)*)'
        match = re.search(db_pattern, content, re.IGNORECASE)
        if match:
            knowledge["db_knowledge"] = match.group(1).strip()
            knowledge["sources"].append({"type": "database", "detail": match.group(1).strip()})

        # API knowledge
        api_pattern = r'\*\*API[^*]*\*\*:\s*([^\n]+(?:\n(?!\*\*)[^\n]+)*)'
        match = re.search(api_pattern, content, re.IGNORECASE)
        if match:
            knowledge["api_knowledge"] = match.group(1).strip()
            knowledge["sources"].append({"type": "api", "detail": match.group(1).strip()})

        # Codebase/Code patterns
        code_pattern = r'\*\*(?:Code(?:base)?|Code patterns?)[^*]*\*\*:\s*([^\n]+(?:\n(?!\*\*)[^\n]+)*)'
        match = re.search(code_pattern, content, re.IGNORECASE)
        if match:
            knowledge["codebase_knowledge"] = match.group(1).strip()
            knowledge["sources"].append({"type": "codebase", "detail": match.group(1).strip()})

        # Extract bullet points as sources
        bullet_pattern = r'-\s*\*\*([^*]+)\*\*:\s*([^\n]+)'
        bullets = re.findall(bullet_pattern, content)
        for category, detail in bullets:
            if category.lower() not in ['db', 'database', 'api', 'code', 'codebase', 'code patterns']:
                knowledge["sources"].append({
                    "type": category.strip().lower(),
                    "detail": detail.strip()
                })

        return knowledge


# =============================================================================
# Main Extractor Class
# =============================================================================

class SRPTDExtractor:
    """Main extractor class that orchestrates the extraction process."""

    def __init__(self, source_path: str):
        self.source_path = Path(source_path)
        self.content = ""
        self.parser = None
        self.extractor = ContentExtractor()

    def load(self) -> bool:
        """Load the source file."""
        try:
            with open(self.source_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
            self.parser = SectionParser(self.content)
            return True
        except Exception as e:
            print(f"Error loading {self.source_path}: {e}")
            return False

    def extract(self) -> SRPTDExtraction:
        """Perform full extraction and return structured data."""
        if not self.content:
            self.load()

        doc_id = generate_doc_id(str(self.source_path), self.content)

        extraction = SRPTDExtraction(
            doc_id=doc_id,
            source_path=str(self.source_path),
            format_detected=self.parser.format
        )

        # Extract sections
        sections = self.parser.extract_sections()
        extraction.raw_sections = sections

        # Extract metadata from header
        header_content = sections.get('header', '') + '\n' + self.content[:1000]
        extraction.metadata = self.extractor.extract_metadata_from_header(header_content)

        # Extract context first (needed for trigger fallback)
        context_content = sections.get('context', sections.get('header', ''))
        extraction.context_inputs = self.extractor.extract_context(context_content)

        # Extract trigger
        trigger_content = sections.get('trigger', sections.get('header', ''))
        extraction.trigger = self.extractor.extract_trigger(trigger_content)

        # If no trigger found in dedicated section, check header for blockquotes
        if not extraction.trigger.what_triggered:
            quote_match = re.search(r'>\s*(.+?)(?=\n(?!>)|$)', self.content[:2000], re.DOTALL)
            if quote_match:
                extraction.trigger.what_triggered = quote_match.group(1).strip()

        # For legacy format, use Objective as trigger if no explicit trigger found
        if not extraction.trigger.what_triggered and extraction.context_inputs.objective:
            extraction.trigger.what_triggered = extraction.context_inputs.objective

        # Also try Requirements/Problem as trigger
        if not extraction.trigger.what_triggered and extraction.context_inputs.requirements:
            extraction.trigger.what_triggered = extraction.context_inputs.requirements

        # Also check for Problem Statement in separate section
        if 'problem' in sections:
            problem_ctx = self.extractor.extract_context(sections['problem'])
            if problem_ctx.problem_statement and not extraction.context_inputs.problem_statement:
                extraction.context_inputs.problem_statement = problem_ctx.problem_statement

        # Extract workflow
        workflow_content = sections.get('workflow', '')
        if not workflow_content:
            # Check for Work Performed in legacy format
            for key in sections:
                if 'work' in key.lower() or 'step' in key.lower():
                    workflow_content = sections[key]
                    break

        # For legacy format, workflow steps might be in the header section
        if not workflow_content and self.parser.format == 'legacy':
            # Look for numbered steps in raw header
            header_raw = sections.get('header', '')
            if '1. ' in header_raw:
                workflow_content = header_raw

        extraction.workflow = self.extractor.extract_workflow(workflow_content)

        # Also extract decisions from dedicated section
        if 'decisions' in sections:
            decision_wf = self.extractor.extract_workflow(sections['decisions'])
            extraction.workflow.decision_points.extend(decision_wf.decision_points)

        # Extract knowledge
        knowledge_content = sections.get('knowledge', '')
        extraction.knowledge_accessed = self.extractor.extract_knowledge(knowledge_content)

        # Extract code blocks from code section and entire document
        code_content = sections.get('code', '')
        code_blocks = self.extractor.extract_code_blocks(code_content)

        # Also extract from entire document to catch all code blocks
        all_code_blocks = self.extractor.extract_code_blocks(self.content)

        # Merge and deduplicate
        seen_codes = set()
        merged_blocks = []
        for block in code_blocks + all_code_blocks:
            code_hash = hashlib.md5(block['code'].encode()).hexdigest()
            if code_hash not in seen_codes:
                seen_codes.add(code_hash)
                merged_blocks.append(block)

        extraction.code_written = {"blocks": merged_blocks}

        # Extract artifacts/outputs
        outputs_content = sections.get('outputs', sections.get('artifacts', ''))
        # Also check Files Modified section
        for key in sections:
            if 'file' in key.lower() or 'artifact' in key.lower() or 'modified' in key.lower():
                outputs_content += '\n' + sections[key]

        extraction.outputs_produced = {"artifacts": self.extractor.extract_artifacts(outputs_content)}

        # Extract issues
        issues_content = sections.get('issues', '')
        extraction.issues_and_fixes = {"items": self.extractor.extract_issues(issues_content)}

        # Extract verification
        verification_content = sections.get('verification', '')
        extraction.verification = self.extractor.extract_verification(verification_content)

        # Also check for expected results
        for key in sections:
            if 'expected' in key.lower() or 'result' in key.lower():
                ver = self.extractor.extract_verification(sections[key])
                extraction.verification["expected_results"].extend(ver.get("expected_results", []))

        # Extract skill assessment - search entire document for scores
        assessment_content = sections.get('skill_assessment', sections.get('skill_potential', ''))
        # Also check for reusability score anywhere in the document
        for key in sections:
            if 'skill' in key.lower() or 'reusab' in key.lower() or 'tags' in key.lower():
                assessment_content += '\n' + sections[key]
        # Also scan the entire document for skill assessment tables
        if 'Dimension' in self.content and 'Score' in self.content:
            assessment_content += '\n' + self.content
        extraction.skill_assessment = self.extractor.extract_skill_assessment(assessment_content)

        # Extract tags
        tags_content = sections.get('tags', '')
        # Also check end of document for inline tags
        tags_content += '\n' + self.content[-1000:]
        extraction.tags = self.extractor.extract_tags(tags_content)

        # Generate parse warnings
        extraction.parse_warnings = self._generate_warnings(extraction)

        return extraction

    def _generate_warnings(self, extraction: SRPTDExtraction) -> list[str]:
        """Generate warnings for missing or incomplete data."""
        warnings = []

        if not extraction.metadata.date:
            warnings.append("Missing: metadata.date")

        if not extraction.trigger.what_triggered:
            warnings.append("Missing: trigger.what_triggered")

        if not extraction.workflow.high_level_steps:
            warnings.append("Missing: workflow.high_level_steps")

        if not extraction.code_written.get('blocks'):
            warnings.append("Empty: code_written.blocks")

        if not extraction.tags.languages:
            warnings.append("Missing: tags.languages")

        if not extraction.tags.domains:
            warnings.append("Missing: tags.domains")

        return warnings


# =============================================================================
# Batch Processing
# =============================================================================

def process_directory(input_dir: str, output_dir: str, pattern: str = "*.md") -> dict:
    """Process all SR-PTD files in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {
        "processed": [],
        "failed": [],
        "total": 0
    }

    # Find all matching files
    files = list(input_path.glob(pattern))
    # Also check subdirectories
    files.extend(input_path.glob(f"**/{pattern}"))

    # Filter to only SR-PTD and task_doc files
    srptd_files = [
        f for f in files
        if f.name.startswith(('SR-PTD', 'task_doc'))
    ]

    results["total"] = len(srptd_files)

    for file_path in srptd_files:
        try:
            extractor = SRPTDExtractor(str(file_path))
            if extractor.load():
                extraction = extractor.extract()

                # Save JSON output
                output_file = output_path / f"{extraction.doc_id}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(extraction.to_dict(), f, indent=2, ensure_ascii=False)

                results["processed"].append({
                    "source": str(file_path),
                    "output": str(output_file),
                    "doc_id": extraction.doc_id,
                    "format": extraction.format_detected,
                    "warnings": extraction.parse_warnings
                })
            else:
                results["failed"].append({
                    "source": str(file_path),
                    "error": "Failed to load file"
                })
        except Exception as e:
            results["failed"].append({
                "source": str(file_path),
                "error": str(e)
            })

    return results


def process_single_file(input_file: str, output_dir: str = None) -> dict:
    """Process a single SR-PTD file."""
    extractor = SRPTDExtractor(input_file)

    if not extractor.load():
        return {"error": f"Failed to load {input_file}"}

    extraction = extractor.extract()
    result = extraction.to_dict()

    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"{extraction.doc_id}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        result["_output_file"] = str(output_file)

    return result


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Command-line interface for the extractor."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Layer 1 SR-PTD Extractor - Extract structured JSON from SR-PTD markdown files"
    )

    parser.add_argument(
        "input",
        help="Input file or directory path"
    )

    parser.add_argument(
        "-o", "--output",
        default="extractions",
        help="Output directory for JSON files (default: extractions)"
    )

    parser.add_argument(
        "-p", "--pattern",
        default="*.md",
        help="File pattern for directory processing (default: *.md)"
    )

    parser.add_argument(
        "--single",
        action="store_true",
        help="Process as single file (auto-detected by default)"
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print extraction summary to console"
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_file() or args.single:
        # Single file processing
        result = process_single_file(str(input_path), args.output)

        if args.pretty:
            print(f"\n{'='*60}")
            print(f"Extracted: {result.get('doc_id', 'unknown')}")
            print(f"Format: {result.get('format_detected', 'unknown')}")
            print(f"{'='*60}")

            if result.get('metadata', {}).get('date'):
                print(f"Date: {result['metadata']['date']}")
            if result.get('metadata', {}).get('task_type'):
                print(f"Type: {result['metadata']['task_type']}")
            if result.get('trigger', {}).get('what_triggered'):
                print(f"\nTrigger: {result['trigger']['what_triggered'][:100]}...")

            steps = result.get('workflow', {}).get('high_level_steps', [])
            if steps:
                print(f"\nWorkflow ({len(steps)} steps):")
                for i, step in enumerate(steps[:5], 1):
                    print(f"  {i}. {step[:60]}...")
                if len(steps) > 5:
                    print(f"  ... and {len(steps) - 5} more steps")

            code_blocks = result.get('code_written', {}).get('blocks', [])
            if code_blocks:
                print(f"\nCode blocks: {len(code_blocks)}")
                for block in code_blocks[:3]:
                    lang = block.get('language', 'unknown')
                    reuse = '[REUSABLE]' if block.get('reuse_flag') else ''
                    print(f"  - {lang} {reuse}")

            warnings = result.get('parse_warnings', [])
            if warnings:
                print(f"\nWarnings ({len(warnings)}):")
                for w in warnings:
                    print(f"  - {w}")

            if result.get('_output_file'):
                print(f"\nSaved to: {result['_output_file']}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        # Directory processing
        results = process_directory(str(input_path), args.output, args.pattern)

        print(f"\n{'='*60}")
        print(f"SR-PTD Layer 1 Extraction Results")
        print(f"{'='*60}")
        print(f"Total files found: {results['total']}")
        print(f"Successfully processed: {len(results['processed'])}")
        print(f"Failed: {len(results['failed'])}")

        if results['processed']:
            print(f"\nProcessed files:")
            for item in results['processed']:
                warnings_str = f" ({len(item['warnings'])} warnings)" if item['warnings'] else ""
                print(f"  [{item['format']}] {Path(item['source']).name}{warnings_str}")

        if results['failed']:
            print(f"\nFailed files:")
            for item in results['failed']:
                print(f"  {Path(item['source']).name}: {item['error']}")

        # Save summary
        summary_file = Path(args.output) / "_extraction_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSummary saved to: {summary_file}")


if __name__ == "__main__":
    main()
