#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
validate_readme.py — Verify the JSONC block in README.md can be parsed by the
antfu.file-nesting VS Code extension.

The extension uses this exact logic (fetch.ts):
  content.trim()
    .split(/\\n/g)
    .filter(line => !line.trim().startsWith('//'))
    .join('\\n')
    .slice(0, -1)          # removes trailing "," left by the patterns closing brace
  then: JSON.parse('{' + result + '}')

Exit 0 on success, exit 1 on failure.

Usage:
  uv run validate_readme.py [README.md]
"""

import json
import re
import sys
from pathlib import Path

JSONC_FENCE_RE = re.compile(r"```jsonc([\s\S]*?)```")


def validate(path: Path) -> None:
    content = path.read_text(encoding="utf-8")

    m = JSONC_FENCE_RE.search(content)
    if not m:
        print(f"ERROR: No ```jsonc block found in {path}", file=sys.stderr)
        sys.exit(1)

    block_content = m.group(1)

    # Replicate the extension's JS parsing exactly:
    #   content.trim().split(/\n/g)
    #     .filter(line => !line.trim().startsWith('//'))
    #     .join('\n')
    #     .slice(0, -1)
    lines = block_content.strip().split("\n")
    filtered = [line for line in lines if not line.strip().startswith("//")]
    joined = "\n".join(filtered)
    sliced = joined[:-1]  # .slice(0, -1) — removes expected trailing ","
    json_str = "{" + sliced + "}"

    try:
        config = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Compute line/col in the original block for a helpful message
        err_lines = json_str[: e.pos].split("\n")
        err_line_no = len(err_lines)
        err_col = len(err_lines[-1]) + 1
        print(
            f"ERROR: JSON parse failed in {path} — {e.msg} "
            f"(line {err_line_no} col {err_col} / position {e.pos})",
            file=sys.stderr,
        )
        # Show context
        all_lines = json_str.split("\n")
        for i in range(max(0, err_line_no - 3), min(len(all_lines), err_line_no + 2)):
            marker = ">>>" if i == err_line_no - 1 else "   "
            print(f"  {marker} {i + 1:4d}: {all_lines[i][:120]}", file=sys.stderr)
        print(
            "\nHint: the extension calls .slice(0,-1) on the JSONC block, so the block\n"
            'must end with  "},\\n  },"  (trailing comma after the closing brace).',
            file=sys.stderr,
        )
        sys.exit(1)

    patterns = config.get("explorer.fileNesting.patterns", {})
    print(
        f"OK: {path} — JSONC is valid ({len(patterns)} patterns, "
        f"fileNesting.enabled={config.get('explorer.fileNesting.enabled')})"
    )


def main() -> None:
    readme = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("README.md")
    if not readme.exists():
        print(f"ERROR: {readme} not found", file=sys.stderr)
        sys.exit(1)
    validate(readme)


if __name__ == "__main__":
    main()
