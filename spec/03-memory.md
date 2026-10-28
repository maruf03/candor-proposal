# Kore 3: Memory Safety

How Kore prevents use-after-free, double free, leaks of resources, null dereference, out-of-bounds access, and aliasing of mutable data, **without a garbage collector and without lifetime annotations**.

The design has one idea and two supporting ones:

1. **Borrows exist only for the duration of a call** (§2). They cannot be returned, stored, or named, so they cannot dangle.
2. **Resources are linear** (§3): they must be consumed exactly once.
3. **Cleanup is explicit and path-complete** (§4): `defer` and `errdefer`.

---

## 1. What Is Guaranteed

Outside `unsafe(...)`, a Kore program cannot:

| Hazard | Prevented by |
| :--- | :--- |
| use after free, dangling reference | borrows are call-scoped (§2); freeing consumes a linear owner (§3) |
| double free, double close | linear values are consumed exactly once (§3) |
| leaked resource | a linear value must be consumed before scope exit (§3) |
| aliased mutation | exclusive borrows may not overlap any other borrow in a call (§2) |
| null dereference | `T*` and borrows are non-null; `?T*` cannot be dereferenced (§6) |
| out-of-bounds access | array, slice and `Buf` accesses abort when out of range (`spec/02-types.md` §4) |
| uninitialized read | definite initialization (§5) |
| arithmetic corruption | overflow, bad division, bad shifts all abort or are defined (`spec/02-types.md` §4) |

**What is not guaranteed**, stated plainly:

- `unsafe(...)` expressions and calls into C are trusted; undefined behavior can occur there and **only** there.
- Linear values can be *forged* by code in the same directory module as the type (`Fd{ raw: 0 }`), because struct literals and destructuring are allowed there (`spec/05-modules.md` §3). The guarantee holds modulo the authors of that module.
- Aborts (`trap()`, bounds, overflow) skip `defer`: a program that aborts may leave external resources (files, locks) unreleased. The process still terminates immediately.
- Kore v1 is single-threaded; data races are out of scope until concurrency is specified.
- Logic errors, resource exhaustion, and deadlock are not prevented.

---

## 2. Borrows

### 2.1 Borrow types and where they may appear

The **borrow types** are `&const T` (shared), `&mut T` (exclusive), `const T[]` (shared slice) and `T[]` (exclusive slice).

A borrow type or expression may appear **only**:

1. as the type of a **function parameter** (including parameters of function-pointer types);
2. as an **argument expression** at a call: `&const place`, `&mut place`, a slicing expression `place[lo..hi]` / `place[..]`, a string literal, or a borrow parameter passed on;
3. as the type of a **`const` item** initialized from a string literal (static data), which may be passed as a `const u8[]` argument.

A borrow type or expression may **not** appear as a return type, a struct or enum field, an array element, a `Result` payload, a generic argument (`Buf[&const u8]`), the type or initializer of a `let`/`mut` binding, a `for` variable, or behind a raw pointer. `for (x in s)` binds `x` **by value** (`Copy` elements only).

Consequences, stated up front: a function cannot hand out a reference into its argument. Getters return **copies** or **indices**; mutation goes through `set`-style functions or `&mut` parameters; long-lived views are replaced by indices (`litmus/02_tokenizer.kr`, `litmus/03_arena_graph.kr`).

### 2.2 The call rule

At a call `f(a1, ..., an)`, including the receiver of a method call, **all arguments are evaluated first** (left to right, nested calls complete), then **the borrows among them activate together** and stay active until `f` returns.

A **place** is a variable, a field path (`x.a.b`), the contents of a borrow parameter (`*p`, `p.f`), or an element place. **All elements of one array, slice or `Buf` are one place** (`a[i]` and `a[j]` overlap). Two places **overlap** if one is a prefix of the other; distinct fields of one struct do not overlap.

> **Rule.** In one call, any two borrows of overlapping places must both be shared. A pair that includes an exclusive borrow of overlapping places is a compile error.

```
f(&mut x, &mut x)          // error: two exclusive borrows
f(&mut x, &const x)        // error: exclusive + shared
f(&mut s.a, &const s.b)    // ok: disjoint fields
f(&const x, &const x)      // ok: both shared
v.push(v.len())            // ok: v.len() finishes before push's &mut v activates
f(&mut a[0], &mut a[1])    // error: elements are one place (use a helper that takes two indices)
```

An exclusive borrow of `x` also conflicts with a by-value *move* of the same `x` in that call (§3), and any borrow of a consumed value is an error.

### 2.3 Inside the callee

A borrow parameter lives exactly as long as the call. In the body:

