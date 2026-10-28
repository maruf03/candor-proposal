# Litmus Programs and Test Corpus

Five realistic programs in `litmus/` and 45 small programs in `tests/`. They exist to find where the rules hurt **before** a compiler is built.

**What is verified, and what is not.**
- **Syntax: mechanically.** `python3 tools/run_tests.py spec/01-syntax.md` checks that every litmus and `tests/fail` program parses and every `tests/syntax_fail` program is rejected.
- **Semantics: by hand.** There is no type checker or ownership checker yet. Each program was walked against `spec/02-types.md` and `spec/03-memory.md` manually; the 35 `tests/fail` programs are the checker's acceptance tests (each starts with `// ERROR: <rule>`). The first milestone of `spec/06-compiler.md` is a prototype that accepts `litmus/` and rejects `tests/fail/`.

## The Programs

| # | Program | Exercises | Result under the v1 rules |
| :-: | :--- | :--- | :--- |
| 1 | `01_hashmap.kr` | `Copy`-bounded generics, function-pointer "interfaces", linear owner, `errdefer`, `swap`, `Result`/`try`, `wrapping_mul` | Passes. Needed `swap` (admitted under D-03). Verbose constructor: filler values and two function pointers |
| 2 | `02_tokenizer.kr` | indices instead of stored views, slicing as a call argument, `else if`, `switch` on a byte | Passes. A lexer cannot own or return its source or token text; every call passes `src` and callers slice at the use site |
| 3 | `03_arena_graph.kr` | `distinct` indices, `Buf` indexing and element assignment, explicit-stack DFS, `defer`, `errdefer` | Passes cleanly. This is the pattern the language recommends for cyclic data |
| 4 | `04_echo_server.kr` | `extern "C"`, `unsafe(...)` per call, linear `Fd`, `defer` per loop iteration, `?T*` at the C boundary, slices as borrows | Passes. All C access is eight `unsafe(...)` expressions in one module |
| 5 | `05_typed_arena.kr` | typed handles, generics over `Copy`, recursion that borrows the arena, mapping two error enums with `catch` | Passes. The "no error widening" rule is visible and mildly annoying |

## What They Showed

**Costs of the call-scoped borrow model (D-01):**
- **No stored views.** A tokenizer cannot hold its input; it takes `src` on every call. Safe but easy to misuse (pass a different buffer next time).
- **Getters copy.** `Buf` and `Arena.get` return `T` by value. Fine for `Copy` elements; large records are read field by field or by index.
- **No `Cursor`-style context structs.** Parsers pass state as parameters.

**Costs of other decisions:**
- **No traits (D-16).** `Map` takes `hash` and `eq` function pointers and filler values; every instantiation repeats them.
- **Exact error types for `try` (D-06).** Litmus 5 maps `AllocError` to `ArenaError` by hand with `catch`.
- **`Buf` has no resize.** `Map.grow` allocates a bigger map, re-inserts, and `swap`s.

**Validated:**
- Linear `Fd` plus `defer` in a loop closes a descriptor on every path (litmus 4).
- `errdefer` keeps three-step initialization readable (litmus 1, 3).
- `unsafe(expr)` makes the FFI layer small and greppable.
- Index handles need no references at all for graphs and trees (litmus 3, 5).

## Bugs the Exercise Found (kept as lessons)

| Bug | Caught by | Fix in v1 |
| :--- | :--- | :--- |
| `Buf` size multiply wrapped while `count` stayed large: an out-of-bounds write from safe code | review of the earlier draft | overflow aborts (D-08); `filled` reports `OutOfMemory` |
| `mmap` failure compared with `NULL`; C returns `MAP_FAILED` | writing the `extern` honestly | FFI chapter: translate C return conventions at the boundary |
| a stateful allocator handle could dangle from safe code | soundness walk | no user allocators (D-09) |
| `[safe]` on `close` let safe code close a descriptor owned by a linear `Fd` | review | attributes removed; every C call is `unsafe(...)` (D-12) |
| SIGPIPE killed the echo server on a closed peer | review | `send(..., MSG_NOSIGNAL)` |
| hash-map growth could not be written without replacing a linear field | rewriting litmus 1 | `swap` intrinsic (D-18) |

## Not Tested

Concurrency, generic instantiation errors, `distinct` beyond `as`, multi-directory modules, and anything performance-related.
