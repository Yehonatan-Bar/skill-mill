"""
Claude Code Logs Parser - Parse JSONL conversation logs from Claude Code CLI

This module reads and parses the JSONL log files that Claude Code stores
in ~/.claude/projects/. It extracts structured conversation data suitable
for conversion to SR-PTD format.

Claude Code Log Location:
    - macOS/Linux: ~/.claude/projects/<encoded-project>/*.jsonl
    - Windows: %USERPROFILE%\\.claude\\projects\\<encoded-project>\\*.jsonl

Usage:
    from claude_logs_parser import ClaudeLogsParser

    parser = ClaudeLogsParser()
    conversations = parser.parse_directory("~/.claude/projects")

    for conv in conversations:
        print(f"Session: {conv.session_id}")
        print(f"Messages: {len(conv.messages)}")
"""

import os
import sys
import json
import base64
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterator, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib

# Import logging
try:
    from logging_setup import get_logger, LogCategory, log_performance
except ImportError:
    import logging
    def get_logger():
        return logging.getLogger(__name__)
    class LogCategory:
        PARSER = "[PARSER]"
        ERROR = "[ERROR]"
        DEBUG = "[DEBUG]"
        FILE_IO = "[FILE_IO]"
    def log_performance(op):
        def decorator(func):
            return func
        return decorator


# =============================================================================
# Data Classes
# =============================================================================

