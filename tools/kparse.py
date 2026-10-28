import re, sys
import ll1  # run from tools/ or with tools/ on PYTHONPATH
KW = set("pub as import fn struct linear enum impl type distinct extern const let mut if else switch case while for in break continue return defer errdefer catch try unsafe true false null".split())
OPS = ["<<=",">>=","->","..","<<",">>","<=",">=","==","!=","&&","||","+=","-=","*=","/=","%=","&=","|=","^="] + list("+-*/%&|^~!<>=.,;:(){}[]?")
NUM = [r"0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*", r"0[bB][01]+(?:_[01]+)*", r"\d+(?:_\d+)*(?:\.\d+(?:_\d+)*)?(?:[eE][+-]?\d+)?"]
STR = r'"(?:[^"\\\n]|\\(?:x[0-9a-fA-F]{2}|[nrt\\"0]))*"'
CHR = r"'(?:\\x[0-9a-fA-F]{2}|\\[nrt\\'0]|[^'\\\n])'"
def lex(src):
    """Lexer per RFC 0002 section 3. Raises SyntaxError (never SystemExit) on bad input."""
    out=[]; i=0
    while i < len(src):
        c = src[i]
        if c.isspace(): i+=1; continue
        if src.startswith("//", i):
            j = src.find("\n", i); i = len(src) if j < 0 else j; continue
        if c.isdigit():
            for pat in NUM:
                m = re.match(pat, src[i:])
                if m: break
            t = m.group(0)
            if i+len(t) < len(src) and (src[i+len(t)].isalnum() or src[i+len(t)] == "_"):
                raise SyntaxError(f"malformed number near {src[i:i+len(t)+2]!r}")
            kind = "FloatLit" if re.fullmatch(r"\d[\d_]*(\.\d[\d_]*([eE][+-]?\d+)?|[eE][+-]?\d+)", t) else "IntLit"
            out.append((kind, t)); i += len(t); continue
        m = re.match(r"[A-Za-z_]\w*", src[i:])
        if m and m.group(0).isascii():
            t = m.group(0); out.append((t,t) if t in KW else ("Ident",t)); i += len(t); continue
        if c == '"':
            m = re.match(STR, src[i:])
            if not m: raise SyntaxError(f"bad string literal near {src[i:i+20]!r}")
            out.append(("StringLit", m.group(0))); i += len(m.group(0)); continue
        if c == "'":
            m = re.match(CHR, src[i:])
            if not m: raise SyntaxError(f"bad char literal near {src[i:i+10]!r}")
            out.append(("CharLit", m.group(0))); i += len(m.group(0)); continue
        for op in OPS:
            if src.startswith(op, i): out.append((op,op)); i += len(op); break
        else:
            raise SyntaxError(f"unexpected character {c!r}")
    out.append(("$","$")); return out

def parse(src, gram):
    ll1.analyze(gram); G,FIRST,FOLLOW,nullable,first_seq = ll1.TABLES
    toks = lex(src); pos=[0]
    def err(nt):
        k=toks[pos[0]]; ctx=" ".join(t[1] for t in toks[max(0,pos[0]-8):pos[0]+4])
        raise SyntaxError(f"in {nt.split('~')[0]}: unexpected {k[1]!r} near: {ctx}")
    def run(nt):
        k = toks[pos[0]][0]
        chosen=None
        for a in G[nt]:
            f,nl = first_seq(a)
            if k in f: chosen=a; break
        if chosen is None:
            for a in G[nt]:
                f,nl = first_seq(a)
                if nl and (k in FOLLOW[nt]): chosen=a; break
        if chosen is None: err(nt)
        for kind,v in chosen:
            if kind=="t" or v not in G:
                if toks[pos[0]][0]!=v: err(nt)
                pos[0]+=1
            else: run(v)
    run("Module")
    if toks[pos[0]][0]!="$": err("Module")
    return True
if __name__=="__main__":
    gram=sys.argv[1]
    for f in sys.argv[2:]:
        try: parse(open(f).read(), gram); print("OK  ",f)
        except (SyntaxError, RecursionError) as e: print("FAIL",f,e if isinstance(e,SyntaxError) else "nesting too deep")
