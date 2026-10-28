# Candor

A small, statically typed, ahead-of-time compiled systems language that is **C with the sharp edges filed off**: no garbage collector, no borrow checker, no hidden machinery. Structs and calls match C exactly. Arithmetic, bounds on arrays and slices, and initialization are defined; everything about pointers and memory is yours, with primitives to build any allocator or container you need.

**Status:** specification (draft 2). **No compiler exists yet.** The grammar is mechanically verified; the type rules are specified and covered by 38 must-reject programs.

```rust
extern "C" {
    fn malloc(n: usize) -> u8*;
    fn free(p: u8*);
}

struct Vec[T] { items: T[]; len: usize; }

impl[T] Vec[T] {
    pub fn with_capacity(n: usize) -> Vec[T] {
        let p = malloc(n * size_of(T));          // overflow aborts, never wraps
        return Vec[T]{ items: slice(p as (T*), n), len: 0 };
    }
    pub fn push(self: Vec[T]*, v: T) {
        if (self.len == self.items.len) { trap(); }
        self.items[self.len] = v;                // slice index is bounds-checked
        self.len += 1;
    }
}

pub fn main() -> i32 {
    mut v = Vec[u32].with_capacity(8);
    defer free(v.items.ptr as (u8*));
    v.push(7);
    return 0;
}
```

## The Idea

C gives you pointers, structs and the machine. Candor keeps all of that and fixes only what costs nothing to fix: integer overflow, division, shifts, array and slice bounds, and uninitialized variables are defined. There is no `unsafe` (nothing to opt out of), no built-in container (a `Vec` is library code over a slice), no ownership tracking, and no traits or closures. `defer` is the one convenience for cleanup. 25 keywords. Safety nets are tools, not syntax.

The trade-offs are listed in `spec/00-overview.md` §4; every decision is in `docs/decisions.md`.

## Layout

| Path | Contents |
| :--- | :--- |
| `spec/00-overview.md` ... `06-compiler.md` | the specification: overview, syntax, types, memory, FFI, modules, compiler plan |
| `docs/decisions.md` | every decision with alternatives and costs; what is deferred and why |
| `docs/litmus.md` | what the six litmus programs showed |
| `litmus/` | six programs that must be accepted |
| `tests/fail/`, `tests/syntax_fail/` | programs that must be rejected (semantically / by the parser) |
| `tools/` | LL(1) checker, parser, keyword check, test runner |
| `deferred/` | parked designs: ownership checking, concurrency, LLVM backend, packages and LSP |

## Checking the Grammar and Tests

```bash
python3 tools/ll1.py spec/01-syntax.md             # conflicts: 0
python3 tools/check_keywords.py spec/01-syntax.md  # keyword box, grammar, parser agree
python3 tools/run_tests.py spec/01-syntax.md       # litmus + tests behave as expected
```

## Next

`spec/06-compiler.md` §5: M0 is the parser and pretty-printer in Rust, then the type checker and C emitter.