class MessageRole(Enum):
    """Role of the message sender."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    TOOL_RESULT = "tool_result"


@dataclass
class ToolUse:
    """Represents a tool invocation in the conversation."""
    tool_name: str
    tool_id: str
    parameters: Dict[str, Any]
    result: Optional[str] = None
    success: bool = True
    timestamp: Optional[datetime] = None


@dataclass
class Message:
    """Represents a single message in the conversation."""
    role: MessageRole
    content: str
    timestamp: Optional[datetime] = None
    tool_uses: List[ToolUse] = field(default_factory=list)
    thinking: Optional[str] = None
    token_count: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_substantial(self) -> bool:
        """Check if message has substantial content worth capturing."""
        if not self.content:
            return bool(self.tool_uses)
        # Filter out very short messages
        return len(self.content.strip()) > 10 or bool(self.tool_uses)


@dataclass
class Conversation:
    """Represents a complete conversation session."""
    session_id: str
    project_path: Optional[str] = None
    working_directory: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    messages: List[Message] = field(default_factory=list)
    summary: Optional[str] = None
    total_tokens: int = 0
    source_file: Optional[Path] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get conversation duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def user_messages(self) -> List[Message]:
        """Get only user messages."""
        return [m for m in self.messages if m.role == MessageRole.USER]

    @property
    def assistant_messages(self) -> List[Message]:
        """Get only assistant messages."""
        return [m for m in self.messages if m.role == MessageRole.ASSISTANT]

    @property
    def all_tool_uses(self) -> List[ToolUse]:
        """Get all tool uses across all messages."""
        tools = []
        for msg in self.messages:
            tools.extend(msg.tool_uses)
        return tools

    def get_unique_tools(self) -> List[str]:
        """Get list of unique tool names used."""
        return list(set(tu.tool_name for tu in self.all_tool_uses))

    def estimate_complexity(self) -> str:
        """Estimate task complexity based on conversation metrics."""
        msg_count = len(self.messages)
        tool_count = len(self.all_tool_uses)
        unique_tools = len(self.get_unique_tools())

        if msg_count > 30 or tool_count > 20 or unique_tools > 5:
            return "High"
        elif msg_count > 15 or tool_count > 10 or unique_tools > 3:
            return "Medium"
        return "Low"


# =============================================================================
# Log Entry Parsers
# =============================================================================

class LogEntryParser:
    """Parse individual JSONL log entries."""

    # Known message types in Claude Code logs
    MESSAGE_TYPES = {
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
        "tool_use": MessageRole.TOOL,
        "tool_result": MessageRole.TOOL_RESULT,
    }

    def __init__(self):
        self.logger = get_logger()

    def parse_entry(self, entry: Dict[str, Any]) -> Optional[Message]:
        """
        Parse a single log entry into a Message.

        Args:
            entry: Parsed JSON object from JSONL line

        Returns:
            Message object or None if entry is not a message
        """
        try:
            # Handle different entry formats
            if "type" in entry:
                return self._parse_typed_entry(entry)
            elif "role" in entry:
                return self._parse_role_entry(entry)
            elif "message" in entry:
                return self._parse_nested_message(entry)
            elif "content" in entry:
                return self._parse_content_entry(entry)
            else:
                self.logger.debug(f"{LogCategory.DEBUG} Unknown entry format: {list(entry.keys())}")
                return None
        except Exception as e:
            self.logger.warning(f"{LogCategory.PARSER} Failed to parse entry: {e}")
            return None

    def _parse_typed_entry(self, entry: Dict[str, Any]) -> Optional[Message]:
        """Parse entry with explicit type field."""
        entry_type = entry.get("type", "").lower()

        if entry_type in ("human", "user"):
            return self._create_message(
                role=MessageRole.USER,
                content=self._extract_content(entry),
                entry=entry
            )
        elif entry_type in ("assistant", "ai"):
            return self._create_message(
                role=MessageRole.ASSISTANT,
                content=self._extract_content(entry),
                entry=entry,
                tool_uses=self._extract_tool_uses(entry),
                thinking=entry.get("thinking")
            )
        elif entry_type == "tool_use":
            tool_use = ToolUse(
                tool_name=entry.get("name", entry.get("tool_name", "unknown")),
                tool_id=entry.get("id", entry.get("tool_id", "")),
                parameters=entry.get("input", entry.get("parameters", {}))
            )
            return self._create_message(
                role=MessageRole.TOOL,
                content=f"Tool: {tool_use.tool_name}",
                entry=entry,
                tool_uses=[tool_use]
            )
        elif entry_type == "tool_result":
            return self._create_message(
                role=MessageRole.TOOL_RESULT,
                content=self._extract_content(entry),
                entry=entry
            )
        elif entry_type == "summary":
            # Session summary - not a message but useful metadata
            return None
        elif entry_type == "init":
            # Session initialization
            return None

        return None

    def _parse_role_entry(self, entry: Dict[str, Any]) -> Optional[Message]:
        """Parse entry with role field."""
        role_str = entry.get("role", "").lower()
        role = self.MESSAGE_TYPES.get(role_str)

        if role:
            return self._create_message(
                role=role,
                content=self._extract_content(entry),
                entry=entry,
                tool_uses=self._extract_tool_uses(entry),
                thinking=entry.get("thinking")
            )
        return None

    def _parse_nested_message(self, entry: Dict[str, Any]) -> Optional[Message]:
        """Parse entry with nested message object."""
        message = entry.get("message", {})
        if isinstance(message, dict):
            return self.parse_entry(message)
        elif isinstance(message, str):
            # Message content is directly in the field
            return self._create_message(
                role=MessageRole.USER,  # Assume user if not specified
                content=message,
                entry=entry
            )
        return None

    def _parse_content_entry(self, entry: Dict[str, Any]) -> Optional[Message]:
        """Parse entry with only content field."""
        content = self._extract_content(entry)
        if content:
            # Try to infer role from content or other fields
            role = MessageRole.USER
            if entry.get("isAssistant") or "assistant" in str(entry.get("sender", "")).lower():
                role = MessageRole.ASSISTANT

            return self._create_message(
                role=role,
                content=content,
                entry=entry
            )
        return None

    def _extract_content(self, entry: Dict[str, Any]) -> str:
        """Extract text content from various entry formats."""
        # Direct content field
        if isinstance(entry.get("content"), str):
            return entry["content"]

        # Content as list of objects
        if isinstance(entry.get("content"), list):
            parts = []
            for item in entry["content"]:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_use":
                        parts.append(f"[Tool: {item.get('name', 'unknown')}]")
            return "\n".join(parts)

        # Base64 encoded content
        if entry.get("content_base64"):
            try:
                return base64.b64decode(entry["content_base64"]).decode('utf-8')
            except Exception:
                pass

        # Message field
        if isinstance(entry.get("message"), str):
            return entry["message"]

        # Text field
        if entry.get("text"):
            return entry["text"]

        return ""

    def _extract_tool_uses(self, entry: Dict[str, Any]) -> List[ToolUse]:
        """Extract tool use invocations from entry."""
        tools = []

        # Content array with tool_use items
        if isinstance(entry.get("content"), list):
            for item in entry["content"]:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tools.append(ToolUse(
                        tool_name=item.get("name", "unknown"),
                        tool_id=item.get("id", ""),
                        parameters=item.get("input", {})
                    ))

        # Tool uses array
        if entry.get("tool_uses"):
            for tu in entry["tool_uses"]:
                tools.append(ToolUse(
                    tool_name=tu.get("name", tu.get("tool_name", "unknown")),
                    tool_id=tu.get("id", tu.get("tool_id", "")),
                    parameters=tu.get("input", tu.get("parameters", {}))
                ))

        return tools

    def _create_message(
        self,
        role: MessageRole,
        content: str,
        entry: Dict[str, Any],
        tool_uses: List[ToolUse] = None,
        thinking: str = None
    ) -> Message:
        """Create a Message object from parsed data."""
        timestamp = None
        if entry.get("timestamp"):
            try:
                ts = entry["timestamp"]
                if isinstance(ts, (int, float)):
                    timestamp = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
                elif isinstance(ts, str):
                    timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                pass

        return Message(
            role=role,
            content=content,
            timestamp=timestamp,
            tool_uses=tool_uses or [],
            thinking=thinking,
            token_count=entry.get("token_count") or entry.get("usage", {}).get("output_tokens"),
            raw_data=entry
        )


# =============================================================================
# Main Parser
# =============================================================================

class ClaudeLogsParser:
    """
    Parser for Claude Code JSONL log files.

    Finds and parses log files from the Claude Code CLI, extracting
    structured conversation data.
    """

    DEFAULT_LOG_LOCATIONS = [
        Path.home() / ".claude" / "projects",
        Path(os.environ.get("USERPROFILE", "")) / ".claude" / "projects",
        Path(os.environ.get("HOME", "")) / ".claude" / "projects",
    ]

    def __init__(self, log_path: Optional[Path] = None):
        """
        Initialize the parser.

        Args:
            log_path: Optional explicit path to logs. If not provided,
                     will search default locations.
        """
        self.logger = get_logger()
        self.entry_parser = LogEntryParser()
        self.log_path = self._resolve_log_path(log_path)

    def _resolve_log_path(self, log_path: Optional[Path]) -> Optional[Path]:
        """Resolve the log path, checking default locations if needed."""
        if log_path:
            path = Path(log_path).expanduser().resolve()
            if path.exists():
                self.logger.info(f"{LogCategory.CONFIG} Using log path: {path}")
                return path
            else:
                self.logger.warning(f"{LogCategory.CONFIG} Specified path does not exist: {path}")

        # Search default locations
        for default_path in self.DEFAULT_LOG_LOCATIONS:
            if default_path.exists():
                self.logger.info(f"{LogCategory.CONFIG} Found logs at: {default_path}")
                return default_path

        self.logger.warning(f"{LogCategory.CONFIG} No Claude Code logs found in default locations")
        return None

    def find_log_files(self, path: Optional[Path] = None) -> List[Path]:
        """
        Find all JSONL log files in the given path.

        Args:
            path: Directory to search (uses self.log_path if not provided)

        Returns:
            List of paths to JSONL files
        """
        search_path = path or self.log_path
        if not search_path or not search_path.exists():
            return []

        log_files = []

        if search_path.is_file() and search_path.suffix == ".jsonl":
            log_files.append(search_path)
        else:
            # Search recursively for JSONL files
            log_files = list(search_path.glob("**/*.jsonl"))

        # Sort by modification time (newest first)
        log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        self.logger.info(f"{LogCategory.PARSER} Found {len(log_files)} log files")
        return log_files

    @log_performance("Parse JSONL file")
    def parse_file(self, file_path: Path) -> Optional[Conversation]:
        """
        Parse a single JSONL log file into a Conversation.

        Args:
            file_path: Path to the JSONL file

        Returns:
            Conversation object or None if parsing fails
        """
        if not file_path.exists():
            self.logger.error(f"{LogCategory.ERROR} File not found: {file_path}")
            return None

        self.logger.info(f"{LogCategory.PARSER} Parsing: {file_path.name}")

        messages = []
        session_id = file_path.stem
        project_path = None
        working_directory = None
        summary = None
        start_time = None
        end_time = None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as e:
                        self.logger.debug(f"{LogCategory.DEBUG} Invalid JSON at line {line_num}: {e}")
                        continue

                    # Extract metadata from special entries
                    entry_type = entry.get("type", "")
                    if entry_type == "init":
                        working_directory = entry.get("cwd") or entry.get("workingDirectory")
                        project_path = entry.get("project")
                        continue
                    elif entry_type == "summary":
                        summary = entry.get("summary") or entry.get("text")
                        continue

                    # Parse regular message
                    message = self.entry_parser.parse_entry(entry)
                    if message and message.is_substantial:
                        messages.append(message)

                        # Track timestamps
                        if message.timestamp:
                            if start_time is None or message.timestamp < start_time:
                                start_time = message.timestamp
                            if end_time is None or message.timestamp > end_time:
                                end_time = message.timestamp

        except IOError as e:
            self.logger.error(f"{LogCategory.ERROR} Failed to read file {file_path}: {e}")
            return None

        if not messages:
            self.logger.debug(f"{LogCategory.DEBUG} No substantial messages in {file_path.name}")
            return None

        # Calculate total tokens
        total_tokens = sum(m.token_count or 0 for m in messages)

        conversation = Conversation(
            session_id=session_id,
            project_path=project_path,
            working_directory=working_directory,
            start_time=start_time,
            end_time=end_time,
            messages=messages,
            summary=summary,
            total_tokens=total_tokens,
            source_file=file_path
        )

        self.logger.info(
            f"{LogCategory.PARSER} Parsed {len(messages)} messages "
            f"({len(conversation.user_messages)} user, "
            f"{len(conversation.assistant_messages)} assistant, "
            f"{len(conversation.all_tool_uses)} tool uses)"
        )

        return conversation

    @log_performance("Parse all log files")
    def parse_directory(
        self,
        path: Optional[Path] = None,
        max_files: Optional[int] = None,
        min_messages: int = 3
    ) -> List[Conversation]:
        """
        Parse all JSONL files in a directory.

        Args:
            path: Directory to search (uses self.log_path if not provided)
            max_files: Maximum number of files to parse (None for all)
            min_messages: Minimum number of messages for a valid conversation

        Returns:
            List of Conversation objects
        """
        log_files = self.find_log_files(path)

        if max_files:
            log_files = log_files[:max_files]

        conversations = []
        for file_path in log_files:
            conv = self.parse_file(file_path)
            if conv and len(conv.messages) >= min_messages:
                conversations.append(conv)

        self.logger.info(
            f"{LogCategory.PARSER} Successfully parsed {len(conversations)} "
            f"conversations from {len(log_files)} files"
        )

        return conversations

    def parse_recent(
        self,
        days: int = 7,
        max_conversations: int = 50
    ) -> List[Conversation]:
        """
        Parse only recent log files.

        Args:
            days: Number of days to look back
            max_conversations: Maximum conversations to return

        Returns:
            List of recent Conversation objects
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)

        log_files = self.find_log_files()
        recent_files = [
            f for f in log_files
            if datetime.fromtimestamp(f.stat().st_mtime) > cutoff
        ]

        self.logger.info(
            f"{LogCategory.PARSER} Found {len(recent_files)} files "
            f"from the last {days} days"
        )

        return self.parse_directory(max_files=max_conversations)


