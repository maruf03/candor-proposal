"""Check that the reserved-word list agrees in all three places:
   1. the box in RFC 0002 section 2 (with its per-column counts and the stated total),
   2. the alphabetic terminals of the EBNF grammar in RFC 0002 section 6,
   3. the KW set in tools/kparse.py.
Usage: python3 tools/check_keywords.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md
Exits non-zero on any mismatch."""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ll1, kparse

def box_words(text):
    box = text.split("KORE RESERVED WORDS")[1].split("```")[0]
    rows = [r for r in box.splitlines() if r.startswith("|") and not r.startswith("+")]
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    declared = {h: int(re.search(r"\((\d+)\)", h).group(1)) for h in header}
    cols = [[] for _ in header]; lit_from = None
    for r in rows[1:]:
        cells = [c.strip() for c in r.strip("|").split("|")]
        for i, c in enumerate(cells):
            if not c: continue
            if c.startswith("Literals"): lit_from = True; continue
            cols[i].append((c, bool(lit_from) and i == len(header) - 1))
    words, lits = [], []
    for col in cols:
        for w, is_lit in col: (lits if is_lit else words).append(w)
    return header, declared, words, lits

def main(path):
    text = open(path).read(); ok = True
    header, declared, words, lits = box_words(text)
    n_kw, n_lit = len(words), len(lits)
    print(f"box: {n_kw} keywords + {n_lit} literals = {n_kw + n_lit}")
    m = re.search(r"\*\*(\d+) keywords and (\d+) literal words \((\d+) reserved words\)\*\*", text)
    if not m or tuple(map(int, m.groups())) != (n_kw, n_lit, n_kw + n_lit):
        print("MISMATCH: stated total in section 2 does not match the box:", m.groups() if m else None); ok = False
    if sum(declared.values()) != n_kw:
        print("MISMATCH: column header counts", declared, "sum to", sum(declared.values()), "but the box lists", n_kw, "keywords"); ok = False
    lm = re.search(r"Literals \((\d+)\)", text)
    if not lm or int(lm.group(1)) != n_lit:
        print("MISMATCH: 'Literals (N)' label does not match", n_lit, "listed literals"); ok = False
    G, conflicts, _ = ll1.analyze(path)
    if conflicts:
        print(f"FAILED: grammar has {len(conflicts)} LL(1) conflict(s); run tools/ll1.py"); return 1
    terms = {v for alts in G.values() for a in alts for k, v in a if k == "t" and re.fullmatch(r"[a-z_]+", v)}
    box = set(words) | set(lits)
    for label, a, b in (("grammar terminals", terms, box), ("kparse.KW", set(kparse.KW), box)):
        if a != b:
            print(f"MISMATCH {label} vs box: only in {label}: {sorted(a-b)}; only in box: {sorted(b-a)}"); ok = False
    print("OK: box, grammar and kparse agree" if ok else "FAILED")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
