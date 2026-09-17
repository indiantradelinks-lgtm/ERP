"""Sweep round 2 — catch optional-chaining / multi-fallback / no-replace variants."""
import re, pathlib

SRC = pathlib.Path("/app/frontend/src")
IMPORT_LINE = 'import { fmtDT, fmtD, fmtT } from "@/lib/datetime";'

VAL = r"[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*|\[[^\[\]]{0,40}\]|\([^()]{0,60}\))*"
# a fallback chain like  a.b || c.d || ""   →  keep the real values only
CHAIN = r"[^()]{0,120}"

PATTERNS = [
    # String(x).replace("T"," ").slice(0,16)
    (re.compile(r"String\((" + VAL + r")\)\.replace\(\"T\",\s*\" \"\)\.slice\(0,\s*16\)"), r"fmtDT(\1)"),
    # (a || b || "").slice(0,16)[.replace("T"," ")]
    (re.compile(r"\((" + CHAIN + r")\s*\|\|\s*\"[^\"]{0,3}\"\)\.slice\(0,\s*16\)(?:\.replace\(\"T\",\s*\" \"\))?"), r"fmtDT(\1)"),
    (re.compile(r"\((" + CHAIN + r")\s*\|\|\s*\"[^\"]{0,3}\"\)\.replace\(\"T\",\s*\" \"\)\.slice\(0,\s*16\)"), r"fmtDT(\1)"),
    # x?.slice(0,16)[.replace("T"," ")]
    (re.compile(r"(" + VAL + r")\?\.slice\(0,\s*16\)(?:\.replace\(\"T\",\s*\" \"\))?"), r"fmtDT(\1)"),
    (re.compile(r"(" + VAL + r")\.slice\(0,\s*16\)(?:\.replace\(\"T\",\s*\" \"\))?"), r"fmtDT(\1)"),
    # new Date(a || b).toLocaleString(...) etc.
    (re.compile(r"new Date\((" + CHAIN + r")\)\.toLocaleString\((?:[^()]|\([^()]*\))*\)"), r"fmtDT(\1)"),
    (re.compile(r"new Date\((" + CHAIN + r")\)\.toLocaleDateString\((?:[^()]|\([^()]*\))*\)"), r"fmtD(\1)"),
    (re.compile(r"new Date\((" + CHAIN + r")\)\.toLocaleTimeString\((?:[^()]|\([^()]*\))*\)"), r"fmtT(\1)"),
    # timestamp-ish fields with optional chaining
    (re.compile(r"(" + VAL + r"(?:_at|At|_ts))\?\.slice\(0,\s*10\)"), r"fmtD(\1)"),
    (re.compile(r"(" + VAL + r"(?:_at|At|_ts))\?\.slice\(11,\s*16\)"), r"fmtT(\1)"),
]

BAD = ("toISOString", "Date()", "new Date(", "todayIST", "fmtDT(", "fmtD(", "fmtT(")


def safe(m):
    inner = m.group(1)
    return not any(b in inner for b in BAD)


changed = []
for f in sorted(SRC.rglob("*.jsx")) + sorted(SRC.rglob("*.js")):
    if f.name == "datetime.js":
        continue
    src = orig = f.read_text()
    for rx, rep in PATTERNS:
        def sub(m, rep=rep):
            if not safe(m):
                return m.group(0)
            return rep.replace(r"\1", m.group(1).strip())
        src = rx.sub(sub, src)
    if src == orig:
        continue
    if re.search(r"\bfmt(DT|D|T)\(", src) and "lib/datetime" not in src:
        lines = src.split("\n")
        last_import = max((i for i, l in enumerate(lines) if l.startswith("import ")), default=-1)
        lines.insert(last_import + 1, IMPORT_LINE)
        src = "\n".join(lines)
    f.write_text(src)
    changed.append(str(f.relative_to(SRC)))

print(f"{len(changed)} files updated")
for c in changed:
    print(" -", c)
