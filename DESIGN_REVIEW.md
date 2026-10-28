# Kore Design Review: Final Judged Report

> **Historical document.** This reviews the **v0.2** specification. Resolutions are tracked in `DECISIONS.md` (see its status table); quotes and line references below refer to v0.2 text that has since changed.

Five reviewers read all 7 spec files (grammar, soundness, semantics/ABI, concurrency/FFI, feasibility). Spec-text claims below were checked against the files. LLVM and psABI points come from reviewer and author knowledge and were not compiled or run. No spec files were modified.

## Verdict

The design is ambitious and the surface syntax is tidy. The headline promises don't hold as written:

- "Memory safe with 4 rules, no lifetimes" has holes.
- "Zero UB in safe code" has holes.
- "Strict LL(1), no symbol table" is false.
- "Zero-overhead C ABI for error unions" is incoherent.

Every RFC is marked "Accepted" with no implementation behind it, and the docs contradict each other. Most fixes are cheap now and expensive after code exists.

## A. Blockers: claims the spec's own text breaks

| # | Problem | Evidence | Fix |
|---|---|---|---|
| A1 | **Rule 1 contradicts `Mutex.lock()`.** Rule 1 says references can't be returned. RFC 0004 `lock()` returns `&mut T`, and the "escape safety" claim depends on it. | RFC 0003 Rule 1 vs RFC 0004 §4.1 | Use Hylo-style subscripts/projections, a callback `with_lock(fn(&mut T))`, or define `with` as a guard protocol with an explicit exception to Rule 1. |
| A2 | **Slices bypass Rule 1.** Rule 1 only restricts `&const T` and `&mut T`. `T[]` can be returned or stored and can dangle. So "mathematically guaranteed" is false. | RFC 0003 Rule 1; `poll_socket` stores `u8[]` in a Task frame | Make slices second-class too, or give them regions (Austral/Cyclone). |
| A3 | **Raw `T*` has no validity story.** Nothing says whether safe code can dereference it. If it can, use-after-free follows once the linear owner is consumed. If it can't, `lock_ptr.lock()` is ill-typed. | RFC 0003 §3 table; RFC 0004 example | Make `T*` deref/creation `unsafe`-only and wrap it in linear owners. |
| A4 | **The spec's own `PageArena.destroy(self)` fails Rule 3.** It never consumes `self`, so it errors as "leak". There is no consume or destructure primitive. | RFC 0006 §2.2 vs RFC 0003 Rule 3 | Add a destructuring `let PageArena{..} = self;` (Austral) or a `deinit` rule. |
| A5 | **Zero-init contradicts non-null `T*`.** `StructInit` can omit fields. Zeroing then makes a "non-null" pointer null. It also fabricates linear handles (fd 0 is stdin). | RFC 0001 rows 1 and 5 | Use definite-initialization analysis. Allow zero-init only for types whose zero value is valid. |
| A6 | **`noalias` is emitted on an under-checked property.** Rule 2 checks only arguments at one call site. A reborrow passed twice (`f(p,p)`), `swap(&mut a[i], &mut a[j])`, slices and `T*` aliases escape it. Wrong `noalias` is LLVM UB, so "zero UB" fails. RFC 0005 also puts `noalias` on a plain slice param. | RFC 0003 Rule 2; RFC 0005 §5.1 | Emit `noalias` only where the checker proves it. Make the check flow- and liveness-based. |
| A7 | **A live `&const` doesn't freeze its referent.** `let r = &const v.data[0]; v.push(..); use(r)` is the iterator-invalidation bug. | Rule 2 bullet 2 covers only `&mut` | Make shared borrows freeze their root. |
| A8 | **Error-union ABI claims are wrong or unmotivated.** LLVM `{double,i32}` and C's `{double,int}` use different registers. The spec says "element 1 in RDX (XMM1 for floats)". SysV returns the sret pointer in RAX, not RDI/EAX. Win64 returns at most 8 bytes in RAX. C has no `E!T`, yet the README claims direct C interop for it. | RFC 0003 §5, README | Define a Kore-internal ABI. Use the C ABI only at `extern` boundaries and ban `E!T`/tuples there. |
| A9 | **The `api.kr.d` opaque-byte stub breaks by-value ABI.** SysV classifies each eightbyte by field type. A private `f64` hidden in `u8[N]` is passed in the wrong register class. It also hides `Send`/`Sync` inputs, so a type holding a raw pointer becomes `Send`. | RFC 0006 §4.3 | Drop precompiled packages for v1, or add explicit ABI-class and `Send` annotations in the stub. |
| A10 | **The grammar is not LL(1).** `items[i]` parses as generic `items[T]` or as indexing. `(Type) expr`, `(Expr)` and `TupleLit` share a prefix, so `(a * b)` looks like a cast to `a*`. `&const` is ambiguous between `&`'s own `const` and the inner type's `const`. | RFC 0002 lines 123–136, 201–215 | Add `as` for casts. Parse `[...]` uniformly as expression-or-type (Go). Run a mechanical FIRST/FOLLOW check. |

