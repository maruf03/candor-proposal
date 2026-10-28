# Kore 3: Memory

Kore manages memory the way C does: you allocate, you free, and nothing checks you. The language adds three things on top: **defined arithmetic and bounds**, **mandatory initialization**, and **`defer`** for cleanup. It gives you the primitives to build allocators and containers; it does not provide them.

---

## 1. What Is and Is Not Guaranteed

| Class of bug | Kore |
| :--- | :--- |
| integer overflow, bad division, bad shifts | defined: abort or specified result (`spec/02-types.md` §4) |
| out-of-bounds index on an array or slice | aborts |
| uninitialized variable | impossible: every binding and struct field is initialized (§5) |
| implicit conversions losing data | compile error |
| null or dangling pointer dereference | **not guaranteed**: same as C |
| out-of-bounds access through a raw pointer | **not guaranteed** |
| use after free, double free, leak | **not guaranteed** |
| aliasing, data races | **not guaranteed**; Kore is single-threaded for now |

**There is no `unsafe` marker** because there is no safe subset to opt out of: pointers, casts and C calls are ordinary operations. The emitted C is compiled with `-fno-strict-aliasing`, so reinterpreting memory through different pointer types behaves like the machine, but an optimizer may still assume no null dereference and no out-of-bounds access. Tools (a debug allocator, sanitizer builds) are the intended safety net, not the type system.

---

## 2. Pointers and Slices

- `T*` is an address; `const T*` forbids writing through it. Any pointer may be `null`. `&x` makes a pointer to a variable, field or element.
- `T[]` is `{ptr, len}`: a pointer plus a length, bounds-checked on `[i]`. It owns nothing and may be copied, stored, and returned freely.
- Local variables and arrays live in the frame of their function. A pointer or slice to one must not outlive the call, exactly as in C; nothing checks it.
- Heap memory is raw `u8*` from an allocator, converted to the element type with `as` and given a length with `slice(p, n)`:

```
let raw = malloc(n * size_of(u32));
let xs: u32[] = slice(raw as (u32*), n);
```

(`n * size_of(u32)` aborts on overflow, so a hostile `n` cannot under-allocate.)

---

## 3. Allocation

The prelude has no allocator. Use libc directly, or write an allocator as a plain struct of function pointers that you pass where needed (no hidden global state):

```
struct Alloc {
    ctx: u8*;
    alloc: fn(u8*, usize) -> u8*;
    free: fn(u8*, u8*) -> void;
}
```

Containers (`Vec[T]`, arenas, maps) are library code over an `Alloc` and a slice (`litmus/05_allocator_vec.kr`). Nothing in the language needs to know about them.

---

## 4. `defer`

`defer S;` or `defer { ... }` schedules `S` to run when the **enclosing block** exits, by any path: end of block, `return`, `break`, `continue`. Multiple defers run LIFO.

- **`S` is evaluated at exit.** Names in `S` refer to the variable, not a snapshot.
- `return e;` evaluates `e` first, then runs the deferred statements, then returns.
- In a loop body, the defer runs at the end of every iteration and on `break`/`continue`.
- A `defer` body may not contain `return`, `break` or `continue`.
- A deferred statement runs only if control reached the `defer`: it is skipped on paths that left the block earlier.
- Aborts (`trap()`, bounds, overflow) skip `defer`.

```
let fd = open(path, 0);
if (fd < 0) { return -1; }
defer close(fd);              // not reached on the path above
```

---

## 5. Initialization

Every `let`/`mut` binding has an initializer; every struct literal names every field. There is no zero-fill, so there is nothing for a zero value to mean. Arrays are initialized with `[v; n]` or `[a, b, c]`. Memory from `malloc` is uninitialized, as in C; reading it before writing is your bug.

---

## 6. Obligations on a Conforming Compiler

A conforming compiler rejects every program in `tests/fail/` (the first line of each file names the rule) and accepts every program in `litmus/`. The rules are the type-level ones of `spec/02-types.md` plus the `defer` and initialization rules above. No analysis beyond type checking and simple syntactic checks is required.
