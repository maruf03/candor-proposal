# RFC 0003: Type System, ABI Layout, and Memory Safety

- **RFC Number:** 0003
- **Title:** Type System, ABI Layout, and Memory Safety
- **Author:** Language Design Working Group
- **Status:** Draft (v0.3: ownership model rewritten after design review; see `DECISIONS.md` D-007..D-016)
- **Type:** Standards Track (Type System & Safety)
- **Created:** 2026-10-28
- **Revised:** 2026-10-28

---

## 1. Abstract

This RFC specifies Kore's static type system, struct layout, and the ownership model that gives memory safety without a garbage collector and **without lifetime annotations**. v0.2 claimed this with four rules that the review found unsound (slices and raw pointers escaped Rule 1; exclusivity was checked only at call sites yet drove `noalias`; the spec's own `PageArena.destroy` failed the leak check; zero-init contradicted non-null pointers). v0.3 keeps the same philosophy and closes those holes with five rules (§4). Error-union ABI details (§5) are **not yet revised**; see §6.

**What "safe" means here.** Safe code (outside `unsafe`) cannot cause use-after-free, double free, leaks of `linear` values, null dereference, out-of-bounds access, or aliasing of an exclusive borrow. It *can* hold dangling raw pointers, but cannot dereference them. Data-race freedom is specified in RFC 0004 and is **not yet complete**.

---

## 2. Primitive & Compound Type Representations

### 2.1 Built-in Scalar Primitives
* **Signed Integers:** `i8`, `i16`, `i32`, `i64`, `isize`.
* **Unsigned Integers:** `u8`, `u16`, `u32`, `u64`, `usize`.
* **IEEE-754 Floating Point:** `f32`, `f64`. Default rounding; no fast-math; `==`/`!=`/`<`... follow IEEE (NaN compares unordered, `!=` is true).
* **Booleans & Unit:** `bool` (1 byte in memory, `i1` in registers), `void`.
* **Conversions** are explicit: `x as T` (RFC 0002 §5). No implicit numeric conversion. Implicit conversions that *do* exist, all lossless and type-directed: `u8[]` to `const u8[]` and `&mut T` to `&const T` (qualifier weakening), `T` or `E` to `Result[T, E]` in `return` position, and `T*` / `&T` to the nullable `?T*` / `?&T`.

### 2.2 C-Compatible Struct Alignment Algorithm
A plain `struct` follows the platform C ABI layout so it can cross into C without marshalling.

Given fields $f_0, \dots, f_{n-1}$ with size $S_i$ and alignment $A_i$ (a power of two; `[align(N)]` on a field overrides $A_i$):

1. $\text{offset} = 0$, $\text{struct\_align} = \max(A_0, \dots, A_{n-1}, \text{explicit\_align})$.
2. For each field: $\text{offset}_i = (\text{offset} + A_i - 1) \,\&\, \sim(A_i - 1)$; $\text{offset} = \text{offset}_i + S_i$.
3. $\text{total\_size} = (\text{offset} + \text{struct\_align} - 1) \,\&\, \sim(\text{struct\_align} - 1)$.

Padding bytes have unspecified contents and **safe code cannot observe them** (there is no byte-view of a struct in safe code). Empty structs have size 1 in Kore (C has none). Slices `T[]` (`{ptr, len}`), tuples, `Result[T, E]`, and any struct containing them have **Kore layout** (not C-visible); only structs of scalars, raw pointers, enums, arrays, and other C-visible structs are valid in `extern` signatures. `[packed]` and per-field `[align(N)]` are supported; unions are not (open).

---

## 3. Pointers, References, and Slices

