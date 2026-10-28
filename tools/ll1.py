import re, sys
from collections import defaultdict

def extract(path):
    t = open(path).read()
    m = re.search(r"```ebnf\n(.*?)```", t, re.S)
    return m.group(1)

def tokenize(src):
    """Tokenize the EBNF strictly: any character that is not whitespace and not part of a token is an error."""
    src = re.sub(r"\(\*.*?\*\)", "", src, flags=re.S)
    pat = re.compile(r'\s+|"((?:[^"\\\n]|\\.)*)"|([A-Za-z_][A-Za-z_0-9]*)|([=;|()\[\]{}])')
    toks = []; i = 0
    while i < len(src):
        m = pat.match(src, i)
        if not m: raise SystemExit(f"EBNF error: unexpected character {src[i]!r} near {src[i:i+30]!r}")
        i = m.end()
        if m.group(1) is not None: toks.append(("T", m.group(1)))
        elif m.group(2): toks.append(("N", m.group(2)))
        elif m.group(3): toks.append(("P", m.group(3)))
    return toks

class P:
    def __init__(s, toks): s.t = toks; s.i = 0; s.prods = defaultdict(list); s.n = 0
    def peek(s): return s.t[s.i] if s.i < len(s.t) else (None, None)
    def eat(s, want=None):
        if s.i >= len(s.t): raise SystemExit(f"EBNF error: unexpected end of grammar, expected {want!r}")
        x = s.t[s.i]
        if want is not None and x != ("P", want):
            raise SystemExit(f"EBNF error: expected {want!r}, found {x[1]!r} (token {s.i}, near {' '.join(v for _, v in s.t[max(0, s.i-4):s.i+3])!r})")
        s.i += 1; return x
    def fresh(s, base): s.n += 1; return f"{base}~{s.n}"
    def grammar(s):
        while s.i < len(s.t):
            k, name = s.eat()
            if k != "N": raise SystemExit(f"EBNF error: expected a production name, found {name!r}")
            s.eat("=")
            alts = s.alt(name)
            s.eat(";")
            s.prods[name] += alts
    def alt(s, ctx):
        alts = [s.seq(ctx)]
        while s.peek() == ("P", "|"):
            s.eat(); alts.append(s.seq(ctx))
        return alts
    def seq(s, ctx):
        out = []
        while True:
            k, v = s.peek()
            if k in ("T", "N"):
                s.eat(); out.append(("t", v) if k == "T" else ("n", v))
            elif (k, v) == ("P", "("):
                s.eat(); a = s.alt(ctx); s.eat(")")
                nt = s.fresh(ctx); s.prods[nt] += a; out.append(("n", nt))
            elif (k, v) == ("P", "["):
                s.eat(); a = s.alt(ctx); s.eat("]")
                nt = s.fresh(ctx); s.prods[nt] += a + [[]]; out.append(("n", nt))
            elif (k, v) == ("P", "{"):
                s.eat(); a = s.alt(ctx); s.eat("}")
                nt = s.fresh(ctx)
                s.prods[nt] += [x + [("n", nt)] for x in a] + [[]]
                out.append(("n", nt))
            else: break
        return out

def analyze(path, start="Module"):
    p = P(tokenize(extract(path))); p.grammar()
    G = p.prods
    nts = set(G)
    nullable = set()
    ch = True
    while ch:
        ch = False
        for A, alts in G.items():
            if A in nullable: continue
            for a in alts:
                if all(s[0] == "n" and s[1] in nullable for s in a):
                    nullable.add(A); ch = True; break
    FIRST = defaultdict(set)
    def first_seq(seq):
        r = set(); 
        for k, v in seq:
            if k == "t" or (k == "n" and v not in nts): r.add(v); return r, False
            r |= FIRST[v]
            if v not in nullable: return r, False
        return r, True
    ch = True
    while ch:
        ch = False
        for A, alts in G.items():
            for a in alts:
                f, _ = first_seq(a)
                if not f <= FIRST[A]: FIRST[A] |= f; ch = True
    FOLLOW = defaultdict(set); FOLLOW[start].add("$")
    ch = True
    while ch:
        ch = False
        for A, alts in G.items():
            for a in alts:
                for i, (k, v) in enumerate(a):
                    if k == "n" and v in nts:
                        f, nl = first_seq(a[i+1:])
                        new = set(f)
                        if nl: new |= FOLLOW[A]
                        if not new <= FOLLOW[v]: FOLLOW[v] |= new; ch = True
    conflicts = []
    for A, alts in G.items():
        sets = []
        for a in alts:
            f, nl = first_seq(a)
            if nl: f = f | FOLLOW[A]
            sets.append(f)
        for i in range(len(sets)):
            for j in range(i+1, len(sets)):
                inter = sets[i] & sets[j]
                if inter: conflicts.append((A, sorted(inter), alts[i], alts[j]))
    global TABLES
    TABLES=(G,FIRST,FOLLOW,nullable,first_seq)
    return G, conflicts, nts

def fmt(seq): return " ".join(('"%s"' % v) if k == "t" else v for k, v in seq) or "ε"

if __name__ == "__main__":
    G, conflicts, nts = analyze(sys.argv[1])
    undefined = set()
    for A, alts in G.items():
        for a in alts:
            for k, v in a:
                if k == "n" and v not in G: undefined.add(v)
    print("lexical/undefined nonterminals (treated as terminals):", sorted(undefined))
    print("conflicts:", len(conflicts))
    for A, toks, a, b in conflicts:
        base = A.split("~")[0]
        print(f"- in {A}: on {toks}\n    alt1: {fmt(a)}\n    alt2: {fmt(b)}")
    LEXICAL = {"Ident", "IntLit", "FloatLit", "StringLit", "CharLit"}
    bad = undefined - LEXICAL
    if bad: print("undefined nonterminals that are not lexical classes:", sorted(bad))
    sys.exit(1 if conflicts or bad else 0)
