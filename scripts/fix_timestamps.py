"""One-off sweep: route every timestamp render through lib/datetime.js (IST)."""
import re, pathlib

SRC = pathlib.Path("/app/frontend/src")
IMPORT_LINE = 'import { fmtDT, fmtD, fmtT } from "@/lib/datetime";\n'

# value expression: identifiers, member access, optional chaining, calls with simple args, strings
VAL = r"[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*|\?\.|\[[^\[\]]{0,40}\]|\([^()]{0,60}\))*"

PATTERNS = [
    # new Date(x).toLocaleString(...) → fmtDT(x)
    (re.compile(r"new Date\((" + VAL + r")\)\.toLocaleString\((?:[^()]|\([^()]*\))*\)"), r"fmtDT(\1)"),
    (re.compile(r"new Date\((" + VAL + r")\)\.toLocaleDateString\((?:[^()]|\([^()]*\))*\)"), r"fmtD(\1)"),
    (re.compile(r"new Date\((" + VAL + r")\)\.toLocaleTimeString\((?:[^()]|\([^()]*\))*\)"), r"fmtT(\1)"),
    # "…".slice(0, 16).replace("T", " ") → fmtDT(...)
    (re.compile(r"\((" + VAL + r")\s*\|\|\s*\"\"\)\.slice\(0,\s*16\)\.replace\(\"T\",\s*\" \"\)"), r"fmtDT(\1)"),
    (re.compile(r"(" + VAL + r")\.slice\(0,\s*16\)\.replace\(\"T\",\s*\" \"\)"), r"fmtDT(\1)"),
    (re.compile(r"\((" + VAL + r")\s*\|\|\s*\"\"\)\.replace\(\"T\",\s*\" \"\)\.slice\(0,\s*16\)"), r"fmtDT(\1)"),
    # timestamp fields sliced to date / time only
    (re.compile(r"\((" + VAL + r"(?:_at|At|_ts))\s*\|\|\s*\"\"\)\.slice\(0,\s*10\)"), r"fmtD(\1)"),
    (re.compile(r"(" + VAL + r"(?:_at|At|_ts))\.slice\(0,\s*10\)"), r"fmtD(\1)"),
    (re.compile(r"\((" + VAL + r"(?:_at|At|_ts))\s*\|\|\s*\"\"\)\.slice\(11,\s*16\)"), r"fmtT(\1)"),
    (re.compile(r"(" + VAL + r"(?:_at|At|_ts))\.slice\(11,\s*16\)"), r"fmtT(\1)"),
]

changed = []
for f in sorted(SRC.rglob("*.jsx")) + sorted(SRC.rglob("*.js")):
    if f.name == "datetime.js":
        continue
    src = orig = f.read_text()
    for rx, rep in PATTERNS:
        src = rx.sub(rep, src)
    if src == orig:
        continue
    # avoid touching date *inputs* that need YYYY-MM-DD — new Date().toISOString().slice(0,10) is untouched
    if re.search(r"\bfmt(DT|D|T)\(", src) and "lib/datetime" not in src:
        lines = src.split("\n")
        last_import = max((i for i, l in enumerate(lines) if l.startswith("import ")), default=-1)
        lines.insert(last_import + 1, IMPORT_LINE.rstrip("\n"))
        src = "\n".join(lines)
    f.write_text(src)
    changed.append(str(f.relative_to(SRC)))

print(f"{len(changed)} files updated")
for c in changed:
    print(" -", c)
