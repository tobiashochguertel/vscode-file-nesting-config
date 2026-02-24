#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
"""
validate_readme.py — Verify the JSONC block in a README.md can be parsed by the
antfu.file-nesting VS Code extension (v2.0.1, dist/index.js line 499).

Compiled extension logic (verbatim from dist/index.js:499):
  const json = `{${content.trim().split(/\\n/g)
    .filter((line) => !line.trim().startsWith("//"))
    .join("\\n").slice(0, -1)}}`;
  const config = JSON.parse(json) || {};

The extension fetches from:
  https://cdn.jsdelivr.net/gh/{repo}@{branch}/README.md
Default repo: antfu/vscode-file-nesting-config, branch: main

Exit 0 if all sources pass, exit 1 if any fail.

Usage:
  uv run validate_readme.py [FILE_OR_URL ...]
  uv run validate_readme.py README.md
  uv run validate_readme.py README.md --upstream
  uv run validate_readme.py --self-test
  uv run validate_readme.py https://cdn.jsdelivr.net/gh/owner/repo@main/README.md

Flags:
  --upstream      Also validate the antfu upstream URL (confirms validator logic)
  --self-test     Run a built-in broken-snippet test; exit 1 if validator fails to catch it
"""

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

JSONC_FENCE_RE = re.compile(r"```jsonc([\s\S]*?)```")

UPSTREAM_URL = (
    "https://cdn.jsdelivr.net/gh/antfu/vscode-file-nesting-config@main/README.md"
)

# A minimal JSONC block that is intentionally broken (no trailing "," after "}").
# The extension's .slice(0,-1) will remove the "}" → invalid JSON.
_BROKEN_SNIPPET = '''\
```jsonc
  // updated 2000-01-01 00:00
  // https://github.com/antfu/vscode-file-nesting-config
  "explorer.fileNesting.enabled": true,
  "explorer.fileNesting.expand": false,
  "explorer.fileNesting.patterns": {
    "*.ts": "$(capture).js"
  }
```'''

# A correct snippet: trailing "," after the closing "}" so .slice(0,-1) removes ","
_GOOD_SNIPPET = '''\
```jsonc
  // updated 2000-01-01 00:00
  // https://github.com/antfu/vscode-file-nesting-config
  "explorer.fileNesting.enabled": true,
  "explorer.fileNesting.expand": false,
  "explorer.fileNesting.patterns": {
    "*.ts": "$(capture).js"
  },
```'''


class Result(NamedTuple):
    source: str
    ok: bool
    message: str


def _parse_like_extension(md: str, source: str) -> Result:
    """Replicate the compiled extension logic exactly (dist/index.js:498-500)."""
    m = JSONC_FENCE_RE.search(md)
    if not m:
        return Result(source, False, f"No ```jsonc block found in {source}")

    content = m.group(1)

    # Exact JS: content.trim().split(/\n/g).filter(...).join("\n").slice(0,-1)
    lines = content.strip().split("\n")
    filtered = [line for line in lines if not line.strip().startswith("//")]
    joined = "\n".join(filtered)
    sliced = joined[:-1]           # .slice(0, -1)
    json_str = "{" + sliced + "}"  # template literal: `{${...}}`

    try:
        config = json.loads(json_str)
    except json.JSONDecodeError as e:
        err_lines = json_str[: e.pos].split("\n")
        err_line_no = len(err_lines)
        err_col = len(err_lines[-1]) + 1
        ctx_lines = json_str.split("\n")
        context = "\n".join(
            f"  {'>>>' if i == err_line_no - 1 else '   '} {i+1:4d}: {ctx_lines[i][:120]}"
            for i in range(max(0, err_line_no - 3), min(len(ctx_lines), err_line_no + 2))
        )
        hint = (
            "\n  Hint: the extension calls .slice(0,-1) expecting a trailing \",\" after\n"
            '  the patterns closing brace. Block must end with: ...},\\n  },'
        )
        msg = (
            f"JSON parse failed — {e.msg} (line {err_line_no} col {err_col} / pos {e.pos})\n"
            f"{context}{hint}"
        )
        return Result(source, False, msg)

    patterns = config.get("explorer.fileNesting.patterns", {})
    msg = (
        f"JSONC is valid ({len(patterns)} patterns, "
        f"fileNesting.enabled={config.get('explorer.fileNesting.enabled')})"
    )
    return Result(source, True, msg)


def _fetch_url(url: str) -> str:
    import httpx
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.text


def validate_source(source: str) -> Result:
    """Validate a local file path or https:// URL."""
    if source.startswith("https://") or source.startswith("http://"):
        try:
            md = _fetch_url(source)
        except Exception as exc:
            return Result(source, False, f"Failed to fetch: {exc}")
        return _parse_like_extension(md, source)
    else:
        path = Path(source)
        if not path.exists():
            return Result(source, False, f"File not found: {path}")
        return _parse_like_extension(path.read_text(encoding="utf-8"), str(path))


def self_test() -> bool:
    """Verify the validator catches a known-broken snippet and passes a known-good one."""
    broken = _parse_like_extension(_BROKEN_SNIPPET, "<self-test/broken>")
    good = _parse_like_extension(_GOOD_SNIPPET, "<self-test/good>")

    ok = True
    if broken.ok:
        print("SELF-TEST FAIL: validator did NOT detect the broken snippet (false negative!)")
        ok = False
    else:
        print(f"SELF-TEST OK: broken snippet correctly rejected — {broken.message.splitlines()[0]}")

    if not good.ok:
        print(f"SELF-TEST FAIL: validator rejected the good snippet — {good.message}")
        ok = False
    else:
        print(f"SELF-TEST OK: good snippet correctly accepted — {good.message}")

    return ok


def main() -> None:
    args = sys.argv[1:]

    if "--self-test" in args:
        sys.exit(0 if self_test() else 1)

    add_upstream = "--upstream" in args
    sources = [a for a in args if not a.startswith("--")]

    if not sources:
        sources = ["README.md"]

    if add_upstream:
        sources.append(UPSTREAM_URL)

    results: list[Result] = []
    for src in sources:
        r = validate_source(src)
        label = "OK " if r.ok else "ERR"
        print(f"[{label}] {r.source}")
        if not r.ok:
            for line in r.message.splitlines():
                print(f"       {line}", file=sys.stderr)
        else:
            print(f"       {r.message}")
        results.append(r)

    if any(not r.ok for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
