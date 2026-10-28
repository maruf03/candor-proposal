# Kore 6: Compiler Plan

How to build a Kore compiler. This chapter is a plan, not a language rule: nothing here constrains programs. Status: **no compiler exists yet**; the grammar has tools (`tools/`), everything else is specification.

---

## 1. Decisions

| Question | Choice | Why |
| :--- | :--- | :--- |
| Implementation language | **Rust** | sum types fit ASTs and checkers; installed and maintained on the author's machine |
| Backend | **emit C, compile with clang** (LLVM IR is a later backend, `deferred/llvm-backend.md`) | struct layout and C calls come free; overflow builtins and sanitizers are available; no LLVM binding to maintain |
| Parser | hand-written recursive descent following the grammar in `spec/01-syntax.md` | one-token lookahead; `tools/ll1.py` stays in CI as a guard against grammar drift |
| Version control | git from the first commit | the v0.x history exists as one snapshot commit |

## 2. Pipeline

```
 .kr files
    │  1. lex + parse (per file)                  → AST, syntax errors
    │  2. modules: collect, resolve imports       → module graph (DAG check)
    │  3. declarations: types, layouts, signatures
    │  4. typecheck bodies                        → typed AST
    │       bidirectional literals, const checks, switch exhaustiveness
    │  5. monomorphize                            → concrete functions and types
    │  6. emit C                                  → one .c file per module
    │  7. clang -O2 -fno-strict-aliasing          → native binary (+ sanitizer builds for tests)
```

Stages 1-4 are shared by `kore build` and any future language server.

## 3. Checks That Exist

Small by design, because nothing tracks ownership or aliasing (`spec/03-memory.md` §1): types and conversions, literal ranges, constant division and shifts, `const` pointer writes, immutable bindings, struct literal completeness, enum switch exhaustiveness, `defer` body restrictions, break/continue placement, missing returns, field/method name clashes, visibility.

## 4. Lowering to C

| Kore | C |
| :--- | :--- |
| `i32`, `u64`, ... | `int32_t`, `uint64_t`, ... |
| `+ - *` | `__builtin_add_overflow` family; on overflow `__builtin_trap()` |
| `wrapping_*` | unsigned arithmetic, converted back |
| `/ %` | explicit guards for zero and `MIN / -1`, then the C operator |
| `<<` | mask the amount to `N - 1`; shift in the unsigned type of the same width, convert back (no signed-shift UB) |
| `>>` | mask the amount to `N - 1`; signed operands use C's arithmetic shift (clang and gcc define it), unsigned the logical one |
| `as` | C casts for integers and pointers; saturating helper for float to int |
| calls and operators with several operands | every operand and argument with side effects goes to a temporary in Kore's left-to-right order, because C leaves `f(g(), h())` unspecified |
| array and slice index | `if (i >= len) __builtin_trap();` before every index and slice; pointer index is plain C |
| `T[]` / `const T[]` | `struct { T* ptr; size_t len; }` |
| `struct` | C struct (same field order; C layout is the language rule) |
| `enum` | the backing integer type, with `switch` default `__builtin_trap()` |
| `defer` | cleanup code duplicated at each exit edge (or `goto` to a cleanup chain), LIFO |
| `trap()` | `__builtin_trap()` |
| `slice(p, n)` | `(Slice_T){ p, n }` |
| `p + n` | `p + n` (pointer arithmetic is C's) |
| `extern "C"` import | a prototype with the platform C signature |

The C the compiler emits never contains an operation with undefined behavior for arithmetic, shifts or array and slice bounds: all are guarded explicitly, so `-fwrapv` is not required (it may be added as defense in depth). Pointer dereferences are emitted as written; they are the program's responsibility.

## 5. Milestones

Estimates are rough (one experienced engineer). The order is the point.

| # | Milestone | Done when | Rough size |
| :-: | :--- | :--- | :--- |
| M0 | Parser (recursive descent) and a pretty-printer | round-trips `litmus/`, rejects `tests/syntax_fail/` | ~3 weeks |
| M1 | Name resolution, type checker, layouts, C emission (no generics) | litmus 02 and 04 compile and run | ~5 weeks |
| M2 | Generics, `defer`, function pointers, all intrinsics | litmus 01, 03, 05, 06 run | ~4 weeks |
| M3 | Diagnostics and hardening: every `tests/fail/` file rejected for the named rule; UBSan on the emitted C | clean on the corpus | ongoing |

With no ownership analysis, the type checker is the whole front end, so a working compiler is reachable much sooner than under the earlier borrow/linear design (`deferred/ownership-checking.md`).

## 6. Tests

| Suite | Location | Expectation |
| :--- | :--- | :--- |
| accept | `litmus/*.kr` | compiles, runs, correct output |
| compile-fail | `tests/fail/*.kr` | rejected; the diagnostic mentions the rule named on the first line (`// ERROR: ...`) |
| syntax-fail | `tests/syntax_fail/*.kr` | rejected by the parser |
| grammar | `tools/ll1.py`, `tools/check_keywords.py` | 0 conflicts, keyword lists agree |
| emitted C | all accepted programs, built with UBSan | no report from arithmetic, shift or bounds checks |

Run today: `python3 tools/run_tests.py spec/01-syntax.md`.

## 7. Diagnostics

Every compile-fail rule has one stable message and a source span; messages name the rule and suggest the fix (for example `cannot write through a const pointer`). The first line of each `tests/fail` file is the message a conforming compiler should produce.
