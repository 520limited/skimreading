#!/usr/bin/env python
"""Regression tests for the strict Markdown formula contract."""

from __future__ import annotations

from markdown_formula import validate_markdown_formulas


def assert_valid(markdown: str) -> None:
    errors, _spans = validate_markdown_formulas(markdown)
    if errors:
        raise AssertionError(f"expected valid Markdown, got: {errors}")


def assert_invalid(markdown: str, expected: str) -> None:
    errors, _spans = validate_markdown_formulas(markdown)
    if not any(expected in error for error in errors):
        raise AssertionError(f"expected {expected!r}, got: {errors}")


def main() -> int:
    assert_valid("变量 $h_t$ 表示当前状态。\n\n$$\nh_t = \\alpha_t h_{t-1} + \\beta_t x_t\n$$")
    assert_valid("![公式截图](figures/formula_1.png)\n\n该截图描述状态如何更新。")
    assert_valid("MIMO 将状态写入和读出扩展为多输入多输出，B、C 表示两个投影。")
    assert_valid("---\nsource_hash: abc123\nasset_manifest: manifest.json\n---\n\n正文无公式。")
    assert_valid("字段 `content_clean` 表示裁剪是否干净。")
    assert_invalid("其中 h_t = alpha_t h_{t-1} + beta_t x_t。", "raw formula-like text")
    assert_invalid("| 模块 | 操作 |\n|---|---|\n| SSM | $h_t = A_t h_{t-1}$ |", "Markdown table")
    assert_invalid("模块 | 操作\n---|---\nSSM | $h_t = A_t h_{t-1}$", "Markdown table")
    assert_invalid("公式为 $h_t = A_t h_{t-1}。", "delimiter")
    assert_invalid("$$ h_t = \\frac{a}{b $$", "unbalanced braces")
    assert_invalid("```text\nh_t = A_t h_{t-1}\n```", "fenced code block")
    assert_invalid("公式片段写成 `B_t X_t^T`。", "inline code")
    print("formula Markdown self-test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
