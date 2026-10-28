# Kore grammar tools

Mechanical checks for RFC 0002. They read the single ```` ```ebnf ```` block in the RFC; no other copy of the grammar exists.

```bash
# 1. LL(1) check: prints every FIRST/FIRST or FIRST/FOLLOW conflict (expect: conflicts: 0)
python3 tools/ll1.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md

# 2. Parse real programs with a table-driven predictive parser built from the same tables
python3 tools/kparse.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md litmus/*.kr

# 3. Reserved-word list agrees in the RFC box, the grammar terminals and kparse.py
python3 tools/check_keywords.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md
```

`ll1.py` treats `Ident`, `IntLit`, `FloatLit`, `StringLit`, `CharLit` as terminals (lexical classes).
`kparse.py` recognizes only; it builds no AST and checks no semantics. Its lexer follows RFC 0002 §3 and reports malformed input as `FAIL`, not a traceback.
Keep all three green before changing the grammar. Python 3, standard library only.
