# Tools

Mechanical checks for `spec/01-syntax.md`. They read the single ```` ```ebnf ```` block in that file; no other copy of the grammar exists. Python 3, standard library only.

```bash
python3 tools/ll1.py spec/01-syntax.md             # FIRST/FOLLOW check; expect "conflicts: 0"
python3 tools/check_keywords.py spec/01-syntax.md  # reserved-word box == grammar terminals == kparse.KW
python3 tools/kparse.py spec/01-syntax.md file.kr  # parse files with a parser generated from the grammar
python3 tools/run_tests.py spec/01-syntax.md       # litmus/ and tests/fail parse; tests/syntax_fail rejected
```

`ll1.py` treats `Ident`, `IntLit`, `FloatLit`, `StringLit`, `CharLit` as terminals (lexical classes). `kparse.py` only recognizes: it builds no AST and checks no semantics; its lexer follows `spec/01-syntax.md` §3 and reports malformed input as `FAIL`. Keep all of them green before changing the grammar.

All four commands exit nonzero on failure (LL(1) conflicts, undefined nonterminals, keyword mismatch, unexpected test result), so they can gate CI directly. `kparse.py` and `run_tests.py` refuse to run on a grammar with conflicts.
