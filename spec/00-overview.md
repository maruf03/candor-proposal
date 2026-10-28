# Candor 0: Overview

**Candor** is a small, statically typed, ahead-of-time compiled systems language. It is C with the sharp edges filed off: the same structs, pointers and calling convention, with defined arithmetic, checked array and slice bounds, and mandatory initialization. There is no garbage collector, no borrow checker, no `unsafe`, and no built-in container. It gives you primitives, not policies.

This is **draft 2 of the specification**. No compiler exists yet. The grammar is mechanically verified; the type rules are covered by 38 must-reject programs and seven litmus programs (`docs/litmus.md`).

---

## 1. A Taste

```rust
extern "C" {
    fn open(path: const u8*, flags: i32) -> i32;
    fn close(fd: i32) -> i32;
}

pub fn main() -> i32 {
    let fd = open("/etc/hostname\0".ptr, 0);
    if (fd < 0) { return 1; }
    defer close(fd);                 // runs on every path out of this block
    return 0;
}
```

---

## 2. Principles

1. **Small.** 25 keywords and 3 literals. No traits, closures, macros, operator overloading, ownership tracking, or built-in containers. A new feature must be required by a program that cannot be written without it (`docs/decisions.md`, D-03).
2. **C is the model.** Structs have C layout, functions have the C ABI, pointers are addresses, and calling C is a plain call. Where a question has a C answer, Candor gives it.
3. **Defined where it is cheap.** Overflow aborts, division and shifts are specified, arrays and slices are bounds-checked, and nothing is uninitialized. Pointer misuse is not defended against (`spec/03-memory.md` §1).
4. **Explicit.** No implicit numeric conversion, no truthiness, no hidden calls beyond `defer` and the receiver conveniences of a method call.
5. **Primitives, not policies.** Pointers, `slice(p, n)`, `size_of`, casts and function pointers are enough to write an allocator, a vector, an arena or a hash map as library code.

---

## 3. The Memory Model in One Paragraph

You allocate and free memory yourself, with `malloc` or an allocator you write. A slice is a `{ptr, len}` value that remembers nothing about where it came from. Nothing checks ownership, lifetime, or aliasing, as in C. `defer` runs cleanup on every exit of a block, so `close(fd)` is hard to forget. Safety nets are tools: a debug allocator and sanitizer builds of the emitted C.

---

## 4. What You Give Up (Honest Trade-offs)

- **No memory safety guarantees.** Use after free, double free, leaks and dangling pointers are possible. This is the price of the model above.
- **No traits.** Generic code cannot hash, compare, or use operators on `T`; pass function pointers (`litmus/01_hashmap.cn`).
- **No tagged unions, tuples, closures, or pattern matching.** Errors are plain return values.
- **Single-threaded.** No threads or atomics yet.
- **No globals, variadics, or exported functions yet** (`docs/decisions.md`, D-17).

---

## 5. Scope

**In:** structs, fieldless enums, `impl`, generics, `defer`, `extern "C"` imports, directory modules with `pub`/`import`, `distinct`, `as`, arrays, slices, single-object raw pointers, function pointers, C layout and ABI.

**Deferred** (`docs/decisions.md` D-17, `deferred/`): ownership checking, `Result`/`try`, tagged unions, compiler directives, variadics and exports, mutable globals, concurrency, package manager, language server, LLVM backend.

---

## 6. Document Map

| File | Contents |
| :--- | :--- |
| `spec/00-overview.md` | this file |
| `spec/01-syntax.md` | lexical rules, reserved words, precedence, verified grammar |
| `spec/02-types.md` | types, conversions, arithmetic, pointers, slices, prelude |
| `spec/03-memory.md` | what is guaranteed, allocation, `defer`, initialization |
| `spec/04-ffi.md` | calling C |
| `spec/05-modules.md` | directory modules, visibility, imports |
| `spec/06-compiler.md` | implementation plan, C lowering, milestones, tests |
| `docs/decisions.md` | every decision, rationale, what is deferred and why |
| `docs/litmus.md` | what the seven litmus programs showed |
| `litmus/`, `tests/` | programs that must be accepted, rejected, or fail to parse |
| `tools/` | LL(1) checker, parser, keyword and test runners |
| `deferred/` | designs parked for later |
