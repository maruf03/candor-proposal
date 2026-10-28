"""List spec sections that no test cites. Informational; `--strict` exits 1 if any section is uncited.
A test cites a section with `NN-name §n` (for example `02-types §4`) in its `// SPEC:` or `// ERROR:` header.
Only sections that state rules count: chapters 01 to 05."""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cited = set()
for f in glob.glob(os.path.join(ROOT, "tests", "**", "*.cn"), recursive=True) + glob.glob(os.path.join(ROOT, "litmus", "*.cn")):
    for line in open(f).read().splitlines()[:2]:
        for m in re.finditer(r"(\d\d-[a-z]+) §([0-9]+)(?:\.[0-9]+)?", line): cited.add((m.group(1), m.group(2)))
missing = []
for spec in sorted(glob.glob(os.path.join(ROOT, "spec", "0[1-5]-*.md"))):
    chapter = os.path.basename(spec)[:-3]
    for h in re.findall(r"^## (\d+)\. (.+)$", open(spec).read(), re.M):
        if (chapter, h[0]) not in cited: missing.append(f"{chapter} §{h[0]} {h[1]}")
print(f"{len(cited)} spec sections cited by at least one test")
for m in missing: print("uncited:", m)
sys.exit(1 if missing and "--strict" in sys.argv else 0)
