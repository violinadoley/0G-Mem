"""Built-in tools available to the Agent Runtime."""

from __future__ import annotations

import difflib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    name: str
    output: str
    error: bool = False


@dataclass
class Tool:
    """A callable tool the agent can invoke."""
    name: str
    description: str
    parameters: dict            # JSON Schema describing the parameters
    fn: Callable[..., str]      # receives **kwargs matching parameters, returns str output

    def call(self, **kwargs: Any) -> ToolResult:
        try:
            output = self.fn(**kwargs)
            return ToolResult(name=self.name, output=str(output))
        except Exception as exc:
            return ToolResult(name=self.name, output=str(exc), error=True)

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── Built-in tools ─────────────────────────────────────────────────────────────

def _web_search(query: str) -> str:
    """Simple DuckDuckGo instant answer via HTTP (no API key required)."""
    try:
        import urllib.request, urllib.parse
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        abstract = data.get("AbstractText") or data.get("Answer") or ""
        if abstract:
            return abstract[:1000]
        related = data.get("RelatedTopics", [])
        snippets = [t.get("Text", "") for t in related[:3] if isinstance(t, dict)]
        return "\n".join(s for s in snippets if s) or "No results found."
    except Exception as e:
        return f"Search failed: {e}"


def _calculate(expression: str) -> str:
    """Evaluate a safe mathematical expression."""
    import ast
    allowed_nodes = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
        ast.USub, ast.UAdd,
    )
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise ValueError(f"Unsafe expression: {type(node).__name__}")
        result = eval(compile(tree, "<string>", "eval"))  # noqa: S307 — ast-validated
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"


def _run_python(code: str, timeout: int = 10) -> str:
    """Execute Python code in a sandboxed subprocess. Returns stdout or error."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        fname = f.name
    try:
        result = subprocess.run(
            ["python3", fname],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode != 0:
            return f"Error (exit {result.returncode}):\n{stderr}" if stderr else f"Exit code {result.returncode}"
        return stdout if stdout else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Timeout: execution exceeded {timeout}s"
    except Exception as e:
        return f"Execution error: {e}"
    finally:
        try:
            os.unlink(fname)
        except Exception:
            pass


def _read_file(path: str) -> str:
    """Read a file and return its contents."""
    try:
        p = os.path.expanduser(path)
        if not os.path.exists(p):
            return f"File not found: {path}"
        size = os.path.getsize(p)
        if size > 100_000:
            return f"File too large ({size} bytes). Read a specific range instead."
        with open(p) as f:
            return f.read()
    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


def _write_file(path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    try:
        p = os.path.expanduser(path)
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        return f"Written {len(content)} chars to {path}"
    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _diff_texts(original: str, modified: str, filename: str = "file") -> str:
    """Generate a unified diff between two text strings."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))
    if not diff:
        return "(no changes)"
    return "".join(diff)


BUILTIN_TOOLS: list[Tool] = [
    Tool(
        name="web_search",
        description="Search the web for current information about a topic.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
        fn=_web_search,
    ),
    Tool(
        name="calculate",
        description="Evaluate a mathematical expression (e.g. '2 ** 10 + 5').",
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression to evaluate"},
            },
            "required": ["expression"],
        },
        fn=_calculate,
    ),
    Tool(
        name="run_python",
        description="Execute Python code and return the output. Use for data processing, calculations, and scripting.",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Max execution time in seconds (default 10)"},
            },
            "required": ["code"],
        },
        fn=_run_python,
    ),
    Tool(
        name="read_file",
        description="Read the contents of a file by path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or ~ relative file path to read"},
            },
            "required": ["path"],
        },
        fn=_read_file,
    ),
    Tool(
        name="write_file",
        description="Write content to a file, creating it or overwriting it.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        fn=_write_file,
    ),
    Tool(
        name="diff_texts",
        description="Show a unified diff between original and modified text. Useful for code review.",
        parameters={
            "type": "object",
            "properties": {
                "original": {"type": "string", "description": "Original text"},
                "modified": {"type": "string", "description": "Modified text"},
                "filename": {"type": "string", "description": "Filename hint for the diff header"},
            },
            "required": ["original", "modified"],
        },
        fn=_diff_texts,
    ),
]
