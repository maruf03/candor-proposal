> **DEFERRED, NOT PART OF KORE.** Kore is a C-like language: it does not check ownership or aliasing (`docs/decisions.md`, D-01). This note records what was designed and removed, so it can come back as an optional tool if wanted. The full text is in commit `3c61f4f` (`spec/03-memory.md`, `spec/02-types.md`, `docs/decisions.md` D-01 to D-18).

# Ownership Checking (removed)

The first specification (v1, committed as `3c61f4f`) was memory safe without a GC. It reached that with:

- **Call-scoped borrows.** `&const T`, `&mut T` and slices could appear only as parameters and call arguments; they could not be returned, stored or bound. Within one call, overlapping borrows had to all be shared. Arguments were evaluated first, then borrows were materialized (an independent review found that evaluating a slice argument before a later argument could free it; borrows must activate after value arguments).
- **`linear struct`.** Values consumed exactly once on every path: states Unconsumed/Consumed/Deferred/ErrDeferred, destructuring `let T{ a, .. } = v;` as the base operation, no partial moves, a `swap` intrinsic for replacing linear places.
- **`errdefer`, `Result[T, E]`, `try`, `catch`.** Path-exact cleanup and an error type with a restriction that `T != E`.
- **`unsafe(expr)`** around every raw-pointer operation and C call; raw pointers were inert elsewhere.
- **A built-in `Buf[T: Copy]`**, because borrows could not be returned and a library type therefore could not expose its storage.

## Why it was removed

The author wanted a small language closer to C than to Rust: no borrow checker, no hidden machinery, primitives that let a programmer build whatever memory management they need. Call-scoped borrows were a smaller borrow checker but still one, and they forced a compiler-known container (`Buf`) and a `Copy` marker, which pushed the language toward Rust.

## Re-entry criteria

Bring a checker back only as an **optional, separate analysis** (a lint or a `kore check --strict` pass) over the same language, never as something the syntax must express. Design notes that carry over: borrows must activate after value arguments; a linear checker must lower `defer` into the CFG before checking; returned-borrow designs are in `returned-borrows.md`.
