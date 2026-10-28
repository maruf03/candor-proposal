# Litmus Programs

Six programs that must parse today and compile once a compiler exists. They are chosen to cover what a C programmer builds first, written in Kore's primitives rather than with built-ins. Parse status: `python3 tools/run_tests.py spec/01-syntax.md`. **Semantics are unchecked**: no compiler exists.

| # | Program | What it exercises |
| :-: | :--- | :--- |
| 1 | `01_hashmap.kr` | generics without traits (function-pointer hash/eq), `slice` over `malloc`, replacing a struct through a pointer, `defer` cleanup |
| 2 | `02_tokenizer.kr` | slices as plain values stored in tokens, enums, `switch` on bytes |
| 3 | `03_arena_graph.kr` | self-referential heap nodes, pointer arithmetic, explicit DFS stack, `defer free` |
| 4 | `04_echo_server.kr` | C calls with no wrapper, return codes, `defer` per loop iteration, partial writes |
| 5 | `05_allocator_vec.kr` | a user allocator (struct of function pointers) and a growable `Vec[T]` built on it |
| 6 | `06_multi_conn_server.kr` | many connections each owning a heap buffer, by-value C structs, swap-remove, `poll` |

## Frictions found

- **Pointer types in expression position.** Explicit generic arguments are name-shaped (`spec/01-syntax.md` §5), so `foo[u8*](x)` needs an alias. `size_of(Node*)` was the common case; it is now a keyword form that takes a `Type`.
- **Error plumbing.** Programs 4 and 6 use return codes and early `return`; it is readable at this size (open question 3 in `docs/decisions.md`).
- **No struct equality or generic operators.** `01` passes `hash` and `eq` as function pointers, as in C's `qsort`.
- **Dangling is possible by design**: in `06`, `drop` frees `buf` and a stale `Conn` copy would dangle. The language will not stop it.

## Not tested

Any semantic rule: no checker exists. The 27 `tests/fail/` programs state what a compiler must reject, each with its rule on the first line.