## B. Major gaps

### Linear types
- Linearity isn't infectious. A plain `struct W{h: Handle}` is copyable, so two copies close the same fd.
- Undefined: tuples, `E!T`, arrays, `Vec[T]` with linear `T`, partial moves, reassignment, and shadowing.
- `defer buf.release(); consume(buf);` is a double free. Deferred→Consumed is undefined.
- Whether `defer` arguments bind at registration or at exit is undefined. The README example reads `arena.capacity` after `defer arena.destroy()`.
- There is no `errdefer`, so the common "free A only if B fails" pattern can't be written.
- The `≡` join in the CFG formula is undefined, and loops aren't covered.

### Concurrency
- `Mutex[T]*` is `Send` but raw pointers aren't. The two lines contradict each other.
- A pointer to a stack mutex can outlive its frame. `Thread` isn't linear and has no `join`.
- The `linear`-wrapper loophole lets safe code build two aliasing wrappers.
- `Sync` is defined but never used. There's no "`&T` is Send iff `T: Sync`" rule, so read-only sharing is inexpressible.
- `Task[T]` has no executor, `await` or result access.
  - `poll_socket` is a busy-poll loop, not async I/O.
  - A dropped Task leaks its linear locals.
  - Its frame size is unknown at Pass 2a.
- The atomics API is incomplete.
  - CAS has no failure ordering and returns only `bool`.
  - There's no `load`/`store`, and `mut s: atomic[u64] = 0` itself contradicts "no direct assignment".
- A bare `&atomic[u32]` is an undefined third reference kind.
- There's no memory model, so data races are UB in LLVM. "Zero UB" is false.
- `VM`, `Futex`, `CPU` and `Thread` are undeclared magic namespaces, and the RFC says "three" but lists four.
- `VMAdvise.Sequential = 1` is `MADV_RANDOM` on Linux. `HugePage2MB = 64` is `MAP_32BIT`. The `PageArena` call omits `MAP_PRIVATE`, so Linux `mmap` returns EINVAL. Enums can't be OR-ed.

### Missing basics
- No globals or statics, so there are no allocators or singletons. Only `VM.map` exists, so `Vec`, `Box` and strings can't be built.
- No sum types or tagged unions, so ASTs, `Option` and `Result` are impossible.
- No bounds on generics, so `T: Send` is prose only. Bodies are checked at instantiation, as in C++ templates.
- No closures, string or char types, `default` in `switch`, error propagation (`try`/`?`) or panic/assert.
- `catch` works only inside `let`, so `close(fd) catch (e){};` doesn't parse.
- Locals must be initialized (`VarStmt` requires `=`), yet RFC 0001 describes zero-initializing "uninitialized" locals. No syntax exists for an uninitialized array.
- The lexical spec is missing: literals, comments, escapes, identifiers, number forms.
- `sizeof` and `i64.min` have no grammar.
- `case .Idle:` doesn't parse.
- `fn Thread.spawn[T]` and `fn VM.map` aren't valid `FnDecl`s.

### UB table details
- A shift amount ≥ the bit width is LLVM poison. The compiler must emit an explicit `and`. It folds away for i32/i64 but is a real instruction for i8/i16, so "zero penalty" is false.
- Division is described only for `i64.min / -1`. It must cover every width and `%`. On AArch64 `sdiv` doesn't trap, so a compare is needed.
- Float-to-int casts are poison out of range.
- Evaluation order, NaN compares, int promotion, enum casts, stack probes and padding bytes are all unspecified. `encode_struct` reads uninitialized padding from a safe-looking API.
- `llvm.trap` is SIGILL, not a defined failure mode.

### Layout
- The algorithm has no `packed`, unions, per-field `[align]`, empty structs or enum size.
- Structs containing slices have no C equivalent.
- A C layout everywhere forgoes field reordering. Split `extern struct` from plain `struct`, as Rust and Zig do.

## C. Documentation and process problems

