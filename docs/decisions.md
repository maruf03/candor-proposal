# Kore Decision Log

One entry per decision: what was chosen, what else was considered, what it costs. **Provenance**: **Author** (the language's author chose it), **Approved** (proposed, then approved), **Default** (a call made without an explicit answer; reverse it freely). Entries marked *taste call* have no technical argument either way.

History: the first specification (commit `3c61f4f`) was a memory-safe design with call-scoped borrows, linear types and a built-in `Buf`. The author redirected the project to a C-like language (D-01). Those designs are summarized in `deferred/ownership-checking.md`; the full text is in git.

---

## Direction

### D-01: Kore is C with defined arithmetic, not a safe language
**Author.** No garbage collector, no borrow checker, no hidden machinery. The language provides **zero-overhead primitives** from which a programmer builds whatever memory management they want, the way C lets you build objects without having OOP. Use after free, leaks, dangling pointers and aliasing are the programmer's problem; the language fixes the *arithmetic and bounds* class of bugs and the *uninitialized variable* class, because those cost almost nothing.
- *Why:* the previous design drifted toward Rust: a smaller borrow checker is still a borrow checker, and it forced a compiler-known container (`Buf`), a `Copy` marker and an `unsafe` boundary just to be consistent.
- *Closest neighbours:* C, Zig, Odin, Hare.
- *Cost:* no compile-time memory safety. The intended net is tools: a debug allocator, sanitizer builds of the emitted C.

### D-02: No `unsafe`
**Author.** There is no safe subset to opt out of. Pointers, casts and C calls are ordinary operations (`spec/03-memory.md` §1).

### D-03: Feature-admission rule
**Approved.** A construct is added only if a program in `litmus/` cannot be written without it, and it must displace something or cost nothing at runtime. Convenience that needs a new keyword or a new tracking pass is rejected by default. Compiler directives (`align`, `packed`, symbol names, variadics) come *later*, when a program needs exact control.

---

## Memory

### D-04: Slices are plain `{ptr, len}` values
**Default.** Copyable, storable, returnable; bounds-checked on index, unchecked about lifetime. This removes the need for any built-in container: a library `Vec[T]` is a slice plus a length (`litmus/05_allocator_vec.kr`).

### D-05: No built-in allocator or container
**Author.** `malloc`/`free` are ordinary `extern "C"` calls; allocators are user structs of function pointers passed explicitly. The prelude holds only what the language cannot express itself: `slice`, `trap`, `wrapping_*`; `size_of(T)` is a keyword form. `align_of` is deferred until alignment directives exist (D-03).

### D-06: Errors are ordinary values
**Default, reversible.** No `Result`, `try`, `catch`, `errdefer`. A function returns an enum code, a negative integer, a null pointer, or a struct. Reason: tagged results are not C-ABI friendly, add three keywords, and need an error-type story. Re-entry criterion: litmus programs become dominated by repetitive `if (rc < 0) return rc;` plumbing. *Taste call.*

### D-07: `defer` stays, without `errdefer`
**Default.** One visible mechanism; it makes `close(fd)` unforgettable on every path and costs nothing.

### D-08: Mandatory initialization
**Approved (carried over).** Every binding has an initializer and every struct literal names every field: no zero-fill, no dataflow analysis (it is a grammar fact: `let x: T;` does not parse).

---

## Types and Arithmetic

### D-09: Arithmetic is defined
**Approved (carried over).** `+ - *` abort on overflow in every build; `wrapping_add/sub/mul` wrap. `/ %` abort on zero and `MIN / -1`. Shifts mask the amount; `<<` acts on the bit pattern. Float to int saturates. Evaluation is left to right. The C lowering uses temporaries and unsigned shifts to deliver these (`spec/06-compiler.md` §4); an independent review found the first lowering plan did not.
- *Cost:* an overflow check on every `+`. Use `wrapping_*` where it matters.

### D-10: Pointers: all nullable, arithmetic, casts anywhere
**Default.** `T*` and `const T*`; `null` converts to any pointer; `p + n`, `p[i]`, `p - q`, `&x`; `as` between pointers and integers. No `?T*`, no `is_null`, no flow typing.

### D-11: All types copy by value; no `Copy` marker, no `linear`
**Follows from D-01.**

### D-12: Struct layout and calling convention are C's
**Author.** Every struct has C layout; structs are passed and returned by value with the C ABI; enums are their backing integer; function pointers are C function pointers (callbacks work). `align`, `packed` and similar come as directives when needed (D-03).

### D-13: Generics are monomorphized and checked per instantiation
**Default.** No bounds, no markers, like C++ templates. Errors point at the instantiation. Without traits, hashing and equality are function-pointer parameters.

### D-14: Syntax carried over
`Result`-free `[T]` generics in both type and expression position, `x as T` with parenthesized pointer targets, Rust-style operator precedence with non-associative comparison, `let`/`mut` bindings, `enum E : u8`, `distinct`. (*Taste call:* `let`/`mut` could become C-style declarations with `const` for immutables; kept to avoid churn.) Grammar checks are enforced by scripts (`tools/`).

---

## Process

### D-15: Rust compiler, emit C, clang
**Approved.** git from the start. With no ownership analysis the type checker is the whole front end (`spec/06-compiler.md` §5).

### D-16: Single-threaded for now
**Approved.** Threads, atomics and a memory model are out of scope; a C-like language will add them as library calls plus intrinsics later.

### D-17: Deferred features and when they come back

| Feature | Re-entry criterion |
| :--- | :--- |
| ownership/aliasing checking | as an *optional* separate analysis, never required by syntax (`deferred/ownership-checking.md`) |
| `Result`, `try`, `catch` | D-06 |
| tagged unions | a litmus program needs a sum type without manual tag plumbing |
| compiler directives (`align`, `packed`, symbol names) | a program needs exact layout or naming |
| variadic imports, exported functions, C unions, C globals | same |
| mutable globals | a program needs process-wide state |
| concurrency | a program needs threads; start from C's model |
| package manager, LSP, LLVM backend | `deferred/` notes |

---

## Open Questions

1. Is the arithmetic overflow check cheap enough, or should it be a build flag?
2. Does `let`/`mut` stay, or should declarations look like C?
3. Are errors-as-values pleasant enough in `litmus/04` and `litmus/06`, or does D-06 return?
4. Does a debug allocator plus sanitizer builds give enough safety net?