| You may | You may not |
| :--- | :--- |
| read through it (`*p`, `p.f`, `p[i]`) | return it, store it, bind it to a `let`/`mut`, or copy it into a struct |
| through `&mut` and exclusive slices: assign (`*p = v`, `p.f = v`, `p[i] = v`) | assign through `&const` or a `const` slice |
| pass it on to another call as a borrow argument (**reborrow**: counts as one borrow of `*p`; `g(p, p)` conflicts per §2.2) | move a non-`Copy` value out of it (`return p.fd;` where `fd` is linear) |
| take sub-borrows: `&mut p.f`, `p.items[a..b]` | |
| weaken: pass `&mut T` where `&const T` is expected | |

`x.method(args)` borrows `x` according to the method's `self` parameter (`self: &mut T` takes `&mut x`, `self: &const T` takes `&const x`; `self: T` copies or moves). Field access and method calls through a borrow parameter dereference it automatically. These two implicit steps are the only "magic" in the memory model.

### 2.4 Why this is sound

1. Because borrows cannot be returned, stored, or bound, a borrow cannot outlive the call it was created for. It therefore **cannot dangle**.
2. While a call runs, the caller is suspended. The borrowed places can change only through the borrows, because there are no globals or statics, no threads, and raw pointers cannot be dereferenced in safe code (§6). By the call rule no two borrows alias unless both are shared. Therefore **exclusive borrows are exclusive**.
3. Neither argument needs a lifetime annotation, region, or flow analysis: the borrow's lifetime is the call.

This is why the language has no lifetime syntax and no returned-reference machinery. The cost is real and accepted (see `docs/decisions.md`, D-01): APIs return copies and indices, and a parser passes its source to every call. Richer designs (returned borrows with elision, a `from` clause, non-lexical liveness) were studied and are preserved in `deferred/returned-borrows.md`.

### 2.5 Code generation

`&mut T` and exclusive slice parameters lower to C `restrict`-qualified pointers; `&const T` and shared slices to `const` + `restrict`. This is valid because §2.2 makes aliasing impossible in safe code, and `unsafe` code is required to uphold it (§6). A checker bug is therefore a miscompile: the checker is part of the trusted base and is tested against `tests/fail/` and a sanitizer oracle (`spec/06-compiler.md` §6).

---

## 3. Linear Values

### 3.1 What is linear

A type is **linear** if it is declared `linear struct`, or if any field, array element or `Result` payload is linear. Linearity cannot be lost by wrapping. An unbounded generic `T` is treated as possibly linear (`spec/02-types.md` §6).

`Buf[T]` is linear. File descriptors, sockets, allocations, and anything that must be released are `linear struct`s.

A **move** is any by-value use of a non-`Copy` value: passing it by value, `return v`, initializing a field or variable from it, or `try`/`catch` extracting a linear payload.

### 3.2 States

For every variable and by-value parameter `v` of linear type, the checker tracks, along every control-flow path:

| State | Meaning |
| :--- | :--- |
| **Unconsumed** | initialized, owned |
| **Consumed** | moved out or destroyed |
| **Deferred** | a `defer` will consume it at scope exit (§4) |
| **ErrDeferred** | an `errdefer` will consume it on error exits (§4) |

| Operation on `v` | Allowed in | Result |
| :--- | :--- | :--- |
| initialization | n/a | Unconsumed |
| borrow (`&const v`, `&mut v`, method with a borrow `self`); read a `Copy` field | Unconsumed, Deferred, ErrDeferred | unchanged |
| move | Unconsumed, ErrDeferred | Consumed |
| destructure `let T{ a, b, .. } = v;` | Unconsumed | Consumed; the bound names are new variables |
| assign `v = e` | Consumed | Unconsumed |
| any use of `v` | Consumed | **error** |
| assign `v = e` | Unconsumed | **error** (the old value would leak) |
| move a field out of `v` (`consume(v.f)`) | any | **error** (partial move; destructure instead) |

### 3.3 Destructuring is the base case

Within the directory module that defines `T`, `let T{ f1, f2, .. } = v;` consumes `v` and binds its fields. Every non-`Copy` field must be bound (and then consumed in turn); `..` may skip only `Copy` fields. Outside the defining module the private fields are invisible, so a value can only be consumed by calling a function that takes it by value, which bottoms out in a destructure. There is no `forget` and no implicit drop.

```
pub fn close(self: Fd) {
    let Fd{ raw } = self;       // consumes `self`; `raw` is Copy
    unsafe(close(raw));
}
```

### 3.4 Control flow

- At a join of non-diverging paths the state of every linear variable must be **identical** on all of them (`conditionally consumed` otherwise). Paths that end in `return`, `break`, `continue`, a call to `trap()`/`unreachable()`, or an exhaustive `switch` all of whose arms return, are checked at their own exits instead of at the join.
- A linear variable declared **outside** a loop must have the same state at the back-edge as at loop entry (so it can be consumed in the loop only if the loop then exits). A variable declared **inside** a loop body is checked per iteration.
- Shadowing creates a new variable; state is per binding.
- At every function exit, and at every scope exit for variables declared in that scope, each linear variable must be Consumed or Deferred (or ErrDeferred on an error exit, §4). Otherwise: `linear value 'v' exits scope unconsumed`.
- A value of linear type that is produced and not bound, passed, or returned (a discarded call result, `open();`) is an error.
- `swap(&mut a, &mut b)` exchanges two linear values without moving either out; it is how a linear field is replaced through a `&mut` borrow (`litmus/01_hashmap.kr`).
- Aborts do not run `defer`, and leak diagnostics do not apply to paths that abort.

