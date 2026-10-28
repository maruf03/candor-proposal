# Kore 6: Compiler Plan

How to build a Kore compiler. This chapter is a plan, not a language rule: nothing here constrains programs. Status: **no compiler exists yet**; the grammar has tools (`tools/`), everything else is specification.

---

## 1. Decisions

| Question | Choice | Why |
| :--- | :--- | :--- |
| Implementation language | **Rust** | sum types fit ASTs and checkers; installed and maintained on the author's machine |
| Backend | **emit C, compile with clang** (LLVM IR is a later backend, `deferred/llvm-backend.md`) | struct layout and C calls come free; `restrict`, overflow builtins and sanitizers are available; no LLVM binding to maintain |
| Parser | hand-written recursive descent following the grammar in `spec/01-syntax.md` | one-token lookahead; `tools/ll1.py` stays in CI as a guard against grammar drift |
| Version control | git from the first commit | the v0.x history exists as one snapshot commit |

## 2. Pipeline

```
 .kr files
    │  1. lex + parse (per file)                  → AST, syntax errors
    │  2. modules: collect, resolve imports       → module graph (DAG check)
    │  3. declarations: types, layouts, signatures
    │  4. typecheck bodies                        → typed AST
    │       bidirectional literals, Result coercions, bounded generics (checked once)
    │  5. ownership check on a CFG                → borrows (call rule), linear states,
    │       defer/errdefer lowered into the CFG at every exit edge
    │  6. monomorphize                            → concrete functions and types
    │  7. emit C                                  → one .c file per module
    │  8. clang -O2 -fno-strict-aliasing          → native binary (+ sanitizer builds for tests)
```

Stages 1-5 are shared by `kore build` and any future language server.

## 3. The Ownership Check (stage 5)

Small by design (`spec/03-memory.md`):

- **Call rule**: for each call, collect the borrow arguments, compute places, and compare pairs for overlap (prefix relation; element paths collapse). No liveness analysis.
- **Placement rule**: a syntactic check that borrow types and expressions appear only where `spec/03-memory.md` §2.1 allows.
- **Linear states**: a dataflow over the CFG with the four states and the rules for joins, loop back-edges and exits. `defer` and `errdefer` bodies are expanded into the CFG at every exit edge, LIFO, **before** this analysis runs, so cleanup is checked like any other code.
- **Initialization**: definite assignment and the all-fields struct literal rule.

Because the checker decides whether `restrict` is emitted (§4), it is part of the trusted base.

## 4. Lowering to C

| Kore | C |
| :--- | :--- |
| `i32`, `u64`, ... | `int32_t`, `uint64_t`, ... |
| `+ - *` | `__builtin_add_overflow` family; on overflow `__builtin_trap()` |
| `wrapping_*` | unsigned arithmetic, converted back |
| `/ %` | explicit guards for zero and `MIN / -1`, then the C operator |
| `<< >>` | mask the amount to `N - 1`, then shift (arithmetic `>>` on signed) |
| `as` | C casts for integer widening and narrowing; saturating helper for float to int |
| bounds checks | `if (i >= len) __builtin_trap();` before every index and slice |
| `T[]` / `const T[]` | `struct { T* ptr; size_t len; }` |
| `&mut T`, exclusive slice param | `T* restrict`; `&const T` and shared slice: `const T* restrict` |
| `struct` | C struct (same field order; C layout is the language rule) |
| `enum` | the backing integer type, with `switch` default `__builtin_trap()` |
| `Result[T, E]` | `struct { uint32_t tag; T payload; }`, tag 0 success, error ordinal + 1 |
| `Buf[T]` | `struct { T* ptr; size_t len; }` with `malloc`/`free`, size overflow checked |
| `defer` / `errdefer` | cleanup code duplicated at each exit edge (or `goto` to a cleanup chain), LIFO |
| `try` | `if (r.tag != 0) return err(r.tag)` after running pending cleanups |
| `unsafe(e)` | `e` verbatim |
| `trap()` / `unreachable()` | `__builtin_trap()` |
| `extern "C"` import | a prototype with the platform C signature |

Defined behavior in C is secured by never emitting an operation that has undefined behavior: overflow, division, shifts and bounds are all guarded explicitly, so `-fwrapv` is not required (it may be added as defense in depth).

## 5. Milestones

Estimates are rough (one experienced engineer, part of a year in total). The order is the point.

| # | Milestone | Done when | Rough size |
| :-: | :--- | :--- | :--- |
| M0 | **Ownership prototype**: toy IR in Rust implementing the call rule, linear states and defer lowering | accepts `litmus/`, rejects every file in `tests/fail/` for the right reason | 1-2 weeks |
| M1 | Parser (recursive descent) and a pretty-printer | round-trips `litmus/`, rejects `tests/syntax_fail/` | ~3 weeks |
| M2 | Name resolution, type checker, layouts, C emission | litmus 02 and 03 compile and run | ~5 weeks |
| M3 | Port the M0 checker onto the real AST | `tests/fail/` all rejected by the real compiler | ~3 weeks |
| M4 | Generics, `Buf`, `Result`, `try`/`catch`, `defer`/`errdefer` | litmus 01, 04, 05 run | ~4 weeks |
| M5 | Hardening: sanitizer oracle, fuzzing, error messages | no sanitizer report on any accepted program in the corpus | ongoing |

**M0 first is deliberate.** The ownership check is the only unproven part of the design. If the call rule needs special cases the spec did not anticipate, the memory model must change before anything else is built.

## 6. Tests

| Suite | Location | Expectation |
| :--- | :--- | :--- |
| accept | `litmus/*.kr` | compiles, runs, correct output |
| compile-fail | `tests/fail/*.kr` | rejected; the diagnostic mentions the rule named on the first line (`// ERROR: ...`) |
| syntax-fail | `tests/syntax_fail/*.kr` | rejected by the parser |
| grammar | `tools/ll1.py`, `tools/check_keywords.py` | 0 conflicts, keyword lists agree |
| soundness oracle | generated programs | any program the checker accepts, built with ASan and UBSan, must run without a sanitizer report |

Run today: `python3 tools/run_tests.py spec/01-syntax.md`.

## 7. Diagnostics

Every compile-fail rule has one stable message and a source span; messages name the rule and suggest the fix (for example `a borrow cannot be returned: return a copy or an index`). The first line of each `tests/fail` file is the message a conforming compiler should produce.
