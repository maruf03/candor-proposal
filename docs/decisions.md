# Kore Decision Log

One entry per decision: what was chosen, what else was considered, and what it costs. **Provenance** says who decided: **Author** (the language's author chose it), **Approved** (proposed, then approved by the author), **Default** (an assumption approved as a batch). Entries marked *taste call* have no soundness argument either way.

Decisions are grouped by area. D-21 lists everything deferred and the condition for bringing it back.

---

## Memory and Ownership

### D-01: Borrows exist only for the duration of a call
**Author-driven, Approved.** References and slices are call-scoped: they appear as parameters and call arguments only; they cannot be returned, stored, bound to locals, or used as generic arguments. In one call, overlapping borrows must all be shared.
- *Why:* the author wanted a **small** language. The earlier design (returned borrows with elision, a `from` clause, liveness-based exclusivity) was sound only after five rounds of patching, and felt like Rust. Reading the litmus programs showed returned borrows were used in 5 places, 4 of them over `Copy` containers where a copy or an index does the job; stored borrows in 1 struct and 1 local.
- *Considered:* single-source elision (rejected, grew a provenance and scope-death rule set); `from` clauses (rejected as lifetime syntax in disguise); Hylo-style projections (comparable machinery); dropping borrow checking entirely (rejected, loses the safety pillar).
- *Cost:* getters return copies or indices; parsers pass their source to every call; no `Cursor` structs; `Mutex`-style guard APIs need a different shape when concurrency returns. Designs preserved in `deferred/returned-borrows.md`.

### D-02: Linear values, four states, destructuring as the base case
**Approved.** `linear struct` plus inference through wrappers; states Unconsumed / Consumed / Deferred / ErrDeferred; destructuring (`let T{ a, .. } = v;`, defining module only) consumes; no `forget`, no implicit drop, no partial moves; `swap` is the only way to replace a linear place through a borrow (D-18).
- *Why:* the previous version had no way to consume a value (its own example failed its own leak check) and linearity was not infectious.
- *Cost:* privacy is per directory, so a type's own module can forge values (`spec/03-memory.md` §1).

### D-04: `defer` is evaluated at exit; `errdefer` is path-exact
**Approved.** Names refer to variables, not snapshots; a deferred consume moves the variable to Deferred; `defer` may consume only variables of its own block and may not contain control flow; `errdefer` runs on error exits only and is cancelled statically on paths where the variable already moved. Defer bodies are lowered into the CFG before checking.
- *Why:* the earlier text left Deferred-then-move, inner-block defers, and defer order unspecified; two review rounds found real holes there.
- *Note:* `errdefer` is a convenience (the alternative is a cleanup in every `catch`, quadratic in the number of acquisitions). Kept because `litmus/01_hashmap.kr` is much cleaner with it. *Taste call.*

### D-05: Definite initialization; no zero-fill, no `Zero` marker
**Approved.** Every binding is initialized at declaration; struct literals name every field; arrays are `[v; n]`; `Buf[T].filled(n, v)`.
- *Why:* implicit zero-fill contradicted non-null pointers and fabricated linear handles. Removing it also removes the `Zero` marker, so `Copy` is the only marker.

### D-10: Raw pointers are inert in safe code; nullability is explicit
**Approved.** Safe code may create, copy, compare and pass raw pointers; dereference, arithmetic, pointer casts, integer-to-pointer and every C call need `unsafe(...)`. No flow-typed null narrowing: `is_null` and `unwrap_or_trap` instead.
- *Why:* narrowing is a flow analysis for a feature that, after D-01, only serves the FFI boundary.

### D-17: One `unsafe` form: `unsafe(expr)`
**Approved with a deviation.** The author approved adding `unsafe(expr)` *and keeping* `unsafe { ... }`. Both cannot coexist under LL(1): a statement starting with `unsafe` is ambiguous between the two forms (the checker reports a FIRST/FIRST conflict). Since every use in the litmus programs is a single expression, the block form was dropped. *Taste call* if you would rather have the block and drop the expression form: it needs `;` after the block or a different spelling.

### D-18: `swap` intrinsic
**Default, justified by D-03.** `litmus/01_hashmap.kr` cannot grow its table without replacing a linear field through `&mut self`. `swap(&mut a, &mut b)` is sound for any `T` including linear, because both values stay owned.

---

## Types and Errors

### D-06: Errors are `Result[T, E]`
**Author.** Replaces the `E!T` operator. An ordinary generic application: first-class, no precedence trap (`fn() -> E!T` used to misparse silently), aliasable (`type IoResult[T] = Result[T, IoError];`). `try` and `catch` stay. `E` is a fieldless enum; the error tag is ordinal + 1 internally, so error enums have no numbering restriction. `try` requires an identical error type (mapping uses `catch`). `unwrap_or` and `is_err` intrinsics; ignoring a `Result` is a compile error.
- *Considered:* Zig `E!T`, Swift/Java `throws` (not a value, cannot be stored).

### D-07: Generic arguments use `[T]` everywhere; conversion is `x as T`
**Author.** In expressions `[...]` parses as an index and semantic analysis decides, as in Go; the grammar is still LL(1) with no symbol table (mechanically verified). `as` is a keyword; a pointer target must be parenthesized (`p as (u8*)`) so `x as u8 * y` stays a multiplication. Intrinsics take types as ordinary arguments (`size_of(T)`).
- *Considered:* turbofish `::[T]` with `cast::[T](x)` (previous spelling, noisier), Rust angle brackets (still need `::<>`), `u64(x)` conversions (pointer targets unwritable).
- *Cost:* an explicit type argument in an expression must be name-shaped; pointer and function types need an alias.

### D-08: Arithmetic aborts on overflow; wrapping is an intrinsic
**Approved.** `+ - *` abort on overflow at every width in every build mode; `wrapping_add/sub/mul` wrap. Division and remainder abort on zero and `MIN / -1`; shifts mask; float-to-int saturates; evaluation is left to right.
- *Why:* silent wraparound let a size multiplication overflow in the earlier `Buf` code, producing an out-of-bounds write from safe code. Same behavior in debug and release keeps the "defined" promise simple.
- *Cost:* an overflow branch per operation; hashing uses `wrapping_mul`. *Taste call* (wrapping operators `+%` were rejected to keep the grammar small).

### D-09: `Buf[T]` is a built-in owning buffer; heap only; `Copy` elements
**Approved.** With no traits, no operator overloading and no returned borrows, a library type cannot offer `b[i]` or `b[lo..hi]`, so the one dynamic container is compiler-known. It always uses the C heap: there is no user `Allocator`, which removes the dangling-allocator hole the earlier design had. No resizing or cloning.

### D-11: No tuples
**Approved.** Removes a type form, a literal, a pattern, an ABI rule, and `.0` access. Multiple results use a small struct.

### D-14: All structs use C layout
**Approved.** Matches the C-interop pillar and keeps layout predictable; no reordering. Revisit only if profiling shows padding costs. Non-C-visible types (slices, `Result`, `Buf`) have compiler-chosen layout.

### D-16: Enums are fieldless; no integer-to-enum conversion
**Default.** Tagged unions are deferred (D-21). Enums are excluded from `extern` signatures so an out-of-range C value cannot become an invalid enum.

---

## Syntax

### D-12: No attributes; every extern call is `unsafe`
**Default, by D-03.** `[packed]` and `[align]` had no litmus use; `[safe]` was replaceable by a one-line wrapper and was unsound for pointer parameters. Removing attributes deletes a grammar rule and a concept.

### D-13: Rust-style operator precedence
**Approved.** Bitwise operators bind tighter than comparison, looser than `+`/`-`; comparison is non-associative; `as` binds tighter than `*`. `flags & MASK == 0` means `(flags & MASK) == 0`. *Taste call.*

### D-15: No `with`; no coroutines
**Approved.** `with` hid a call and is exactly `let g = ...; defer g.unlock();` over a linear guard. `yield` and `Task` had no executor, cancellation, or frame-size story.

### D-19: The grammar is enforced by a script
**Approved.** `spec/01-syntax.md` holds the only copy of the grammar; `tools/ll1.py` must report 0 conflicts; `tools/kparse.py` must parse `litmus/` and `tests/`; `tools/check_keywords.py` must agree with the keyword box. The earlier grammar claimed LL(1) and had 13 conflicts.

---

## Process and Scope

### D-03: Feature-admission rule
**Approved.** A new feature needs a program that cannot be written without it, and must displace something. Applied retroactively: attributes, `case` ranges, anonymous functions, `[safe]`, and exported `extern "C"` functions were cut because no litmus program used them; `swap` was added because the hash map needed it.

### D-20: Rust compiler, C backend, version control from the start
**Approved.** See `spec/06-compiler.md`. The ownership prototype (M0) comes before the parser.

### D-21: Deferred features and when they come back

| Feature | Why deferred | Returns when |
| :--- | :--- | :--- |
| Threads, atomics, `Mutex`, `Send`/`Sync`, coroutines (D-22) | no safe sharing design under call-scoped borrows; coroutines unsound as drafted | the ownership checker works single-threaded and a program needs concurrency |
| Returned / stored borrows | see D-01 | litmus programs where copies and indices are demonstrably unacceptable |
| Tagged unions, pattern matching | multiplies the linearity/`Copy` rules | `Result` and `?T*` cannot express a needed program |
| Traits, user bounds | size of the checker | hashing and ordering via function pointers proves too painful |
| Closures, anonymous functions | no litmus use | a callback API that cannot take a named function plus a context |
| Globals, `static` | no litmus use; also blocks aliasing arguments | singletons or counters needed |
| User allocators, regions | dangling-allocator hazard (earlier L5-1) | a safe design such as typed handles |
| Containers of linear elements | needs destroy semantics without traits | a program needs `Buf[Fd]` |
| C callbacks, variadics, unions, exported functions, by-value structs | no litmus use | an FFI program needs them |
| `.kpkg`, registry, LSP, PGO, LLVM backend, non-Linux targets | not language design | after M4 of `spec/06-compiler.md` |

### D-22: Single-threaded for v1
**Approved.** `deferred/concurrency-and-intrinsics.md` keeps the earlier thread, atomics and `Mutex` material as a design sketch; it is not specified and its code no longer typechecks against the current rules.

---

## What Changed From the Drafts, and What Was Learned

| Draft (v0.x) | v1 | Reason |
| :--- | :--- | :--- |
| `E!T`, `::[T]`, `cast::[T](x)` | `Result[T, E]`, `[T]`, `x as T` | D-06, D-07 |
| returned borrows, elision, `from`, liveness | call-scoped borrows | D-01 |
| `Zero`, `Send`, `Sync`, `zeroed` | only `Copy` | D-05, D-22 |
| `with`, `yield`, `Task`, `[safe]`, attributes, tuples, anonymous fns, `case` ranges | removed | D-03, D-11, D-12, D-15 |
| `Allocator` struct, `Region`, `VM`, `Futex`, atomics | built-in heap `Buf`; the rest deferred | D-09, D-22 |
| flow-typed null narrowing | `is_null`, `unwrap_or_trap` | D-10 |
| "Accepted" RFCs, 27/29/31 keywords | one numbered spec; keyword box checked by script | D-19 |

Lessons that shaped v1: an "LL(1)" claim is false until a tool says so; every convenience default (zero-fill, wrap-on-overflow, implicit casts) produced a soundness hole somewhere else; documentation drifted unless a script checked it; and writing real programs early found more than reviewing prose did.

## Open Questions

1. Does the call rule hold up in an implementation? (M0, `spec/06-compiler.md`.)
2. Are copies and indices enough for real programs, or will returned borrows be needed again? (`docs/litmus.md`.)
3. Concurrency: what is the minimal safe design under call-scoped borrows (scoped threads, ownership transfer by `Buf` move)?
4. Containers of linear values and user allocators.