A call that takes a linear argument by value consumes it whether or not the call succeeds: when it returns an error, the callee owns what happened to the value. Errors carry no payload, so a failed consume cannot hand the value back.

---

## 4. `defer` and `errdefer`

`defer S` registers `S` to run when control leaves the **enclosing block** by any path: fall-through, `return`, `break`, `continue`, or a propagating `try`. Deferred statements of a block run last-in first-out.

- **`S` is evaluated at exit.** Names in `S` refer to the variable, not a snapshot. Writing `defer arena.destroy();` and then reading `arena.capacity` is fine.
- **Registering a `defer` that consumes a linear variable `v` moves `v` to Deferred.** In Deferred, `v` can be borrowed and its `Copy` fields read, but not moved, consumed, or reassigned. (`defer close(fd); return fd;` is an error.) At every exit of the scope the deferred statement consumes `v`.
- **A `defer` may consume only variables declared in its own block.** (`if (c) { defer close(fd); }` for an outer `fd` is an error.)
- **`S` may not contain `return`, `break`, `continue`, or `try`:** cleanup cannot change control flow.
- `return e;` evaluates `e` first, then runs the deferred statements, then returns, so `return unwrap_or(m.get(7), 0);` reads the map before `defer m.destroy()` runs.
- A `defer` in a loop body runs at the end of every iteration and on `continue`/`break`.

**`errdefer S`** is `defer` that runs only on **error exits**: a `try` that propagates, or a `return` whose operand has the error-enum type `E`. A `return` whose operand has type `T` is a success exit; a `return` of an already-built `Result` counts as **both**.

For a linear `v`, `errdefer v.destroy();` moves `v` to **ErrDeferred**, which permits borrowing **and moving**. On an error exit the statement runs iff `v` is not yet Consumed on that path (decided statically, since state is path-exact). On a success exit an ErrDeferred variable must already have been consumed by something else, otherwise it is a leak.

```
let keys = try Buf[K].filled(cap, k0);
errdefer keys.destroy();                       // keys: ErrDeferred
let vals = try Buf[V].filled(cap, v0);         // if this fails, keys.destroy() runs
errdefer vals.destroy();
return Map[K, V]{ keys: keys, vals: vals, ... };   // success exit: moves keys and vals
```

`errdefer` for non-linear cleanup runs on every error exit.

---

## 5. Initialization

- Every `let`/`mut` binding is initialized in its declaration.
- A struct literal must name **every** field.
- There is no implicit zero-fill. Repeat a value explicitly: `[0; 4096]`, `Buf[u8].filled(n, 0)`.
- Padding bytes have unspecified contents and safe code cannot observe them.

So nothing is ever uninitialized, and a non-null pointer or a linear handle cannot be fabricated by zeroing.

---

## 6. Raw Pointers and `unsafe`

`T*` is a non-null raw pointer; `?T*` may be null. Raw pointers are plain `Copy` values. They carry no ownership, no bounds, and no lifetime.

**Safe operations:** create (`s.ptr` for a slice or array), copy, compare, store, and pass to C. **Everything else requires `unsafe(...)`:** dereference `*p`, arithmetic `p + n`, conversion between pointer types or from an integer, and calling any C function. `unsafe ( Expr )` marks **one expression**; the result is an ordinary value.

```
let n = unsafe(read(self.raw, buf.ptr, buf.len));
```

**Nullable pointers.** `null` has type `?T*` (a `T*` cannot be null). There is no flow-typed narrowing: test with `is_null(p)` and convert with `unwrap_or_trap(p)`, which aborts on null. Declare any C pointer that may be null as `?T*`.

**The `unsafe` contract.** Code inside `unsafe(...)` must itself uphold every rule in this chapter: it must not alias an exclusive borrow, not outlive or free memory it did not own, not forge a linear value, and not index out of range. Violating that contract is the only source of undefined behavior in Kore.

---

## 7. Checker Obligations

A conforming compiler rejects every program in `tests/fail/`. Each file starts with `// ERROR: <rule>`. They cover, by rule: borrow placement (§2.1), the call rule (§2.2), moving out of borrows (§2.3), linear use, leaks, joins, loops, partial moves and discards (§3), `defer`/`errdefer` (§4), initialization (§5), unsafe and nullability (§6), plus the type-level rules of `spec/02-types.md`. The programs in `litmus/` must be accepted.