```
┌──────────────┬──────────────┬───────────────────────────┬────────────────────────────┐
│ Type         │ Nullable?    │ Deref / arithmetic        │ Where it may live          │
├──────────────┼──────────────┼───────────────────────────┼────────────────────────────┤
│ &const T     │ no (?&const) │ safe deref                │ BORROWING: params, locals  │
│ &mut T       │ no (?&mut)   │ safe deref                │ BORROWING: params, locals  │
│ const T[]    │ n/a          │ safe, bounds-checked      │ BORROWING (shared view)    │
│ T[]          │ n/a          │ safe, bounds-checked      │ BORROWING (exclusive view) │
│ T*           │ never        │ unsafe only               │ anywhere (Copy)            │
│ ?T*          │ yes          │ unsafe, after narrowing   │ anywhere (Copy)            │
└──────────────┴──────────────┴───────────────────────────┴────────────────────────────┘
```

* **Slices are borrows.** A slice is a *view*, so it follows the same second-class rules as `&`/`&mut` (§4 Rule 1). `T[]` is an exclusive (mutable) view; `const T[]` a shared view. Owned, storable, growable memory is a `linear` library type (`mem.Buf[T]`), never a slice.
* **Raw pointers are inert in safe code.** Safe code may create (`slice.ptr`, `r as (T*)` from a reference), copy, compare, store, and pass `T*`/`?T*`, but **cannot dereference them, do arithmetic on them, or cast between pointer types**. Those require `unsafe`, as does creating a `T*` from an integer (`n as (T*)`; use `?T*` if the integer may be 0). A dangling raw pointer is therefore harmless until an `unsafe` block dereferences it, and the obligation to prove validity sits with that block.
* **Calls to non-`[safe]` `extern` functions require `unsafe`.** `[safe]` is the *author's* assertion that the C function is memory-safe for all argument values. It is legal only on imports whose parameters are all non-pointer scalars (a raw pointer may dangle, so no pointer-taking import can be safe), and it asserts *memory* safety only: a `[safe] close(fd)` could still close a descriptor owned by a linear `Fd`, which is why `close` is not `[safe]` in `litmus/04_echo_server.kr`.
* **`unsafe` contract.** Code in `unsafe` must uphold Rules 1-3 manually (no aliasing an exclusive borrow, no outliving a borrowed source, no consuming a `linear` twice). Violating them is undefined behavior; this is the only place where Kore has UB (RFC 0001).

### Flow-Typed Null Narrowing
`?T*` (and `?&const T`, `?&mut T`, `?const T*`) has the same width as `T*`, with address 0 as `null`. It cannot be dereferenced, and it cannot be used where `T*` is expected, until narrowed:

* Narrowing applies to a **local variable or parameter** `p` tested by `p != null` (inside the `if`), `p == null` with a diverging branch (after it), or `&&` chains of such tests.
* It is **killed** by assignment to `p`, by taking `&mut p`, and at loop headers if `p` is assigned in the loop. It does **not** apply to fields, dereferences, or indexed places (`s.next != null` does not narrow `s.next`): copy into a local first.
* Passing a narrowed value converts it to `T*`.

---

## 4. The Ownership Model: Five Rules, Zero Lifetime Annotations