# =============================================================================
# Utility Functions
# =============================================================================

def get_claude_logs_path() -> Optional[Path]:
    """Get the default Claude Code logs path for the current platform."""
    parser = ClaudeLogsParser()
    return parser.log_path


def list_available_sessions(log_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    List available conversation sessions with metadata.

    Returns:
        List of dicts with session_id, file_path, modified_time, size
    """
    parser = ClaudeLogsParser(log_path)
    files = parser.find_log_files()

    sessions = []
    for f in files:
        stat = f.stat()
        sessions.append({
            "session_id": f.stem,
            "file_path": str(f),
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_kb": stat.st_size / 1024,
            "project": f.parent.name if f.parent else None
        })

    return sessions


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Command-line interface for the parser."""
    import argparse

    parser_cli = argparse.ArgumentParser(
        description="Parse Claude Code JSONL log files"
    )
    parser_cli.add_argument(
        "path",
        nargs="?",
        help="Path to logs (default: ~/.claude/projects)"
    )
    parser_cli.add_argument(
        "--list",
        action="store_true",
        help="List available sessions"
    )
    parser_cli.add_argument(
        "--session",
        help="Parse specific session by ID"
    )
    parser_cli.add_argument(
        "--recent",
        type=int,
        metavar="DAYS",
        help="Parse logs from last N days"
    )
    parser_cli.add_argument(
        "--max",
        type=int,
        default=10,
        help="Maximum files to process"
    )
    parser_cli.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser_cli.parse_args()

    log_path = Path(args.path).expanduser() if args.path else None

    if args.list:
        sessions = list_available_sessions(log_path)
        if args.json:
            print(json.dumps(sessions, indent=2))
        else:
            print(f"\nFound {len(sessions)} sessions:\n")
            for s in sessions[:20]:
                print(f"  {s['session_id'][:40]:40} {s['modified_time'][:10]} {s['size_kb']:.1f}KB")
            if len(sessions) > 20:
                print(f"  ... and {len(sessions) - 20} more")
        return

    parser = ClaudeLogsParser(log_path)

    if args.session:
        # Find and parse specific session
        files = parser.find_log_files()
        target_file = next(
            (f for f in files if args.session in f.stem),
            None
        )
        if target_file:
            conv = parser.parse_file(target_file)
            if conv:
                _print_conversation(conv, args.json)
        else:
            print(f"Session not found: {args.session}")
        return

    if args.recent:
        conversations = parser.parse_recent(days=args.recent, max_conversations=args.max)
    else:
        conversations = parser.parse_directory(max_files=args.max)

    if args.json:
        output = []
        for conv in conversations:
            output.append({
                "session_id": conv.session_id,
                "messages": len(conv.messages),
                "tool_uses": len(conv.all_tool_uses),
                "complexity": conv.estimate_complexity(),
                "start_time": conv.start_time.isoformat() if conv.start_time else None,
            })
        print(json.dumps(output, indent=2))
    else:
        print(f"\nParsed {len(conversations)} conversations:\n")
        for conv in conversations:
            print(f"  Session: {conv.session_id[:40]}")
            print(f"    Messages: {len(conv.messages)} | Tools: {len(conv.all_tool_uses)}")
            print(f"    Complexity: {conv.estimate_complexity()}")
            if conv.summary:
                print(f"    Summary: {conv.summary[:60]}...")
            print()


def _print_conversation(conv: Conversation, as_json: bool = False):
    """Print a single conversation."""
    if as_json:
        data = {
            "session_id": conv.session_id,
            "working_directory": conv.working_directory,
            "start_time": conv.start_time.isoformat() if conv.start_time else None,
            "messages": [
                {
                    "role": m.role.value,
                    "content": m.content[:500],
                    "tool_uses": [t.tool_name for t in m.tool_uses]
                }
                for m in conv.messages
            ]
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"\nSession: {conv.session_id}")
        print(f"Directory: {conv.working_directory}")
        print(f"Messages: {len(conv.messages)}")
        print(f"Tools used: {', '.join(conv.get_unique_tools()) or 'None'}")
        print("\nConversation:")
        for msg in conv.messages[:10]:
            role = msg.role.value.upper()
            content = msg.content[:200].replace('\n', ' ')
            print(f"  [{role}] {content}...")
        if len(conv.messages) > 10:
            print(f"  ... and {len(conv.messages) - 10} more messages")


if __name__ == "__main__":
    main()
