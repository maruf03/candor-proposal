> **DEFERRED, NOT PART OF CANDOR.** Candor does not track borrows at all (`spec/03-memory.md` §1, `deferred/ownership-checking.md`). This note preserves a borrow design that was studied and rejected for size, in case an optional checker is ever built.

# Returned and Stored Borrows

## The design that was tried

- **Second-class borrows.** References and slices live only in parameters and locals; they cannot be fields of non-borrowing structs, globals, or generic arguments. A struct with a borrowed field is itself "borrowing" (inferred) and obeys the same rules.
- **Returning by elision.** A function may return a borrow only if it has exactly one borrowing parameter (counting `self`); the result is borrowed from that argument for as long as it is live. No lifetime syntax.
- **Liveness-based exclusivity.** A borrow is live from creation until the last use of it or of anything derived from it (reborrows, elided results, borrowing structs). While an exclusive borrow of place `P` is live, nothing else touches an overlapping place; while a shared borrow is live, `P` is frozen. Two-phase receivers allow `v.push(v.len())`.
- **A `from` clause** (considered): `fn text(self: &const Token, src: const u8[]) -> const u8[] from src;` names which parameters a returned borrow depends on, relating several borrowing parameters without lifetime variables.

## Why it was deferred

It needed five rounds of review to approach soundness and felt like Rust. The holes found in the final round, all of which must be closed by any revival:

1. **Provenance in the callee body.** The elision rule is a call-site rule; `fn bad(a: &const u32) -> &const u32 { let x = 5; return &const x; }` has one borrowing parameter and passes. A returned borrow must be proven to derive from the sole borrowing parameter's referent (or be static).
2. **Scope death.** A borrow of a local stored in a longer-lived variable dangles when the local's scope ends (including loop-carried forms). Borrows of local `X` may be stored only in locals declared after `X`.
3. **Stores through references.** `fn link(dst: &mut Holder, src: &const u32) { dst.r = src; }` writes a callee borrow into caller-owned memory. Assigning a borrow into a place reached through a reference must be forbidden (or tracked with dependency summaries).
4. **`defer` in the liveness CFG.** Deferred statements must be lowered into the CFG at every exit edge, LIFO, before liveness and freeze are computed (`defer g.unlock(); defer m.destroy();` otherwise leaves the guard borrowing a destroyed mutex).
5. **A `defer` in an inner block consuming an outer variable** must be rejected or the variable moved to Consumed at block exit.
6. **Interior mutability** (`atomic`, `Mutex`) breaks the `readonly noalias` assumption on shared borrows and must be an inferred, user-extensible property.

## Evidence that v1 does not need it

In the five litmus programs returned borrows were used in 5 places (`node`, `text`, `Map.get`, `Buf.get`, `Buf.get_mut`); four returned elements of `Copy` containers (a copy or an index suffices) and `text` returns a slice that callers can take at the use site. One struct (`Cursor`) and one local held a borrow.

## Re-entry criteria

Bring it back only if a program needs one of: a zero-copy view of a large record or buffer returned across a function boundary; a parser or iterator that must hold its input; a guard type for concurrency. Then prefer the `from` clause plus holes 1-5 above over reintroducing implicit elision.