Two kinds of values need tracking: **borrows** (views of someone else's memory) and **linear values** (things that must be released exactly once). Everything else (scalars, raw pointers, plain structs of those) is `Copy` and unrestricted. All analysis is intra-procedural plus the function signature; there are no lifetime parameters.

### Rule 1: Borrowing Types Are Second-Class

A type is **borrowing** if it is `&const T`, `&mut T`, `const T[]`, `T[]`, their nullable forms (`?&const T`, `?&mut T`), or a struct, tuple, enum, array or error union that has a borrowing component. (Borrowing-ness is inferred.) A function-pointer *type* is not borrowing merely because its parameters are borrows (parameters are not stored); a function-pointer type with a borrowing *return type* is subject to the same single-borrowing-parameter rule as a declaration.

A borrowing type **may** appear as: a function parameter, a local variable, a function return type (subject to elision below), a field of another borrowing struct.

A borrowing type **must not** appear as: a field of a non-borrowing struct (inference would make that struct borrowing), a `const` or global, behind a raw pointer, **any generic argument** (`Vec[&T]` and `Pair[&T, u8]` are rejected, so a generic function can never smuggle a borrow past the elision rule), or a value sent to another thread.

**Returning borrows by elision.** A function may return a borrowing type only if it has **exactly one borrowing parameter** (counting `self`). The result is then borrowed from that parameter's argument for as long as the result is live. If the function has zero or several borrowing parameters, returning a borrow is a compile error, which forces such APIs to take indices or copy values. There is no syntax to name or relate lifetimes.

```rust
pub fn get(self: &const Map[K, V], key: K) -> ?&const V;   // ok: one borrowing param (self)
pub fn text(src: const u8[], t: Token) -> const u8[];     // ok: Token is Copy, not borrowing
pub fn pick(a: &const T, b: &const T) -> &const T;        // ERROR: two borrowing params
```

*Why this is sound without lifetimes:* a borrow can only exist as a local or parameter, so it always lives in a stack frame *below* (callee side) or *equal to* the frame that owns the borrowed place; elision ties a returned borrow to its single source, and Rule 2 keeps that source frozen while the result is live. Interior memory of heap owners (`Buf`) is reachable only through borrows of the owner.

*Cost, stated honestly:* long-lived views cannot be stored in structs (see `LITMUS.md`, findings L2-1, L5-1). A tokenizer keeps `pos` and receives the source per call, or bundles both into a borrowing struct that itself stays on the stack. Graphs, ASTs, and caches use typed indices into owned arenas (RFC 0001 §5).

### Rule 2: Exclusivity and Freezing, Checked by Liveness

A **borrow** is created by `&const place`, `&mut place`, slicing (`a[i..j]`, `a[..]`), or an elided call result. It is **live** from creation until the last use of the borrow *or of any value derived from it* (a reborrow, an elided result, a borrowing struct containing it). Liveness is computed per function over the CFG (non-lexical).

A **place** is a local, parameter, field path (`x.a.b`), or element path. Element paths collapse: `a[i]` and `a[j]` are both "the elements of `a`" and are treated as **one place**. Two places **overlap** if one is a prefix of the other.

While a borrow of place `P` is live:

* an **exclusive** borrow (`&mut`, mutable slice) forbids *any* other access to an overlapping place (read, write, borrow, move), except through that borrow;
* a **shared** borrow (`&const`, `const` slice) **freezes** `P`: no write, `&mut` borrow, move, consume, or assignment to an overlapping place. Reads and other shared borrows are fine.

Consequences: `f(p, p)` with `p: &mut T` is an error (two exclusive uses); `swap(&mut a[i], &mut a[j])` is an error (use `std.swap` or `split_at_mut`, whose `unsafe` bodies uphold the contract); `let r = &const v.items[0]; v.push(x); use(r)` is an error (the shared borrow froze `v`). Passing an existing reference parameter on to a callee is a **reborrow** and counts as a use of the original.

**Two-phase receivers.** For a method call with an implicit `&mut` receiver, the receiver borrow is *reserved* first and *activated* at the call, so reads of the same place in the arguments are allowed: `v.push(v.len())`.

**Implicit autoref and deref (documented magic).** `x.m(...)` borrows `x` according to the declared `self` type (`self: &mut T` takes `&mut x`). Field access and method calls through a reference auto-dereference; use `*r` to name the whole referent.

**`noalias`.** The compiler emits LLVM `noalias` on `&mut T` and mutable-slice parameters, and `readonly` + `noalias` on `&const T` / `const T[]` parameters whose element type is not interior-mutable (`atomic[T]`, `Mutex[T]` are not). Because Rule 2 is liveness-based and covers reborrows and slices, these attributes are emitted only for properties that were checked. A bug in the checker is therefore a miscompile; the checker must be treated as part of the trusted base and fuzzed accordingly.

### Rule 3: Linear Values

A type is **linear** if it is declared `linear struct`, **or** contains a linear component (struct field, tuple element, array element, enum payload, error-union payload). Linearity is inferred upward; it cannot be lost by wrapping. An unbounded generic parameter `T` is treated as possibly linear inside the generic body, so values of type `T` can only be moved (each exactly once), never copied or dropped, unless `T: Copy` is declared.

`Copy` is auto-derived for all non-linear, non-exclusive types. `Zero` (§4 Rule 5) is auto-derived. Neither can be implemented by hand.

For every **local variable and by-value parameter** `v` of linear type, the verifier tracks a state over the CFG:

$$\text{State}(v) \in \{\text{Unconsumed}, \text{Consumed}, \text{Deferred}, \text{ErrDeferred}\}$$

| Operation on `v` | Allowed in | Effect |
| :--- | :--- | :--- |
| initialization (`let v = ...`, by-value param) | n/a | `Unconsumed` |
| borrow (`&const v`, `&mut v`, method with borrowing `self`), read of a `Copy` field | Unconsumed, Deferred, ErrDeferred | none |
| **move** (pass by value, `return v`, store into a field/literal) | Unconsumed, ErrDeferred | to `Consumed` |
| destructure (`let T{ a, b, .. } = v;`) | Unconsumed | to `Consumed`; `a`, `b` are new variables, `Unconsumed` if linear |
| assignment `v = e` | Consumed (re-initialization) | to `Unconsumed` |
| any use, borrow or move | Consumed | **error**: `use of consumed linear value 'v'` |
| assignment to an `Unconsumed` linear place | none | **error**: would leak the old value |
| partial move (`consume(v.field)`) | none | **error** (use destructuring) |

**The base case: destructuring.** Within the module that defines `T`, `let T{ f1, f2, .. } = v;` consumes `v` and binds its fields. Every non-`Copy` field must be bound (and so become a variable to consume in turn); `..` may skip only `Copy` fields. Outside the defining module, private fields are invisible, so external code can only consume `T` by calling a function that takes it by value. This is how `destroy(self: PageArena)` bottoms out: it destructures `self` into plain `Copy` fields and calls `munmap`. (There is no `forget` and no implicit drop.)

**Joins and loops.**
* At a CFG join from non-diverging paths, `State(v)` must be identical on all of them, otherwise `linear value 'v' conditionally consumed`. Paths that end in `return`, `break`, `continue`, `unreachable()`, `trap()` or a diverging call are checked at their own exits instead and do not participate in the join.
* A linear variable declared **outside** a loop must have the same state at the back-edge as at loop entry (so it can be consumed in the loop only if the loop then exits). A variable declared **inside** the loop body is checked per iteration.
* Shadowing creates a new variable; state is per binding, not per name.

**Exits.** At every function exit and at every scope exit for variables declared in that scope, each linear variable must be `Consumed` or `Deferred`; or `ErrDeferred` on an *error exit* (Rule 4). Otherwise: `resource leak: linear value 'v' exits scope unconsumed`.

**Traps do not run `defer`.** `trap()`, bounds failures, and division traps abort the process; leak diagnostics do not apply to paths that end in a trap. `unreachable()` is a trap with a different message, never an optimizer hint: it lowers to an abort, and LLVM's `unreachable` instruction is emitted only by the compiler for paths it has proven dead.

### Rule 4: `defer` and `errdefer`

`defer S` registers `S` to run when control leaves the enclosing block by any path (fall-through, `return`, `break`, `continue`, `try`), in last-in-first-out order.

* **Evaluated at exit.** Names in `S` refer to the *variable*, not a snapshot taken at registration, so `defer arena.destroy();` followed by `arena.capacity` reads is fine.
* **Registering a defer that consumes a linear variable `v` moves `v` into `Deferred`.** In `Deferred`, `v` may be borrowed and its `Copy` fields read, but not moved, consumed, or reassigned (`defer buf.release(); consume(buf);` and `defer buf.release(); return buf;` are errors). At every scope exit the deferred statement consumes `v`.
* `S` may not contain `return`, `break`, `continue`, or `try` (a cleanup cannot change control flow). `S` runs *after* the return operand has been evaluated, so `return *r;` reads through a borrow before the deferred `m.destroy()` runs.
* A `defer` inside a loop body runs at the end of each iteration and on `continue`/`break`.

`errdefer S` is `defer` that runs **only on error exits**: a `try` that propagates, or `return e` where `e` has the error-enum type `E`. A `return v` with a value of type `T` is a *success exit*; a `return x` where `x` has type `Result[T, E]` (already a union) is treated as **both**. `errdefer` is how multi-step initialization is written:

```rust
let keys = try mem.Buf[K].init_zeroed(a, cap);
errdefer keys.destroy();                    // keys: ErrDeferred
let vals = try mem.Buf[V].init_zeroed(a, cap);   // if this fails, keys.destroy() runs
errdefer vals.destroy();
return Map[K, V]{ keys: keys, vals: vals, ... };  // success exit: moves keys and vals
```

State rules: `ErrDeferred` permits borrowing and **moving**. On an **error exit**, the errdefer statement runs iff `v` is not `Consumed` on that path (decided statically, since state is path-exact). On a **success exit** an `ErrDeferred` variable must have been `Consumed` by some other move (as `keys`/`vals` are above), otherwise it is a leak. An `errdefer` whose body does not consume a linear variable (plain cleanup) runs on every error exit.

### Rule 5: Definite Initialization (replaces blanket zero-fill)

* Every `let`/`mut` binding must be initialized in its declaration (`= expr`).
* A struct literal must name **every** field.
* There is no implicit zero-initialization. Zero-filled storage is requested explicitly with `zeroed(T)`, legal only when `T` is **`Zero`**. `Zero` is auto-derived for: integers, floats, `bool`, nullable pointers/references, enums that have a variant equal to 0, `distinct` types over `Zero` types, and arrays/structs/tuples whose components are all `Zero`. It is **not** derived for `&T`, `T*`, slices, `linear` types, or `Result[T, E]`. This is what keeps "non-null `T*`" and "fabricated `linear` handle" from being constructible by zeroing.
* The optimizer sees ordinary initialization, so there is no hidden `memset` cost.

---

## 5. Error Unions (`Result[T, E]`) and Multi-Returns

> **Status: not yet revised.** The register-pair lowering below is the original proposal. The review found it is not the C ABI in general (mixed int/float payloads, Windows x64, sret register), and `Result[T, E]` and tuples have no C representation. The direction decided in `DECISIONS.md` (D-017) is a **Kore-internal calling convention** (free to use LLVM first-class aggregates and `fastcc`-style registers), with the platform C ABI applied only to `extern "C"` declarations and exports, where `Result[T, E]`, tuples, and slices are rejected. Until the RFC is rewritten, treat the register assignments below as illustrative, not normative.

### 5.1 Multi-Return Tuple Lowering
Functions returning `(T1, T2)` where the laid-out size is at most 16 bytes are returned as an LLVM two-element struct `{ T1, T2 }` in two registers under the Kore convention; larger results use a caller-allocated `sret` slot.

### 5.2 Error Unions
An error union `Result[T, E]` is `{ Payload, i32 tag }` under the Kore convention. **Tag 0 means success**, so error enums used in `Result[T, E]` must not define a variant equal to 0 (`enum NetError : i32 { Socket = 1, ... }`); the compiler rejects a 0-valued variant. `E` is always a fieldless enum (no payload-carrying errors in v0.3). `Result[void, E]` is valid; `return;` (or falling off the end) is success. At a call site, `try` / `catch` compiles to a test of the tag and a branch.

---

## 6. Known Open Issues in This RFC

1. §5 ABI text (D-017) needs rewriting against the Kore-internal vs C-ABI split.
2. `Send`/`Sync` interaction with Rule 1 (`Mutex[T]*`, thread lifetimes) is in RFC 0004 and unresolved.
3. Containers of `linear` elements (`Vec[LinearT]`) need `destroy_with(fn(T))` or an explicit drain protocol; v0.3 std containers are `Copy + Zero` only (`LITMUS.md` L1-1).
4. Stateful allocators cannot be exposed safely through pointer-holding `Buf` (`LITMUS.md` L5-1).
5. No array literal, no `static`/global variables, no unions.
