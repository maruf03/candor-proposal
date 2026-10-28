# Kore 0: Overview

**Kore** is a small, statically typed, ahead-of-time compiled systems language. It aims for the memory safety of a modern language without a garbage collector and without lifetime annotations, defined behavior everywhere outside `unsafe`, and direct C interoperability, in a surface a programmer can learn in an afternoon.

This is **version 1 of the specification**. No compiler exists yet. The grammar is mechanically verified; the ownership rules are checked by hand against five programs and thirty-five must-reject programs (`docs/litmus.md`).

---

## 1. A Taste

```rust
linear struct Fd { raw: i32; }

extern "C" {
    fn dup(fd: i32) -> i32;
    fn close(fd: i32) -> i32;
}

pub enum DupError { Failed }

impl Fd {
    pub fn dup(raw: i32) -> Result[Fd, DupError] {
        let copy = unsafe(dup(raw));           // calling C is always `unsafe(...)`
        if (copy < 0) { return DupError.Failed; }
        return Fd{ raw: copy };
    }
    pub fn close(self: Fd) {
        let Fd{ raw } = self;                  // destructuring consumes the handle
        unsafe(close(raw));
    }
}

pub fn main() -> i32 {
    let f = Fd.dup(1) catch (e) { return 1; };
    defer f.close();                           // cannot be forgotten: `f` is linear
    return 0;
}
```

---

## 2. Principles

1. **Small.** The surface is 29 keywords and 3 literal words, one memory model with two moving parts (call-scoped borrows, linear values), no traits, no closures, no macros, no operator overloading. A new feature must be required by a program that cannot be written without it, and must displace something (`docs/decisions.md`, D-03).
2. **Memory safe without a runtime.** No garbage collector, no reference counting, no lifetime annotations. Safety comes from three rules (`spec/03-memory.md`).
3. **Defined behavior.** Outside `unsafe(...)` every operation has one defined result or aborts: overflow aborts, division and shifts are specified, indexing is checked, nothing is uninitialized.
4. **Explicit.** No implicit numeric conversion, no truthiness, no hidden calls beyond `defer` and the receiver borrow of a method call.
5. **C is a neighbor, not a foreign country.** Structs use the C layout; calling C is a plain C call.

---

## 3. The Memory Model in One Paragraph

A reference (`&const T`, `&mut T`, slice) exists only as a function parameter and as the argument of a call. It cannot be returned, stored, or bound, so it cannot outlive the call and cannot dangle; within one call, borrows of overlapping data must all be shared, so exclusive borrows are exclusive. Resources (files, memory, handles) are `linear` structs: the compiler tracks every path and rejects a program that forgets to release one or releases one twice. `defer` and `errdefer` make cleanup path-complete. Raw pointers exist for C and are inert in safe code.

---

## 4. What You Give Up (Honest Trade-offs)

- **No returned or stored references.** A getter returns a copy or an index. A parser passes its source to every call. Graphs and trees use typed indices into a `Buf` (`litmus/03_arena_graph.kr`, `litmus/05_typed_arena.kr`).
- **Containers hold `Copy` elements only.** `Buf[T]` of linear values is not available in v1.
- **No traits.** Generic code cannot hash, compare, or use operators on `T`; pass function pointers (`litmus/01_hashmap.kr`).
- **No tagged unions, tuples, closures, or pattern matching.** Errors are `Result[T, E]` with fieldless enum errors.
- **Single-threaded.** No threads, atomics, or coroutines in v1.
- **Privacy is per directory**, so a linear type can be forged by code in its own module.

Each item has a stated re-entry criterion in `docs/decisions.md` D-21.

---

## 5. Scope of Version 1

**In:** structs, fieldless enums, `impl`, generics bounded by `Copy`, `linear` types, `defer`/`errdefer`, `Result`/`try`/`catch`, `unsafe(expr)`, `extern "C"` imports, directory modules with `pub`/`import`, built-in `Buf`, `distinct`, `as`, arrays and slices, C layout for all structs.

**Deferred** (kept in `deferred/`): threads, atomics, `Mutex`, `Send`/`Sync`, coroutines; tagged unions, traits, closures; globals; C-ABI callbacks, variadics, unions, exported functions; user allocators and regions; containers of linear values; returned or stored borrows; package manager, `.kpkg`, language server, LLVM backend, PGO, non-Linux targets.

---

## 6. Document Map

| File | Contents |
| :--- | :--- |
| `spec/00-overview.md` | this file |
| `spec/01-syntax.md` | lexical rules, reserved words, precedence, verified grammar |
| `spec/02-types.md` | types, conversions, arithmetic, errors, prelude |
| `spec/03-memory.md` | borrows, linear values, `defer`, initialization, `unsafe` |
| `spec/04-ffi.md` | calling C |
| `spec/05-modules.md` | directory modules, visibility, imports |
| `spec/06-compiler.md` | implementation plan, C lowering, milestones, tests |
| `docs/decisions.md` | every decision, rationale, alternatives, what is deferred and why |
| `docs/litmus.md` | what the five litmus programs showed |
| `litmus/`, `tests/` | programs that must be accepted, rejected, or fail to parse |
| `tools/` | LL(1) checker, parser, keyword and test runners |
| `deferred/` | designs and research parked for later |
