#!/usr/bin/env python3
"""Lint workshop material.

ERROR  = the file cannot be opened or run at all (fails the check).
WARN   = likely mistake, but could be intentional in teaching material.

Usage:
    lint_workshop.py FILE...                 lint the given files
    lint_workshop.py --changed-since REF     lint files changed between REF and HEAD
    lint_workshop.py --all                   lint every tracked file
Add --github for GitHub annotations and a job summary, --print-files to only
list what would be linted.
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

try:
    import nbformat
except ImportError:  # JSON check still runs without it
    nbformat = None
try:
    import yaml
except ImportError:
    yaml = None

RSCRIPT = shutil.which("Rscript")
BASH = shutil.which("bash")
SKIPPED = set()  # checks that could not run because a tool is missing
BROKEN = set()  # checks that were attempted but did not complete; these fail the run

# Parses every file given on the command line, prints "path<TAB>message" for failures,
# then a marker line so a parser that stopped early is not mistaken for clean files.
R_DONE = "LINT_WORKSHOP_R_DONE"
R_PARSE = (
    "for (f in commandArgs(TRUE)) tryCatch(invisible(parse(file = f, keep.source = FALSE)),"
    " error = function(e) cat(f, '\\t', gsub('\\n', ' ', conditionMessage(e)), '\\n', sep = ''));"
    f" cat('{R_DONE}\\n')"
)


def r_parse_failures(paths):
    """Return {path: message} for R files that do not parse. Empty if R is missing."""
    if not paths:
        return {}
    if not RSCRIPT:
        SKIPPED.add("R code was not checked: Rscript is not installed")
        return {}
    failures = {}
    for start in range(0, len(paths), 200):
        batch = [str(p) for p in paths[start:start + 200]]
        # --vanilla: do not load .Rprofile or .Renviron from the repo being checked
        out = subprocess.run([RSCRIPT, "--vanilla", "-e", R_PARSE, *batch], capture_output=True, text=True)
        if out.returncode or R_DONE not in out.stdout:
            reason = (out.stderr.strip().splitlines() or ["no output"])[-1][:160]
            BROKEN.add(f"R code could not be checked: Rscript exited with status {out.returncode}: {reason}")
            continue
        for line in out.stdout.splitlines():
            if "\t" in line:
                path, msg = line.split("\t", 1)
                failures[path] = re.sub(r"^.*?:(?=\d+:\d+:)", "", msg).strip()  # drop the file path R prepends
    return failures


HELP = re.compile(r"[\w.\[\]]+\?{1,2}")  # `name?` and `name??`
MAGIC_ASSIGNMENT = re.compile(r"^(\s*[A-Za-z_][\w.,\s\[\]]*?)=\s*[!%].*$")  # `x = !ls`, `x = %magic`


def strip_ipython(source):
    """Blank out IPython magics and shell escapes so the rest can go through ast."""
    if source.lstrip().startswith("%%"):
        first = source.lstrip().split(None, 1)[0]
        if first not in ("%%time", "%%timeit", "%%capture"):
            return None  # the cell body is not Python
        source = "\n" + (source.split("\n", 1)[1] if "\n" in source else "")  # keep line numbers
    lines = []
    for line in source.split("\n"):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(("%", "!", "?")) or HELP.fullmatch(stripped.strip()):
            line = indent + "pass"
        else:
            line = MAGIC_ASSIGNMENT.sub(r"\1= None", line)
        lines.append(line)
    return "\n".join(lines)


def python_syntax_error(source):
    try:
        ast.parse(source)
    except SyntaxError as e:
        return f"{type(e).__name__}: {e.msg} (line {e.lineno})"
    return None


def python_cell_error(source):
    """Syntax error in a notebook cell or chunk, or None. IPython syntax is allowed."""
    err = python_syntax_error(source)
    if err is None:
        return None
    cleaned = strip_ipython(source)
    return python_syntax_error(cleaned) if cleaned is not None else None


RELATIVE_IMG = re.compile(r'!\[[^\]]*\]\(([^)\s]+)|<img[^>]+src=["\']([^"\']+)')


def lint_ipynb(path, add):
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        nb = json.loads(text)
    except json.JSONDecodeError as e:
        add("ERROR", f"line {e.lineno}", f"not valid JSON, the notebook cannot be opened: {e.msg}")
        return
    if not isinstance(nb, dict) or "cells" not in nb and "worksheets" not in nb:
        add("ERROR", "", "valid JSON but not a notebook (no cells)")
        return
    if nbformat is not None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                nbformat.validate(nb)
        except Exception as e:
            msg = str(getattr(e, "message", e)).split("\n")[0][:160]
            add("WARN", "", f"does not match the notebook schema: {msg}")

    meta = nb.get("metadata", {})
    language = (
        meta.get("kernelspec", {}).get("language")
        or meta.get("language_info", {}).get("name")
        or ("R" if meta.get("kernelspec", {}).get("name", "").lower() in ("ir", "r") else "python")
    ).lower()

    r_chunks = {}
    tmp = Path(tempfile.mkdtemp())
    for i, cell in enumerate(nb.get("cells", [])):
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else source
        where = f"cell {i}"
        if cell.get("cell_type") == "markdown":
            for m in RELATIVE_IMG.finditer(source):
                target = m.group(1) or m.group(2)
                if not target.startswith(("http://", "https://", "data:", "attachment:", "#")):
                    add("WARN", where, f"relative image path does not render in Colab: {target}")
        elif cell.get("cell_type") == "code":
            for output in cell.get("outputs", []):
                if output.get("output_type") == "error":
                    add("WARN", where, f"committed with an error output: {output.get('ename')}: {str(output.get('evalue'))[:80]}")
            if not source.strip():
                continue
            if language == "python":
                err = python_cell_error(source)
                if err:
                    add("WARN", where, f"code cell does not parse: {err}")
            elif language == "r":
                chunk = tmp / f"{i}.R"
                chunk.write_text(source)
                r_chunks[str(chunk)] = where
    for chunk, msg in r_parse_failures(list(r_chunks)).items():
        add("WARN", r_chunks[chunk], f"code cell does not parse: {msg[:140]}")
    shutil.rmtree(tmp, ignore_errors=True)


def lint_py(path, add):
    err = python_syntax_error(path.read_text(encoding="utf-8", errors="replace"))
    if err:
        add("ERROR", "", f"does not parse: {err}")


def lint_r(path, add):
    for msg in r_parse_failures([path]).values():
        add("ERROR", "", f"does not parse: {msg[:160]}")


def lint_sh(path, add):
    if not BASH:
        SKIPPED.add("shell scripts were not checked: bash is not installed")
        return
    out = subprocess.run([BASH, "-n", str(path)], capture_output=True, text=True)
    if out.returncode:
        add("ERROR", "", f"bash -n: {out.stderr.strip().splitlines()[-1][:160]}")


FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
CHUNK_HEADER = re.compile(r"^\{\s*([A-Za-z0-9_]+)(.*)\}\s*$")
NOT_RUN = re.compile(r"eval\s*[=:]\s*(FALSE|F|false)\b|error\s*[=:]\s*(TRUE|T|true)\b")


def lint_rmd(path, add):
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")

    # YAML front matter
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
        if end is None:
            add("ERROR", "line 1", "YAML header is never closed with ---")
        elif yaml is not None:
            class Loader(yaml.SafeLoader):
                pass
            Loader.add_multi_constructor("!", lambda loader, suffix, node: None)  # !r, !expr
            try:
                yaml.load("\n".join(lines[1:end]), Loader=Loader)
            except yaml.YAMLError as e:
                add("ERROR", "line 1", f"YAML header does not parse, the document cannot render: {str(e).splitlines()[0][:140]}")

    # Code fences and chunks
    chunks = []  # (start_line, language, header, code)
    opened = None
    for n, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if opened is None:
            if m:
                opened = (n, m.group(1), m.group(2).strip(), [])
        elif m and m.group(1)[0] == opened[1][0] and len(m.group(1)) >= len(opened[1]) and not m.group(2).strip():
            header = CHUNK_HEADER.match(opened[2])
            if header:
                chunks.append((opened[0], header.group(1).lower(), header.group(2), "\n".join(opened[3])))
            opened = None
        else:
            opened[3].append(line)
    if opened is not None:
        add("ERROR", f"line {opened[0]}", "code chunk is never closed; everything after it renders as code")

    tmp = Path(tempfile.mkdtemp())
    r_chunks = {}
    for start, language, header, code in chunks:
        options = header + "\n" + "\n".join(l for l in code.split("\n") if l.startswith("#|"))
        if NOT_RUN.search(options) or not code.strip():
            continue
        where = f"line {start}"
        if language == "r":
            chunk = tmp / f"{start}.R"
            chunk.write_text(code)
            r_chunks[str(chunk)] = where
        elif language == "python":
            err = python_cell_error(code)
            if err:
                add("WARN", where, f"python chunk does not parse: {err}")
        elif language in ("bash", "sh") and BASH:
            out = subprocess.run([BASH, "-n"], input=code, capture_output=True, text=True)
            if out.returncode:
                add("WARN", where, f"bash chunk does not parse: {out.stderr.strip().splitlines()[-1][:120]}")
    for chunk, msg in r_parse_failures(list(r_chunks)).items():
        add("WARN", r_chunks[chunk], f"R chunk does not parse: {msg[:140]}")
    shutil.rmtree(tmp, ignore_errors=True)


def lint_mlx(path, add):
    if not zipfile.is_zipfile(path):
        add("ERROR", "", "not a valid .mlx archive, MATLAB cannot open it")


LINTERS = {
    ".ipynb": lint_ipynb,
    ".py": lint_py,
    ".r": lint_r,
    ".rmd": lint_rmd,
    ".qmd": lint_rmd,
    ".sh": lint_sh,
    ".mlx": lint_mlx,
}


def lint(paths):
    findings = []
    for path in map(Path, paths):
        linter = LINTERS.get(path.suffix.lower())
        if linter is None or not path.is_file():
            continue

        def add(level, where, message, path=path):
            findings.append({"level": level, "file": str(path), "where": where, "message": message})

        try:
            linter(path, add)
        except Exception as e:  # a linter crash must not look like a clean file
            add("ERROR", "", f"linter crashed: {type(e).__name__}: {e}")
    return findings


# When a pull request changes the caller workflow, every file is checked.
SELF = (".github/workflows/lint_workshop.yml",)


def git_files(command, *args):
    out = subprocess.run(["git", command, "-z", *args], capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def select_files(args):
    if args.all:
        files = git_files("ls-files")
    elif args.changed_since:
        files = git_files("diff", "--name-only", "--diff-filter=AMR", args.changed_since, "HEAD")
        if any(f in SELF for f in files):
            files = git_files("ls-files")
    else:
        files = args.files
    return [f for f in files if Path(f).suffix.lower() in LINTERS]


def escape(text, is_property=False):
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if is_property else text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--changed-since", metavar="REF")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--print-files", action="store_true")
    parser.add_argument("--github", action="store_true", help="emit GitHub annotations and a job summary")
    parser.add_argument("--json", help="write findings to this file")
    args = parser.parse_args()

    files = select_files(args)
    if args.print_files:
        print("\n".join(files))
        return

    findings = lint(files)
    errors = sum(f["level"] == "ERROR" for f in findings) + len(BROKEN)
    warnings_count = sum(f["level"] == "WARN" for f in findings)
    total = f"{len(files)} file(s) checked, {errors} error(s), {warnings_count} warning(s)"
    for f in findings:
        text = f"{f['where']}: {f['message']}" if f["where"] else f["message"]
        if args.github:
            kind = "error" if f["level"] == "ERROR" else "warning"
            print(f"::{kind} file={escape(f['file'], True)},title=Workshop lint::{escape(text)}")
        else:
            print(f"{f['level']:5} {f['file']}: {text}")
    for problem in sorted(BROKEN):
        print(f"::error title=Workshop lint::{escape(problem)}" if args.github else f"ERROR {problem}")
    for note in sorted(SKIPPED):
        print(f"::notice title=Workshop lint::{escape(note)}" if args.github else f"NOTE  {note}")
    print(total)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if args.github and summary:
        lines = ["## Workshop lint", "", total, ""]
        if findings:
            lines += ["| | File | Where | Problem |", "|---|---|---|---|"]
            for f in sorted(findings, key=lambda f: f["level"]):
                problem = f["message"].replace("|", "\\|")
                lines.append(f"| {'❌' if f['level'] == 'ERROR' else '⚠️'} | `{f['file']}` | {f['where']} | {problem} |")
        lines += [f"- ❌ {problem}" for problem in sorted(BROKEN)]
        lines += [f"- {note}" for note in sorted(SKIPPED)]
        with open(summary, "a", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")

    if args.json:
        Path(args.json).write_text(json.dumps(findings, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
