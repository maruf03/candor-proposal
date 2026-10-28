# Litmus Programs

Six programs that must parse today and compile once a compiler exists. They are chosen to cover what a C programmer builds first, written in Candor's primitives rather than with built-ins. Parse status: `python3 tools/run_tests.py spec/01-syntax.md`. **Semantics are unchecked**: no compiler exists.

| # | Program | What it exercises |
| :-: | :--- | :--- |
| 1 | `01_hashmap.cn` | generics without traits (function-pointer hash/eq), `slice` over `malloc`, replacing a struct through a pointer, `defer` cleanup |
| 2 | `02_tokenizer.cn` | slices as plain values stored in tokens, enums, `switch` on bytes |
| 3 | `03_arena_graph.cn` | self-referential heap nodes, slices over malloc, explicit DFS stack, `defer free` |
| 4 | `04_echo_server.cn` | C calls with no wrapper, return codes, `defer` per loop iteration, partial writes |
| 5 | `05_allocator_vec.cn` | a user allocator (struct of function pointers) and a growable `Vec[T]` built on it |
| 6 | `06_multi_conn_server.cn` | many connections each owning a heap buffer, by-value C structs, swap-remove, `poll` |

## Frictions found

- **Pointer types in expression position.** Explicit generic arguments are name-shaped (`spec/01-syntax.md` §5), so `foo[u8*](x)` needs an alias. `size_of(Node*)` was the common case; it is now a keyword form that takes a `Type`.
- **Error plumbing.** Programs 4 and 6 use return codes and early `return`; it is readable at this size (open question 3 in `docs/decisions.md`).
- **No struct equality or generic operators.** `01` passes `hash` and `eq` as function pointers, as in C's `qsort`.
- **Bugs the independent review found in the programs**: `03` could overflow its DFS stack (nodes marked when popped, not when pushed); `06` dropped unsent bytes on a partial `send`. Both fixed; both are bugs the language will not catch.
- **Review round 3:** `03` kept `seen` flags set, so a second traversal under-counted; it now resets them at the start. The cnparse lexer accepted non-ASCII digits, spaces and char literals and crashed on `²`; fixed with explicit ASCII classes and four new syntax-fail tests.
- **Review round 4:** `02` expected 9 tokens but `=` also counts (10); `ll1.py` printed conflicts yet exited 0, so every tool could pass on a conflicting grammar (now fixed, and the parser refuses such grammars); empty structs need a hidden byte in the C lowering (`spec/06-compiler.md` §4) and are not C-visible.
- **Review round 5:** `ll1.py` silently accepted malformed EBNF (a `{ ... ]` mismatch passed every check) and now validates delimiters, punctuation and full character consumption; `run_tests.py` resolved corpus paths against the working directory and passed with zero tests, and now resolves them from the repo root and fails on an empty suite. Slice bounds and indices must be `usize`. C-visibility is defined recursively in `spec/04-ffi.md` §2 (three new must-reject tests).
- **Review round 6:** the scope of a `let` and the operation rules of `distinct` were unspecified; both are now rules with five new must-reject tests.
- **Dangling is possible by design**: in `06`, `drop` frees `buf` and a stale `Conn` copy would dangle. The language will not stop it.

## Not tested

Any semantic rule: no checker exists. The 38 `tests/fail/` programs state what a compiler must reject, each with its rule on the first line.
