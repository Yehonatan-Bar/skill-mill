"""
Log to SR-PTD Converter - Convert Claude Code conversations to SR-PTD format

This module takes parsed Claude Code conversations and converts them
into the SR-PTD (Skill-Ready Post-Task Documentation) markdown format
that can be processed by the Skills From Docs pipeline.

Usage:
    from log_to_srptd_converter import LogToSRPTDConverter

    converter = LogToSRPTDConverter()
    srptd_content = converter.convert(conversation)
    converter.save(srptd_content, output_dir)
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

# Import parser types
try:
    from claude_logs_parser import Conversation, Message, MessageRole, ToolUse
except ImportError:
    # Fallback for standalone testing
    pass

# Import logging
try:
    from logging_setup import get_logger, LogCategory, log_performance
except ImportError:
    import logging
    def get_logger():
        return logging.getLogger(__name__)
    class LogCategory:
        CONVERTER = "[CONVERTER]"
        ERROR = "[ERROR]"
        DEBUG = "[DEBUG]"
    def log_performance(op):
        def decorator(func):
            return func
        return decorator


# =============================================================================
# Analysis Helpers
# =============================================================================

@dataclass
class ConversationAnalysis:
    """Analysis results for a conversation."""
    task_type: str = "feature-implementation"
    primary_domain: str = "unknown"
    complexity: str = "Medium"
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    key_decisions: List[Dict[str, str]] = field(default_factory=list)
    issues_found: List[Dict[str, str]] = field(default_factory=list)
    code_blocks: List[Dict[str, str]] = field(default_factory=list)
    workflow_steps: List[str] = field(default_factory=list)
    trigger_phrases: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)


class ConversationAnalyzer:
    """Analyze conversation to extract structure for SR-PTD."""

    # Language detection patterns
    LANGUAGE_PATTERNS = {
        "python": [r"\.py\b", r"\bpython\b", r"\bpip\b", r"\bdef\s+\w+", r"\bimport\s+"],
        "javascript": [r"\.js\b", r"\bnode\b", r"\bnpm\b", r"\bconst\s+", r"\blet\s+"],
        "typescript": [r"\.ts\b", r"\.tsx\b", r"\btsc\b", r":\s*string\b", r":\s*number\b"],
        "html": [r"\.html\b", r"<html", r"<div", r"<body"],
        "css": [r"\.css\b", r"\.scss\b", r"\.sass\b"],
        "json": [r"\.json\b", r"\bjson\b"],
        "yaml": [r"\.ya?ml\b"],
        "bash": [r"\.sh\b", r"\bbash\b", r"\bchmod\b", r"\bgrep\b"],
        "sql": [r"\.sql\b", r"\bSELECT\b", r"\bINSERT\b", r"\bUPDATE\b"],
    }

    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        "fastapi": [r"\bFastAPI\b", r"\bfastapi\b", r"from fastapi"],
        "flask": [r"\bFlask\b", r"from flask"],
        "django": [r"\bDjango\b", r"from django"],
        "react": [r"\bReact\b", r"\breact\b", r"useState", r"useEffect"],
        "next.js": [r"\bnext\.js\b", r"\bNext\b", r"getServerSideProps"],
        "tailwind": [r"\btailwind\b", r"tailwindcss"],
        "pandas": [r"\bpandas\b", r"pd\.", r"DataFrame"],
        "pdfplumber": [r"\bpdfplumber\b", r"pdf\.pages"],
        "anthropic": [r"\banthropic\b", r"Anthropic", r"Claude"],
    }

    # Domain detection patterns
    DOMAIN_PATTERNS = {
        "api-development": [r"\bAPI\b", r"\bendpoint\b", r"\bREST\b", r"FastAPI", r"Flask"],
        "pdf-processing": [r"\bPDF\b", r"\bpdf\b", r"pdfplumber", r"PyPDF"],
        "data-analysis": [r"\bpandas\b", r"\bDataFrame\b", r"\bExcel\b", r"\bCSV\b"],
        "frontend": [r"\bReact\b", r"\bHTML\b", r"\bCSS\b", r"\bUI\b", r"\bdashboard\b"],
        "deployment": [r"\bIIS\b", r"\bdeploy\b", r"\bDocker\b", r"\bserver\b"],
        "ai-integration": [r"\bClaude\b", r"\bGPT\b", r"\bLLM\b", r"\bAI\b", r"\banthropic\b"],
        "testing": [r"\btest\b", r"\bpytest\b", r"\bunittest\b", r"\bspec\b"],
        "automation": [r"\bscript\b", r"\bautomat", r"\bpipeline\b", r"\bcron\b"],
    }

    # Task type detection patterns
    TASK_TYPE_PATTERNS = {
        "bug-fix": [r"\bfix\b", r"\bbug\b", r"\berror\b", r"\bissue\b", r"\bbroken\b"],
        "feature-implementation": [r"\badd\b", r"\bimplement\b", r"\bcreate\b", r"\bnew\b"],
        "refactor": [r"\brefactor\b", r"\bclean\b", r"\brestructure\b", r"\boptimize\b"],
        "configuration": [r"\bconfig\b", r"\bsetup\b", r"\bconfigure\b", r"\bsetting\b"],
        "documentation": [r"\bdoc\b", r"\bREADME\b", r"\bcomment\b", r"\bexplain\b"],
        "investigation": [r"\binvestigat\b", r"\bdebug\b", r"\banalyze\b", r"\bfind\b"],
    }

    def __init__(self):
        self.logger = get_logger()

    def analyze(self, conversation: Conversation) -> ConversationAnalysis:
        """
        Analyze a conversation to extract structured information.

        Args:
            conversation: Parsed Conversation object

        Returns:
            ConversationAnalysis with extracted data
        """
        analysis = ConversationAnalysis()

        # Combine all text for pattern matching
        all_text = self._get_all_text(conversation)

        # Detect languages
        analysis.languages = self._detect_patterns(all_text, self.LANGUAGE_PATTERNS)

        # Detect frameworks
        analysis.frameworks = self._detect_patterns(all_text, self.FRAMEWORK_PATTERNS)

        # Detect domain
        domains = self._detect_patterns(all_text, self.DOMAIN_PATTERNS)
        analysis.primary_domain = domains[0] if domains else "unknown"

        # Detect task type
        task_types = self._detect_patterns(all_text, self.TASK_TYPE_PATTERNS)
        analysis.task_type = task_types[0] if task_types else "feature-implementation"

        # Extract tools used
        analysis.tools_used = conversation.get_unique_tools()

        # Set complexity from conversation metrics
        analysis.complexity = conversation.estimate_complexity()

        # Extract workflow steps from assistant messages
        analysis.workflow_steps = self._extract_workflow_steps(conversation)

        # Extract code blocks
        analysis.code_blocks = self._extract_code_blocks(conversation)

        # Extract trigger phrases from first user message
        analysis.trigger_phrases = self._extract_trigger_phrases(conversation)

        # Extract issues and fixes
        analysis.issues_found = self._extract_issues(conversation)

        # Extract files modified from tool uses
        analysis.files_modified = self._extract_files_modified(conversation)

        # Extract key decisions
        analysis.key_decisions = self._extract_decisions(conversation)

        self.logger.debug(
            f"{LogCategory.CONVERTER} Analysis: domain={analysis.primary_domain}, "
            f"type={analysis.task_type}, complexity={analysis.complexity}"
        )

        return analysis

    def _get_all_text(self, conversation: Conversation) -> str:
        """Combine all message content for analysis."""
        parts = []
        for msg in conversation.messages:
            parts.append(msg.content)
            for tool in msg.tool_uses:
                parts.append(json.dumps(tool.parameters))
        return " ".join(parts)

    def _detect_patterns(
        self,
        text: str,
        pattern_dict: Dict[str, List[str]]
    ) -> List[str]:
        """Detect items based on regex patterns."""
        detected = []
        for item, patterns in pattern_dict.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    detected.append(item)
                    break
        return detected

    def _extract_workflow_steps(self, conversation: Conversation) -> List[str]:
        """Extract high-level workflow steps from assistant messages."""
        steps = []
        step_num = 1

        for msg in conversation.assistant_messages:
            # Look for explicit numbered steps
            numbered = re.findall(r'^\s*(\d+)\.\s+(.+)$', msg.content, re.MULTILINE)
            for num, step in numbered:
                steps.append(step.strip()[:100])

            # Look for action verbs at start of sentences
            actions = re.findall(
                r"(?:I'll|I will|Let me|Now I|First,?|Then,?|Next,?)\s+([^.!?\n]+)",
                msg.content,
                re.IGNORECASE
            )
            for action in actions:
                if len(action) > 10:
                    steps.append(action.strip()[:100])

            # Tool uses as implicit steps
            for tool in msg.tool_uses:
                tool_step = self._tool_to_step(tool)
                if tool_step:
                    steps.append(tool_step)

        # Deduplicate and limit
        seen = set()
        unique_steps = []
        for step in steps:
            normalized = step.lower().strip()[:50]
            if normalized not in seen:
                seen.add(normalized)
                unique_steps.append(step)

        return unique_steps[:15]  # Limit to 15 steps

    def _tool_to_step(self, tool: ToolUse) -> Optional[str]:
        """Convert a tool use to a workflow step description."""
        tool_descriptions = {
            "Read": "Read file",
            "Write": "Create/update file",
            "Edit": "Edit code",
            "Bash": "Execute command",
            "Glob": "Search for files",
            "Grep": "Search in files",
            "WebFetch": "Fetch web content",
            "WebSearch": "Search the web",
        }

        base = tool_descriptions.get(tool.tool_name, tool.tool_name)

        # Add context from parameters
        if tool.tool_name == "Read" and tool.parameters.get("file_path"):
            path = Path(tool.parameters["file_path"]).name
            return f"{base}: {path}"
        elif tool.tool_name == "Write" and tool.parameters.get("file_path"):
            path = Path(tool.parameters["file_path"]).name
            return f"{base}: {path}"
        elif tool.tool_name == "Bash" and tool.parameters.get("command"):
            cmd = tool.parameters["command"][:40]
            return f"{base}: {cmd}"

        return base

    def _extract_code_blocks(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Extract code blocks from messages."""
        code_blocks = []
        code_pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)

        for msg in conversation.assistant_messages:
            matches = code_pattern.findall(msg.content)
            for lang, code in matches:
                if len(code.strip()) > 20:  # Skip trivial code
                    code_blocks.append({
                        "language": lang or "text",
                        "code": code.strip()[:2000],  # Limit size
                        "reusable": len(code.strip()) > 100
                    })

        return code_blocks[:10]  # Limit to 10 blocks

    def _extract_trigger_phrases(self, conversation: Conversation) -> List[str]:
        """Extract potential trigger phrases from user messages."""
        triggers = []

        for msg in conversation.user_messages[:3]:  # Focus on first 3 user messages
            content = msg.content.strip()
            if not content:
                continue

            # Take first sentence or first 200 chars
            first_sentence = re.split(r'[.!?\n]', content)[0]
            if len(first_sentence) > 10:
                triggers.append(first_sentence[:200])

            # Extract imperative phrases
            imperatives = re.findall(
                r'\b(add|create|fix|implement|update|help|make|build|write)\b[^.!?\n]+',
                content,
                re.IGNORECASE
            )
            triggers.extend([i.strip()[:100] for i in imperatives[:3]])

        return triggers[:5]

    def _extract_issues(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Extract issues and their fixes from the conversation."""
        issues = []

        # Patterns that indicate issues
        issue_patterns = [
            r"(?:error|issue|problem|bug|failed|broken)[:\s]+([^.!?\n]+)",
            r"(?:fixing|fixed|resolved|solved)[:\s]+([^.!?\n]+)",
        ]

        for msg in conversation.messages:
            for pattern in issue_patterns:
                matches = re.findall(pattern, msg.content, re.IGNORECASE)
                for match in matches:
                    if len(match) > 10:
                        issues.append({
                            "issue": match.strip()[:200],
                            "fix": "",  # Will try to find fix in context
                        })

        return issues[:5]

    def _extract_files_modified(self, conversation: Conversation) -> List[str]:
        """Extract file paths that were modified."""
        files = set()

        for tool in conversation.all_tool_uses:
            if tool.tool_name in ("Write", "Edit", "NotebookEdit"):
                path = tool.parameters.get("file_path", "")
                if path:
                    files.add(Path(path).name)

        return list(files)[:20]

    def _extract_decisions(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Extract key decisions from the conversation."""
        decisions = []

        # Look for decision patterns in assistant messages
        decision_patterns = [
            r"I(?:'ll| will)\s+(?:use|choose|go with)\s+([^.!?\n]+)",
            r"(?:decided|choosing|selected|opted)\s+(?:to|for)\s+([^.!?\n]+)",
            r"(?:better|best|prefer)\s+(?:to|option|approach)\s+([^.!?\n]+)",
        ]

        for msg in conversation.assistant_messages:
            for pattern in decision_patterns:
                matches = re.findall(pattern, msg.content, re.IGNORECASE)
                for match in matches:
                    if len(match) > 10:
                        decisions.append({
                            "decision": match.strip()[:150],
                            "rationale": ""
                        })

        return decisions[:5]


# =============================================================================
# SR-PTD Generator
# =============================================================================

class LogToSRPTDConverter:
    """
    Convert Claude Code conversations to SR-PTD markdown format.

    The generated SR-PTD follows the full format with sections A-J,
    suitable for processing by the Skills From Docs pipeline.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize the converter.

        Args:
            output_dir: Directory to save generated SR-PTD files
        """
        self.logger = get_logger()
        self.output_dir = Path(output_dir) if output_dir else Path.cwd() / "srptd_raw"
        self.analyzer = ConversationAnalyzer()

    @log_performance("Convert conversation to SR-PTD")
    def convert(self, conversation: Conversation) -> str:
        """
        Convert a conversation to SR-PTD markdown format.

        Args:
            conversation: Parsed Conversation object

        Returns:
            SR-PTD markdown content as string
        """
        self.logger.info(
            f"{LogCategory.CONVERTER} Converting session: {conversation.session_id}"
        )

        # Analyze conversation
        analysis = self.analyzer.analyze(conversation)

        # Generate SR-PTD sections
        sections = [
            self._generate_header(conversation, analysis),
            self._generate_section_a(conversation, analysis),
            self._generate_section_b(conversation, analysis),
            self._generate_section_c(conversation, analysis),
            self._generate_section_d(conversation, analysis),
            self._generate_section_e(conversation, analysis),
            self._generate_section_f(conversation, analysis),
            self._generate_section_g(conversation, analysis),
            self._generate_section_h(conversation, analysis),
            self._generate_section_i(conversation, analysis),
            self._generate_section_j(conversation, analysis),
        ]

        content = "\n\n---\n\n".join(sections)

        self.logger.info(
            f"{LogCategory.CONVERTER} Generated {len(content)} chars of SR-PTD"
        )

        return content

    def _generate_header(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate document header."""
        date = conv.start_time.strftime("%Y-%m-%d") if conv.start_time else datetime.now().strftime("%Y-%m-%d")
        task_id = conv.session_id[:12]

        return f"""# SR-PTD: {analysis.task_type.replace('-', ' ').title()} - {analysis.primary_domain.replace('-', ' ').title()}

**Date**: {date} | **Type**: {analysis.task_type} | **Domain**: {analysis.primary_domain} | **Complexity**: {analysis.complexity}

**Session ID**: {conv.session_id}
**Working Directory**: {conv.working_directory or 'Unknown'}"""

    def _generate_section_a(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section A: Trigger Profile."""
        # Get first user message as trigger
        first_user = conv.user_messages[0] if conv.user_messages else None
        trigger_text = first_user.content[:500] if first_user else "Task initiated"

        # Format trigger phrases
        phrases = analysis.trigger_phrases or [trigger_text[:100]]
        keywords = "\n".join(f"- \"{p}\"" for p in phrases[:5])

        return f"""## Section A: Trigger Profile

### What Triggered This Task
> {trigger_text}

### Keywords/Phrases That Would Activate This Skill
{keywords}

### Context Markers
- Working in: {conv.working_directory or 'Unknown project'}
- Task type: {analysis.task_type}
- Domain: {analysis.primary_domain}

### Draft Skill Trigger
"When user asks to {analysis.task_type.replace('-', ' ')} in {analysis.primary_domain.replace('-', ' ')} context\""""

    def _generate_section_b(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section B: Context & Inputs."""
        # Extract problem from first user message
        first_user = conv.user_messages[0] if conv.user_messages else None
        problem = first_user.content[:300] if first_user else "Task requested"

        return f"""## Section B: Context & Inputs

### Problem Statement
{problem}

### Starting State
- Project directory: {conv.working_directory or 'Unknown'}
- Initial files present in workspace

### Environment
- Languages: {', '.join(analysis.languages) or 'Unknown'}
- Frameworks: {', '.join(analysis.frameworks) or 'None detected'}

### Key Constraints
- Follow existing project conventions
- Maintain compatibility with current codebase"""

    def _generate_section_c(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section C: Workflow."""
        # Format workflow steps
        steps = analysis.workflow_steps or ["Analyzed requirements", "Implemented solution", "Verified results"]
        numbered_steps = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))

        # Format decisions
        decisions = ""
        if analysis.key_decisions:
            decisions = "\n### Key Decisions\n"
            for d in analysis.key_decisions:
                decisions += f"- {d['decision']}\n"

        return f"""## Section C: Workflow

### Workflow Type
{analysis.task_type.replace('-', ' ').title()}

### High-Level Steps
{numbered_steps}
{decisions}
### Tools Used
{', '.join(analysis.tools_used) or 'Standard tools'}"""

    def _generate_section_d(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section D: Knowledge Accessed."""
        # Infer knowledge sources from content
        knowledge_sources = []
        if analysis.frameworks:
            knowledge_sources.append(f"- **Framework documentation**: {', '.join(analysis.frameworks)}")
        if analysis.languages:
            knowledge_sources.append(f"- **Language references**: {', '.join(analysis.languages)}")
        if "api" in analysis.primary_domain.lower():
            knowledge_sources.append("- **API patterns**: REST best practices")
        if "pdf" in analysis.primary_domain.lower():
            knowledge_sources.append("- **PDF processing**: Document structure handling")

        if not knowledge_sources:
            knowledge_sources = ["- General programming knowledge"]

        return f"""## Section D: Knowledge Accessed

{chr(10).join(knowledge_sources)}
- **Codebase patterns**: Existing project conventions"""

    def _generate_section_e(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section E: Code Written."""
        if not analysis.code_blocks:
            return """## Section E: Code Written

*No significant code blocks captured in this conversation.*"""

        code_sections = []
        for i, block in enumerate(analysis.code_blocks[:5], 1):
            reuse = "[REUSABLE]" if block.get("reusable") else ""
            code = block["code"]
            if len(code) > 500:
                code = code[:500] + "\n# ... (truncated)"

            code_sections.append(f"""### Code Block {i} {reuse}
```{block['language']}
{code}
```""")

        return "## Section E: Code Written\n\n" + "\n\n".join(code_sections)

    def _generate_section_f(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section F: Outputs Produced."""
        if not analysis.files_modified:
            return """## Section F: Outputs Produced

| Output | Type | Template Potential |
|--------|------|-------------------|
| (No files tracked) | - | - |"""

        rows = []
        for f in analysis.files_modified[:10]:
            ext = Path(f).suffix or ".unknown"
            file_type = {
                ".py": "Python source",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".html": "HTML template",
                ".css": "Stylesheet",
                ".json": "Configuration",
                ".md": "Documentation",
            }.get(ext, "File")
            rows.append(f"| `{f}` | {file_type} | No |")

        table = "\n".join(rows)

        return f"""## Section F: Outputs Produced

| Output | Type | Template Potential |
|--------|------|-------------------|
{table}"""

    def _generate_section_g(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section G: Issues & Fixes."""
        if not analysis.issues_found:
            return """## Section G: Issues & Fixes

*No significant issues encountered during this task.*"""

        issues_text = []
        for i, issue in enumerate(analysis.issues_found, 1):
            issues_text.append(f"""### Issue {i}
- **Problem**: {issue['issue']}
- **Fix**: {issue.get('fix') or 'Resolved during implementation'}""")

        return "## Section G: Issues & Fixes\n\n" + "\n\n".join(issues_text)

    def _generate_section_h(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section H: Verification."""
        return f"""## Section H: Verification

### Verification Performed
- [x] Solution implemented
- [x] Code reviewed in conversation
- [ ] Unit tests (if applicable)
- [ ] Manual testing

### Session Metrics
- Messages exchanged: {len(conv.messages)}
- Tools used: {len(conv.all_tool_uses)}
- Estimated complexity: {analysis.complexity}"""

    def _generate_section_i(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section I: Skill Assessment."""
        # Calculate scores based on analysis
        complexity_map = {"Low": 2, "Medium": 3, "High": 4}
        complexity_score = complexity_map.get(analysis.complexity, 3)

        reusability = 4 if len(analysis.code_blocks) > 2 else 3
        frequency = 3  # Default moderate frequency
        consistency = 4 if analysis.workflow_steps else 3
        codifiability = 5 if analysis.code_blocks else 3

        total = reusability + frequency + consistency + complexity_score + codifiability

        priority = "HIGH" if total >= 18 else "MEDIUM" if total >= 14 else "LOW"

        return f"""## Section I: Skill Assessment

| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| Reusability | {reusability} | {len(analysis.code_blocks)} code blocks |
| Frequency | {frequency} | Common pattern |
| Consistency | {consistency} | {len(analysis.workflow_steps)} workflow steps |
| Complexity | {complexity_score} | {analysis.complexity} complexity |
| Codifiability | {codifiability} | Clear implementation |
| **TOTAL** | **{total}** | |

**Extraction Priority**: {priority}"""

    def _generate_section_j(
        self,
        conv: Conversation,
        analysis: ConversationAnalysis
    ) -> str:
        """Generate Section J: Tags."""
        languages = ", ".join(analysis.languages) or "unknown"
        frameworks = ", ".join(analysis.frameworks) or "none"
        tools = ", ".join(analysis.tools_used[:5]) or "standard"
        domains = analysis.primary_domain.replace("-", ", ")
        patterns = analysis.task_type.replace("-", ", ")

        return f"""## Section J: Tags

- **Languages**: {languages}
- **Frameworks/Libs**: {frameworks}
- **Tools**: {tools}
- **Domains**: {domains}
- **Patterns**: {patterns}

---
*Auto-generated from Claude Code session: {conv.session_id}*
*Generated at: {datetime.now().isoformat()}*"""

    def save(
        self,
        content: str,
        conversation: Conversation,
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        Save SR-PTD content to a file.

        Args:
            content: SR-PTD markdown content
            conversation: Source conversation (for naming)
            output_dir: Optional output directory override

        Returns:
            Path to saved file
        """
        output_path = Path(output_dir) if output_dir else self.output_dir
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        date = conversation.start_time.strftime("%Y-%m-%d") if conversation.start_time else datetime.now().strftime("%Y-%m-%d")
        session_short = conversation.session_id[:16]
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]

        filename = f"SR-PTD_{date}_{session_short}_{content_hash}.md"
        file_path = output_path / filename

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        self.logger.info(f"{LogCategory.CONVERTER} Saved: {file_path}")

        return file_path

    def convert_and_save(
        self,
        conversation: Conversation,
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        Convert conversation and save to file.

        Args:
            conversation: Conversation to convert
            output_dir: Output directory

        Returns:
            Path to saved file
        """
        content = self.convert(conversation)
        return self.save(content, conversation, output_dir)

    @log_performance("Batch convert conversations")
    def batch_convert(
        self,
        conversations: List[Conversation],
        output_dir: Optional[Path] = None
    ) -> List[Path]:
        """
        Convert multiple conversations to SR-PTD files.

        Args:
            conversations: List of conversations to convert
            output_dir: Output directory

        Returns:
            List of paths to saved files
        """
        saved_files = []

        for conv in conversations:
            try:
                path = self.convert_and_save(conv, output_dir)
                saved_files.append(path)
            except Exception as e:
                self.logger.error(
                    f"{LogCategory.ERROR} Failed to convert {conv.session_id}: {e}"
                )

        self.logger.info(
            f"{LogCategory.CONVERTER} Batch converted {len(saved_files)}/{len(conversations)} conversations"
        )

        return saved_files


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Command-line interface for the converter."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert Claude Code logs to SR-PTD format"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input JSONL file or directory"
    )
    parser.add_argument(
        "-o", "--output",
        default="srptd_raw",
        help="Output directory for SR-PTD files"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="Maximum conversations to convert"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview conversion without saving"
    )

    args = parser.parse_args()

    # Import parser
    from claude_logs_parser import ClaudeLogsParser

    # Parse logs
    log_path = Path(args.input).expanduser() if args.input else None
    parser_instance = ClaudeLogsParser(log_path)
    conversations = parser_instance.parse_directory(max_files=args.max)

    if not conversations:
        print("No conversations found to convert.")
        return

    # Convert
    converter = LogToSRPTDConverter(Path(args.output))

    if args.preview:
        # Preview first conversation
        content = converter.convert(conversations[0])
        print(content)
    else:
        saved = converter.batch_convert(conversations, Path(args.output))
        print(f"\nConverted {len(saved)} conversations to SR-PTD format")
        print(f"Output directory: {args.output}")


if __name__ == "__main__":
    main()
