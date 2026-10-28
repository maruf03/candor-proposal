# Kore Decision Log

One entry per design decision, newest spec version first. Each entry says what was decided, what else was considered, and what it costs. **Status** is `Decided` (in the RFCs) or `Provisional` (a direction chosen to unblock work; revisit when evidence arrives). These decisions were made on 2026-10-28 in response to `DESIGN_REVIEW.md`; the author may overrule any of them, and where a decision is a taste call it says so. **All of them are the assistant's proposals and stay unratified until the author approves them.** `Provisional` means a direction chosen to unblock work; `Decided (direction only)` means the choice is made but the RFC text has not been rewritten to match.

## Syntax (RFC 0002)

### D-001: Explicit `::[T]` for type arguments in expressions; casts are `cast::[T](x)` (SUPERSEDED by D-023)
* **Superseded** (kept for the record; the author chose Go-style brackets and `as`). In type position `Vec[i32]`; in expression position `Vec::[i32].init()`, `size_of::[T]()`. The `(Type) expr` cast is removed.
* **Considered:** Go-style "parse `[...]` as expression-or-type and resolve in sema" (rejected: types like `u8*` and `?T*` are not expressions); `as` keyword (rejected: `x as u8 * y` is ambiguous with pointer types and costs a keyword); angle brackets (rejected: `>>` and comparison ambiguity).
* **Cost:** `::` noise at generic call sites (turbofish). **Taste call.**