- **Keyword count:** the keyword box contains 31 words. RFC 0001 says 27. RFC 0002, RFC 0006 and the README say 29. The box headers say 9 for Control Flow (it has 10 words) and 5 for Bindings (6 words). `self`, `sizeof` and the magic namespaces are unlisted.
- **README links:** all six point to `rfcs/000N-…md`. The real files are `rfc_000N_…md` in the repo root, and the titles differ.
- **README promises** a quickstart, a code tour and a "course roadmap" that don't exist.
- **Status:** every RFC is "Accepted" with the same creation date, and no implementation exists.
- **Compiler language:** RFC 0005 uses Go, but LLVM's DIBuilder is C++. That means cgo or textual IR, which conflicts with the "no cgo tax" theme.
- **`.kpkg` bitcode:** LLVM bitcode isn't stable across LLVM versions. `llvm-dis` exposes everything, so the "bodies stripped" IP claim is false for `.bc`.
- **Platforms:** the README names SysV and AAPCS64 only, but RFCs 0004 and 0006 promise macOS and Windows.
- **Observability:**
  - `push rbp; mov rbp,rsp` is 4 bytes, not 3.
  - `perf script | pprof` doesn't work without a converter.
  - "100% compatible" ignores C frames built without frame pointers.
  - The "`.eh_frame` eliminated" claim is overstated (reviewer claim, not verified).
- **Unmeasured claims:**
  - LSP under 5 ms.
  - A parser under 2,000 lines.
  - The Go `cgo` cost of "50–150 ns".

## D. Findings downgraded or left unproven

- **Zig/Rust/Go strawmen** (RFC 0001): arguable and low priority. Zig's `comptime` can hide types behind `anytype`. The Go cgo figure is probably high. Neither affects correctness.
- **PGO and legacy pass manager:** the semantics reviewer retracted this point itself, so it is dropped.
- **LLVM and psABI details:** these come from memory and weren't tested. Confirm with `clang -S -emit-llvm` on small C examples before relying on them.
- **Effort estimates** (2–3 person-years) are the feasibility reviewer's rough guess.

## E. Alternatives you may have overlooked

- **Return-by-reference without lifetimes.** Allow a returned reference only when derived from a single reference parameter or `self` (elision-style). Or use Hylo projections or Austral-style regions. Rule 1 as written makes `get()`, `first()`, iterators and tokenizers unwritable.
- **Austral** is the closest design for linear types and capabilities. **Hylo/Val** is the closest to second-class references.
- **Scoped threads** (Rust `thread::scope` or an equivalent). Downward-only references make them natural, and they fix several concurrency problems at once.
- **Drop language-level coroutines for v1.** Ship an event-loop library with owned buffers passed by value and returned, as Monoio/Glommio do.
- **Stdlib instead of compiler magic.** `VM` and `Futex` should be `extern "C"` wrappers in `std/sys`. Keep only `atomic` and prefetch as real intrinsics.
- **Backend:** emit C first, or use QBE/Cranelift, before LLVM. That gives ABI, debug info and cross-compilation nearly free.
- **Syntax:** `as` for casts, a postfix `try`/`?` for errors, and `T[N]{}` or `= undefined` for uninitialized storage. `E!T` follows Zig. `T!E` may read better.

## F. What is solid

- Square-bracket generics, mandatory braces and the "keyword-first declarations" idea.
- Wrapping arithmetic without `nsw`/`nuw`, and the `?T*` null niche with flow-typed narrowing for immutable locals.
- `icmp ult` bounds checks with a cold trap, and eager LIFO `defer` expansion with no unwinding.
- `pub` not affecting layout, and the private-field literal ban that protects linear invariants at module boundaries.
- Tag-only error values in registers (Zig-like), and 1:1 threads for cheap C calls.
- Data-bound `Mutex[T]`, and second-class references as a design direction.

## G. Suggested order of work

1. Mark all RFCs Draft, fix the keyword count and README links, and add a decision log.
2. Run the grammar through a mechanical LL(1) checker and fix casts, `[`, `&const` and `catch`.
3. Write 5 litmus programs: hash map, tokenizer, arena-index graph, TCP echo server, allocator. Test Rule 1 against them.
4. Decide the reference story (A1–A3, A6, A7), the linear consume/defer semantics (A4) and initialization (A5). Retract "mathematically guaranteed" and "zero UB" until they hold.
5. Specify a Kore-internal ABI separate from the C ABI (A8).
6. Cut `.kpkg`, the LSP latency claim, Windows/macOS and coroutines from v1.
7. Pick an implementation language and a C-emitting backend, then build the lexer, parser and golden tests first.
