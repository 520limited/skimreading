"""Validate that equations in user-facing Markdown use renderable MathJax form."""

from __future__ import annotations

import re
from dataclasses import dataclass


FENCED_CODE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|$)", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)|!\[\[[^\]]+\]\]")
MATH_RE = re.compile(
    r"(?<!\\)\$\$(?P<block>.*?)(?<!\\)\$\$|"
    r"(?<!\\)\$(?!\$)(?P<inline>[^$\n]+?)(?<!\\)\$",
    re.DOTALL,
)
UNESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)\$")
ALT_MATH_DELIMITER_RE = re.compile(r"\\\(|\\\)|\\\[|\\\]")
RAW_LATEX_RE = re.compile(
    r"\\(?:frac|dfrac|tfrac|sqrt|sum|prod|int|begin|end|left|right|"
    r"mathbf|mathbb|mathrm|operatorname|alpha|beta|gamma|lambda|theta|Delta|"
    r"cdot|times|leq|geq|approx)\b"
)
RAW_SCRIPT_RE = re.compile(
    r"(?<![\w])(?:[A-Za-zΑ-Ωα-ω]|[A-Za-z][A-Za-z0-9]*)[_^]"
    r"(?:\{[^}\n]+\}|[A-Za-z0-9])"
)
CODE_MATH_SCRIPT_RE = re.compile(r"(?<![\w])[A-Za-zΑ-Ωα-ω][_^](?:\{[^}\n]+\}|[A-Za-z0-9])")
RAW_EQUATION_RE = re.compile(
    r"(?<![\w])(?:[A-Za-zΑ-Ωα-ω](?:_[A-Za-z0-9{}-]+)?)\s*=\s*"
    r"(?:[A-Za-z0-9Α-Ωα-ω({\\])"
)
RAW_EXPONENT_RE = re.compile(r"\b[eE]\s*\^\s*[({]")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass(frozen=True)
class MathSpan:
    content: str
    display: bool
    line: int
    start: int
    end: int


def _blank_matches(value: str, pattern: re.Pattern[str]) -> str:
    chars = list(value)
    for match in pattern.finditer(value):
        for index in range(match.start(), match.end()):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _balanced(value: str, opening: str, closing: str) -> bool:
    depth = 0
    escaped = False
    for char in value:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _formula_errors(span: MathSpan) -> list[str]:
    errors: list[str] = []
    content = span.content.strip()
    if not content:
        errors.append(f"empty MathJax expression at markdown line {span.line}")
        return errors
    if any(marker in content for marker in ("�", "锟斤拷")):
        errors.append(f"MathJax expression contains mojibake at markdown line {span.line}")
    for opening, closing, label in (("{", "}", "braces"), ("(", ")", "parentheses"), ("[", "]", "brackets")):
        if not _balanced(content, opening, closing):
            errors.append(f"unbalanced {label} in MathJax at markdown line {span.line}")
    environments = re.findall(r"\\begin\{([^{}]+)\}", content)
    endings = re.findall(r"\\end\{([^{}]+)\}", content)
    if environments != endings:
        errors.append(f"unbalanced MathJax environment at markdown line {span.line}")
    if not span.display and "\n" in content:
        errors.append(f"inline MathJax spans multiple lines at markdown line {span.line}")
    return errors


def is_complete_formula(content: str) -> bool:
    compact = re.sub(r"\s+", " ", content.strip())
    if "=" in compact or "\\begin{" in compact:
        return True
    if re.search(r"\\(?:frac|sum|prod|int|sqrt)\b", compact):
        return True
    operator_count = len(re.findall(r"[+\-*/^_]", compact))
    return operator_count >= 2


def normalize_formula(value: str) -> str:
    value = value.strip()
    if value.startswith("$$") and value.endswith("$$"):
        value = value[2:-2]
    elif value.startswith("$") and value.endswith("$"):
        value = value[1:-1]
    return re.sub(r"\s+", "", value)


def markdown_table_lines(markdown: str) -> set[int]:
    lines = markdown.splitlines()
    table_rows: set[int] = set()
    for index, line in enumerate(lines):
        if not TABLE_SEPARATOR_RE.match(line):
            continue
        if index > 0 and "|" in lines[index - 1]:
            table_rows.add(index)
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].strip() and "|" in lines[cursor]:
            table_rows.add(cursor + 1)
            cursor += 1
    return table_rows


def validate_markdown_formulas(markdown: str) -> tuple[list[str], list[MathSpan]]:
    """Return blocking errors and all well-delimited MathJax spans."""
    errors: list[str] = []
    markdown = _blank_matches(markdown, FRONTMATTER_RE)
    table_rows = markdown_table_lines(markdown)
    for pattern, label in ((FENCED_CODE_RE, "fenced code block"), (INLINE_CODE_RE, "inline code")):
        for match in pattern.finditer(markdown):
            value = match.group(0)
            if (
                RAW_LATEX_RE.search(value)
                or RAW_EQUATION_RE.search(value)
                or RAW_EXPONENT_RE.search(value)
                or CODE_MATH_SCRIPT_RE.search(value)
            ):
                line = markdown.count("\n", 0, match.start()) + 1
                errors.append(f"formula-like content appears in {label} at markdown line {line}")
    code_masked = _blank_matches(_blank_matches(markdown, FENCED_CODE_RE), INLINE_CODE_RE)
    spans: list[MathSpan] = []
    for match in MATH_RE.finditer(code_masked):
        content = match.group("block") if match.group("block") is not None else match.group("inline")
        span = MathSpan(
            content=content or "",
            display=match.group("block") is not None,
            line=code_masked.count("\n", 0, match.start()) + 1,
            start=match.start(),
            end=match.end(),
        )
        spans.append(span)
        errors.extend(_formula_errors(span))

        if span.line in table_rows and is_complete_formula(span.content):
            errors.append(
                f"complete formula appears in a Markdown table at line {span.line}; "
                "move it to a standalone formula card"
            )

    prose = code_masked
    chars = list(prose)
    for span in spans:
        for index in range(span.start, span.end):
            if chars[index] != "\n":
                chars[index] = " "
    prose = _blank_matches("".join(chars), IMAGE_RE)

    if UNESCAPED_DOLLAR_RE.search(prose):
        line = prose.count("\n", 0, UNESCAPED_DOLLAR_RE.search(prose).start()) + 1
        errors.append(f"unclosed or malformed MathJax delimiter at markdown line {line}")

    for line_no, line in enumerate(prose.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("!") or TABLE_SEPARATOR_RE.match(stripped):
            continue
        if ALT_MATH_DELIMITER_RE.search(stripped):
            errors.append(f"unsupported MathJax delimiter outside $...$ or $$...$$ at markdown line {line_no}")
            continue
        if RAW_LATEX_RE.search(stripped) or RAW_SCRIPT_RE.search(stripped) or RAW_EQUATION_RE.search(stripped) or RAW_EXPONENT_RE.search(stripped):
            errors.append(f"raw formula-like text outside MathJax at markdown line {line_no}")

    return sorted(set(errors)), spans