### D-022: Error unions are the prelude type `Result[T, E]`; the `E!T` operator is removed
* **Decided (author's choice, 2026-10-28).** `Result[T, E]` is an ordinary generic application (`Result[void, E]` for no payload), with `try`/`catch` unchanged. Generic aliases shorten families: `type IoResult[T] = Result[T, IoError];`.
* **Considered:** Zig's `E!T` (the previous spelling; compact, but the `!` binds loosest and `fn() -> E!T` silently misparsed as `(fn() -> E)!T`); a Swift/Java `throws` clause (reads well, but a result would not be a value: no storing, no `Buf[Result[..]]`, no channels).
* **Cost:** longer signatures. **Gain:** no special type syntax, no precedence trap, first-class values. Lowering and the tag-0 rule are unchanged (RFC 0003 §5, D-018).

### D-023: Generic arguments use `[T]` everywhere (Go-style); conversions are `x as T`
* **Decided (author's choice, 2026-10-28; supersedes D-001).** In expressions, `[...]` takes an expression list and parses as an index; semantic analysis decides index versus generic application, so the parser still needs no symbol table (verified: `tools/ll1.py` 0 conflicts). Conversions are `expr as T`; the type after `as` may not end in `*` (write `p as (u8*)`), which keeps `x as u8 * y` a multiplication. `cast`, `::` and `E!T` are gone; `as` is a new keyword (29 keywords + 3 literals = 32). Intrinsics take type arguments as ordinary arguments: `size_of(T)`, `align_of(T)`, `zeroed(u8[4096])`.
* **Considered:** Rust-style `Vec<T>` with `::<T>` turbofish (still needs `::` in expressions); `u64(x)` Go-style conversions (no keyword, but pointer targets cannot be written as a callee and chains read inside-out); keeping `::[T]` and `cast::[T](x)`.
* **Cost:** one keyword; explicit type arguments in an expression must be expression-shaped (names, qualified names, bracket suffixes). Pointer, nullable and function types need a `type` alias or inference.

### D-002: LL(1) is enforced by a script, not by assertion
* **Decided.** The RFC 0002 EBNF block is the only copy of the grammar; `tools/ll1.py` must report 0 conflicts and `tools/kparse.py` must parse `litmus/*.kr` before any grammar change merges. v0.2's grammar had 13 conflicts.
* Fixes made to reach 0: trailing-comma lists made right-recursive; `&` must be followed by `mut`/`const`; fn types take no suffix (`(fn() -> u8)*` needs parentheses); field access and call are separate postfix ops; tuples are expressions; one `VarStmt`.

### D-003: Remove `with`
* **Decided.** `with (g = m.lock()) {}` hid a call (teardown) and needed a protocol the spec never defined. It is exactly `let g = m.lock(); defer g.unlock();` once `lock()` returns a linear guard, so the keyword adds nothing.
* **Cost:** one extra line at each use. **Gain:** a keyword gone, Pillar 1 ("no hidden calls") restored. **Taste call:** the guard-plus-`defer` form is sound, but `with` is a legitimate alternative.

### D-004: Add `errdefer`
* **Decided.** Litmus 1's three-step initialization is much cleaner with it (Zig's `errdefer`); the alternative is an explicit cleanup in every `catch`, quadratic in the number of acquisitions. It is a convenience, not a necessity. Semantics in RFC 0003 Rule 4.

### D-005: Add `try`; make `catch` a postfix on any expression
* **Decided.** `try f()` returns the error from the enclosing function; `f() catch (e) { ... }` works as a statement, in `let`, in `return`. v0.2 allowed `catch` only after `let x = ...` and had no propagation.
* **Cost:** a keyword. `try` is hidden control flow, but it is visible at the call site, as Zig/Swift treat it. **Taste call** on the exact shape (`try`/`catch` versus `?`/`unwrap_or`).

### D-006: Rust-style precedence, comparison non-associative, no ternary
* **Decided.** Bitwise ops bind tighter than comparison, looser than `+`/`-`. `flags & MASK == 0` means `(flags & MASK) == 0` (Rust's behavior) instead of C's surprising `flags & (MASK == 0)`; only chained comparisons like `a < b == c` are syntax errors. **Taste call.** Reserved words are counted by `tools/check_keywords.py`, which compares the RFC 0002 box, the grammar terminals and `tools/kparse.py`: 29 keywords + 3 literals = 32 after D-023 added `as` (v0.2 said 27, 29, and listed 31).

## Memory model (RFC 0003)

### D-007: Slices are borrows
* **Decided.** `T[]` / `const T[]` follow the second-class rules of `&mut` / `&const`. Owned, storable memory is a linear library type (`Buf[T]`).
* **Considered:** leaving slices free (rejected: dangling slice into a freed buffer in safe code, the review's C1); making slices owned only (rejected: kills `fn f(data: const u8[])`).
* **Cost:** a parser cannot hold its source in a normal struct (LITMUS L2-1). Mitigated by D-010 and borrowing structs.

### D-008: Raw pointers are inert in safe code
* **Decided.** Safe code may create, copy, compare, store, and pass `T*`; deref, arithmetic, pointer-to-pointer casts, integer-to-pointer, and non-`[safe]` extern calls need `unsafe`.
* **Why:** the review found no rule for when safe code could dereference `T*`; either answer was unsound or made the spec's own `Mutex` example ill-typed.

### D-009: Cut coroutines (`yield`, `Task[T]`) from v0.3
* **Decided (Provisional).** No executor, `await`, cancellation, or frame-size story existed; the example spun on `MSG_DONTWAIT`; frames stored slices past their sources; function colouring unaddressed. RFC 0004 §4.2 is marked deferred and `yield` is no longer reserved. Async I/O is a library concern (event loop + owned buffers) until a safe design exists.
* **Revisit** after threads and `Send`/`Sync` are fixed.

### D-010: Returning borrows is allowed by single-source elision
* **Provisional (awaiting author ratification).** A function may return a borrowing type iff it has exactly one borrowing parameter; the result is borrowed from it. No lifetime syntax.
* **Considered:** forbidding all borrow returns (rejected: no `get`, `first`, iterators, `Mutex` access; the spec's own `lock()` needed it); Hylo-style subscripts (viable, more machinery); Rust-style named lifetimes (violates the language's premise); keeping v0.2's ban (rejected after litmus 1).
* **Cost:** APIs mixing two borrowed inputs must take indices or copies (LITMUS L2-3). **This is the single biggest bet in the language** and should be re-examined after more programs.

### D-011: Exclusivity and freezing are checked by liveness, not at call sites
* **Decided.** Borrow lifetime = last use of the borrow or anything derived from it (non-lexical, per function). Shared borrows freeze their place. Array/slice element places collapse. Two-phase receivers allow `v.push(v.len())`. Reborrowing a reference param counts as a use.
* **Why:** v0.2's call-site rule missed `f(p, p)`, live `&const` across a freeing call, and slices.

### D-012: `noalias` is emitted only for checked properties
* **Decided.** `noalias` on `&mut` and mutable slices; `readonly noalias` on `&const`/const slices of non-interior-mutable types. If the checker is wrong, codegen is wrong, so the checker is part of the trusted base. A `--no-noalias` compiler flag is planned as an escape hatch while the checker matures; no RFC specifies it yet.

### D-013: Linearity is infectious; destructuring is the base case
* **Decided.** Anything containing a linear component is linear. `let T{ a, b, .. } = v;` (defining module only) consumes `v`; `..` skips only `Copy` fields. No `forget`, no implicit drop, no partial moves, no assigning over a live linear place. Joins must agree; loop-carried linear state must be loop-invariant.
* **Why:** the review showed `PageArena.destroy(self)` failed its own leak check and `struct W{ h: Handle }` was copyable.

### D-014: `defer` is evaluated at exit and puts the variable in `Deferred`
* **Decided.** Names refer to variables (not snapshots); `Deferred` permits borrows and `Copy` field reads, forbids moves; the return operand is evaluated before defers; defers cannot `return`/`break`/`continue`/`try`. `errdefer` runs on error exits only and cancels itself on paths where the variable was already moved.

### D-015: Definite initialization replaces blanket zero-fill
* **Decided.** Every binding is initialized at declaration; struct literals list every field; `zeroed::[T]()` exists only for `Zero` types. Removes the non-null-pointer contradiction, fabricated `linear` handles, and the hidden `memset`.

### D-016: Generics have built-in marker bounds; borrowing types are never generic arguments
* **Decided (Provisional).** `[T: Copy + Zero + Send + Sync]` only; no user traits. Bodies are checked once against the bounds, not at each instantiation. Unbounded `T` is "possibly linear": move-only, no comparison/arithmetic, so comparators and hashers are passed as function pointers (LITMUS L1-2).
* **Cost:** no `HashMap[K, V]` with `K: Hash`; verbose constructors. A real trait system is the obvious next step if this proves too painful.

### D-017: Kore-internal calling convention; platform C ABI only at `extern` boundaries
* **Decided (direction only).** `Result[T, E]`, tuples, and slices use a Kore convention chosen for speed; `extern "C"` imports and exports use the platform C ABI and may not mention `Result[T, E]`, tuples, or slices. **RFC 0003 §5 and RFC 0005 §5.2 still contain the old register assignments** and need rewriting (the review found them wrong for mixed int/float payloads, the sret register, and Windows x64).

### D-018: Error enums reserve 0
* **Decided.** `Result[T, E]` tag 0 is success, so an error enum may not have a variant equal to 0 (the compiler rejects it). Errors are fieldless enums in v0.3. **Taste call:** a separate success flag would allow a 0-valued error at the cost of a wider return.

### D-019: Safe std exposes only stateless allocators
* **Decided (Provisional).** A stateful allocator handle stored in a `Buf` can dangle from safe code (LITMUS L5-1). `heap()` is the safe allocator; regions give out typed indices; pointer-returning arenas are `unsafe` contracts. A real answer (regions, generational handles) is open.

### D-020: Casts are defined, never UB
* **Decided.** `cast::[T](x)`: integer narrowing truncates, widening sign/zero-extends by source type, float to int saturates with NaN to 0, int to enum is not a cast, pointer-involving casts need `unsafe`. **Taste call** (saturating float-to-int versus trapping).

## Process

### D-021: All RFCs are Draft; Accepted requires a compiling litmus program
* **Provisional (the Draft status itself is uncontroversial; the exact Accepted gate is a proposal).** Every RFC was "Accepted" with the same creation date and no implementation. All six are now **Draft**. An RFC moves to Accepted only when (a) its grammar passes `tools/`, (b) the litmus programs relevant to it type-check in a working compiler, and (c) its open issues list is empty.

---

## Status of Review Findings

IDs refer to `DESIGN_REVIEW.md`. **Resolved** = spec text now answers it. **Direction** = decided but spec text not fully rewritten. **Open** = not addressed in this pass (outside the requested scope).

| Finding | Status | Where |
| :--- | :--- | :--- |
| A1 `lock()` returns `&mut`, contradicts Rule 1 | Resolved at the type level (D-003, D-010; RFC 0004 §4.1 rewritten); **open:** how a mutex reaches another thread, `Mutex` construction, interior mutability | RFC 0004 |
| A2 slices bypass Rule 1 | Resolved | D-007 |
| A3 raw pointer validity | Resolved | D-008 |
| A4 `PageArena.destroy` fails Rule 3 | Resolved | D-013; RFC 0006 §2.2 uses destructuring |
| A5 zero-init vs non-null | Resolved | D-015 |
| A6 `noalias` on under-checked rules | Resolved in spec; **implementation risk remains** | D-011, D-012 |
| A7 live `&const` doesn't freeze | Resolved | D-011 |
| A8 error-union ABI wrong | Direction | D-017 (RFC text not rewritten) |
| A9 `api.kr.d` breaks by-value ABI | **Open** (recommend cutting `.kpkg` from v1) | n/a |
| A10 grammar not LL(1) | Resolved, mechanically checked | D-001, D-002 |
| Linear: infectious, `defer` holes, loops, shadowing, partial moves | Resolved | D-013, D-014 |
| Linear containers (`Vec[LinearT]`) | **Open** | RFC 0003 §6, LITMUS L1-1 |
| Missing `catch` forms, `switch else`, `errdefer`/`try`, lexical spec, precedence table, `sizeof`, `[packed]` | Resolved | RFC 0002 |
| Send/Sync, thread lifetime, `Sync` unused, atomics API, memory model | **Open** | RFC 0004 banner |
| `Task[T]` execution model | Cut from v0.3 | D-009 |
| `VM`/`Futex`/`CPU` as compiler magic, enum values wrong | **Open** | RFC 0004 banner |
| UB table: shifts, division widths, float casts, eval order, padding | Shifts and casts and padding addressed; **division widths, eval order, stack probes open** | RFC 0001 §4, D-020 |
| Sum types, globals/`static`, closures, string/char types | Char and string literals specified; **rest open** | RFC 0002 §3 |
| Keyword counts, README links, all-"Accepted" status, missing README sections | Resolved | D-006, D-021, README |
| Go + LLVM tension, LSP latency claim, `.kpkg` IP claim, platform claims, effort | **Open** | n/a |
| Litmus programs and conformance tests | Litmus done (5); **no conformance suite yet** | `LITMUS.md` |
| Split `extern struct` (C layout) from plain `struct` (free to reorder) | **Open** | RFC 0003 §2.2 |
| `i64.min` / literal range semantics | Partly: RFC 0002 §3 range-checks a leading `-` with its literal; `T.min` accessors are **open** | RFC 0002 §3 |

---

## Round 2 Clean-Up (trivial, non-design fixes applied after `DESIGN_REVIEW_R2.md`)

Applied: corrected the false `flags & MASK == 0` claim and the `fn() -> E!T` note (RFC 0002 §4-5; superseded by D-022); half-open range semantics, `//`-in-string rule, negative-literal range check, doc-comment role, enum-switch default aborts, `[safe]` only for non-pointer scalar imports (RFC 0002/0003); division and shift rows of the UB table now cover every width, `>>` signedness, constant over-shift (RFC 0001); `unreachable()` is an abort (RFC 0003); stale text removed (RFC 0001 "4-rule", "linear slices", Pillar 3 layout; RFC 0004 coroutine heading, slice-`Send` text, bare `&`, pseudo-signature notes, prefetch-write operand; RFC 0005 zero-init text, `SysError.None`, `nocapture`, per-instantiation verifier, missing `declare`/`attributes #0`; RFC 0006 "29-keyword", `kore_version`, `ErrDeferred`, `VMError`); litmus bugs fixed (`Buf` size overflow, `close` no longer `[safe]`, `send` with `MSG_NOSIGNAL`); `LITMUS.md` and decision wording corrected; `tools/kparse.py` lexer made strict, `tools/check_keywords.py` added.

**Deliberately not touched (design decisions for the author):** the borrow-provenance, scope-death, store-through-reference and defer-in-CFG holes (R2 S-1..S-5); scoped threads and `Arc`; `Send`/`Sync`/interior-mutability declarations; `Mutex`/`atomic` being `Copy`; `unsafe` expressions, array literals, value-yielding `catch`; the `from` clause; the `Result[T, E]` spelling and the `::[T]` / `cast` spellings; ABI text rewrite (D-017).
