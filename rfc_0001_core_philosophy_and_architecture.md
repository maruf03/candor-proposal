# RFC 0001: Core Philosophy, Design Pillars, and Elimination of Undefined Behavior

- **RFC Number:** 0001
- **Title:** Core Philosophy, Design Pillars, and Elimination of Undefined Behavior
- **Author:** Language Design Working Group
- **Status:** Draft (revised 2026-10-28 after design review; see `DECISIONS.md`)
- **Type:** Standards Track (Core Language)
- **Created:** 2026-10-28

---

## 1. Abstract

This RFC establishes the foundational design principles of the **Kore** programming language. It defines the trade-off matrix governing syntax ergonomics, compile-time safety without garbage collection, zero-overhead execution, and the complete removal of Undefined Behavior (UB) from safe language constructs.

---

## 2. Motivation & Problem Statement

Modern systems programming forces developers into an uncomfortable trilemma:

1. **C and C++** offer raw hardware access and zero-cost C ABI compatibility, but suffer from pervasive Undefined Behavior (signed integer overflow, uninitialized reads, dangling pointers), legacy declarator syntax, and fragile preprocessor macros.
2. **Rust** solves memory and concurrency safety without a garbage collector, but introduces substantial cognitive and syntactic complexity: lifetime algebra (`'a: 'b`), complex trait bounds, borrow-checker fighting on graph/arena structures, and slow compile times.
3. **Zig** simplifies C cross-compilation and eliminates hidden control flow, but relies heavily on dynamic-style `comptime` type manipulation that obscures static function signatures and requires manual vigilance to avoid use-after-free bugs.
4. **C# and Go** provide exceptional readability, fast onboarding, and clean structured syntax, but rely on heavy managed runtimes, garbage collectors, and costly FFI boundaries (`cgo` / P/Invoke) that penalize native C library calls.

**Kore** resolves this trilemma by combining **C#'s high readability**, **Go/Lua's small grammatical surface**, **C's exact ABI memory layout**, and **a deterministic 5-rule compile-time ownership verifier**.

---

## 3. The Five Non-Negotiable Design Pillars

### Pillar 1: "Zero Magic" Readability
Code is read far more often than it is written. Kore bans hidden control flow and implicit costs:
* **No hidden function calls:** No C++-style implicit copy constructors, move constructors, or hidden operator overloading.
* **No implicit type widening or truthiness:** An `i32` never implicitly converts to `i64` or `f64`. Conditionals (`if`, `while`) require strict `bool` expressions (`if (ptr != null)`, never `if (ptr)`).
* **No metaprogramming sub-language:** Generics are expressed via clean parametric type signatures (`RingBuffer[T]`), never through Turing-complete compile-time scripts or hygienic macro DSLs.

### Pillar 2: Minimal Surface, Maximum Orthogonal Leverage
Rather than adding specialized syntax for every use case, Kore restricts its grammar to **29 keywords plus the 3 literal words `true`, `false`, `null`** (RFC 0002 §2). Every top-level construct and local declaration begins with an explicit keyword token (`fn`, `struct`, `enum`, `impl`, `type`, `const`, `let`, `mut`). The grammar is $LL(1)$ with single-token lookahead, **verified mechanically** by `tools/ll1.py` (RFC 0002 §8).

### Pillar 3: True Zero-Overhead C Interoperability
C holds a 50-year ecosystem of battle-tested systems libraries (`libc`, `sqlite3`, `libuv`, `openssl`, `io_uring`, `raylib`). Kore treats C libraries as first-class citizens:
* Every plain Kore `struct` whose fields are C-visible types uses the standard platform C ABI field alignment and padding. Structs containing slices, tuples or `Result[T, E]` have Kore layout and cannot appear in `extern` signatures (RFC 0003 §2.2).
* Calling an `extern "C"` function emits a direct machine `call` instruction with zero wrapper stubs, zero heap allocations, and zero stack switching.

### Pillar 4: Memory Safety Without Lifetimes or Garbage Collection
Instead of tracking arbitrary graph lifetimes across structs and return values, Kore enforces structural memory discipline (RFC 0003 §4):
1. **Borrows are second-class.** References and slices (`&T`, `&mut T`, `T[]`) live only in parameters and locals, never in non-borrowing structs, and may be returned only when derived from the function's single borrowing parameter (elision, no lifetime syntax). Exclusivity is checked by liveness over the CFG.
2. **Heap allocations and OS descriptors are `linear` values** that must be consumed exactly once before leaving scope, verified statically over the CFG. Linearity is inferred through any wrapper.
3. **Scoped teardown (`defer`, `errdefer`)** guarantees deterministic cleanup across normal, early-return, and error paths.
4. **Raw pointers are inert in safe code**: copyable and storable, never dereferenced outside `unsafe`.

### Pillar 5: Elimination of Undefined Behavior (Zero UB in Safe Code)
In C and C++, compilers treat Undefined Behavior as a license to silently delete safety checks or corrupt program logic. In Kore, **every syntactically valid program outside an `unsafe` block has 100% deterministic, defined operational semantics.**

> **Status of this claim (Draft).** This is the *goal*; it is not yet fully specified. Rows 1, 4, 7 and 8 of the table below were corrected after review. Still open before the claim can be made without qualification: division/remainder trap rules for every integer width (`INT_MIN / -1` for each type, and `%`), operand and argument evaluation order (to be left-to-right), float-to-int behavior (`cast` saturates, RFC 0003 §2.1, D-020), stack-overflow probes, defined behavior of `trap()` (abort, no `defer`), and **data races**, which RFC 0004 must either forbid statically or confine to `unsafe`.

---

## 4. Formal Resolution of C/C++ Undefined Behavior Categories

To guarantee zero UB while preserving native speed, Kore defines exact hardware behavior for every hazard present in C and LLVM IR:

| C / LLVM Undefined Behavior | Kore Defined Specification | LLVM IR Lowering & Performance Impact |
| :--- | :--- | :--- |
| **1. Uninitialized Memory Reads** | **Definite initialization:** every binding is initialized at its declaration and every struct literal names every field, so there is nothing to read uninitialized. Explicit zero-fill is `zeroed(T)`, legal only for `Zero` types (RFC 0003 Rule 5). Padding bytes are unobservable in safe code. | No implicit `memset`. `zeroed` lowers to a zero store or `llvm.memset` only where written. |
| **2. Signed Integer Overflow** | Signed and unsigned integer arithmetic (`+`, `-`, `*`) is defined as two's-complement modulo $2^N$ wraparound. | Emits standard LLVM `add`, `sub`, `mul` **without** the `nsw` (No Signed Wrap) poison flag. Zero runtime penalty; matches native ALU instructions. |
| **3. Division by Zero / `INT_MIN / -1`** | Integer `/` or `%` by `0`, or `MIN / -1` and `MIN % -1` at **every** integer width, aborts the program deterministically (`trap()`). Float division follows IEEE-754 and never traps. | Two predicted-false guards before `sdiv`/`srem`/`udiv`/`urem`: `d == 0`, and (signed types) `d == -1 && n == MIN`, each elided when range analysis proves it impossible. A constant divisor of 0 is a compile error. x86 `idiv` also faults on overflow, but AArch64 `sdiv` does not trap and LLVM treats the case as undefined, so the explicit guard is required. `trap()` lowers to `llvm.trap` (SIGILL/SIGTRAP); the spec calls it *abort*. |
| **4. Bit Shift Out-of-Range** | Shifting an $N$-bit integer by $\ge N$ bits masks the shift count to $N - 1$ ($\text{shift\_amt} \bmod N$). `>>` is arithmetic on signed and logical on unsigned types. The shift amount is converted to the operand type before masking. A constant amount $\ge N$ is a compile error. | The compiler emits an explicit `and amt, N-1` before every `shl`/`lshr`/`ashr`, because LLVM treats an oversized amount as `poison` regardless of what hardware does. For 32/64-bit operands the `and` folds into the hardware mask; for 8/16-bit operands it is a real instruction. |
| **5. Null Pointer Dereference** | Pointers (`T*`) and references (`&T`) are statically non-null. Nullable pointers (`?T*`) cannot be dereferenced without flow-typed null narrowing. | Zero runtime checks required on `T*` or `&T`. Null checks occur once at the narrowing branch (`if (p != null)`). |
| **6. Buffer Overruns** | Slices (`T[]`, borrowed views) carry `{ ptr, len }`. Indexing `slice[i]` performs an unsigned bounds check `i < slice.len`. | Emits `icmp ult` on the index (`i64` on 64-bit targets, `usize` generally) branching to a cold abort block. For `for (x in slice)` no check is needed; for indexing in other loops LLVM's loop passes (for example `IRCE`, `LoopPredication`) can remove many checks. A slicing expression `a[lo..hi]` checks `lo <= hi <= len`. |
| **7. Strict Aliasing Violations** | Kore does not use C's Type-Based Alias Analysis (TBAA). Exclusive borrows (`&mut T`, mutable slices) guarantee physical exclusivity, enforced by the liveness-based check in RFC 0003 Rule 2. | Emits `noalias` **only** on properties the checker proved (RFC 0003 Rule 2). `unsafe` code that violates exclusivity is undefined behavior; this is the language's only source of UB. |
| **8. Dangling References & Leaks** | Borrows are second-class and frozen sources cannot change while borrowed; `linear` values cannot leave scope unconsumed. Raw pointers may dangle but cannot be dereferenced outside `unsafe`. (Leaks are not UB; they are rejected as a resource-safety property.) | Compile-time verification; zero runtime reference counting or GC pauses. |

---

## 5. Summary of Trade-Offs Accepted

By adopting these pillars, Kore intentionally rejects certain paradigms:
* **No Cyclic Object Graphs via References:** Because references cannot be stored inside structs, cyclic graphs (e.g., doubly-linked lists, ASTs, ECS tables) are built using **typed arena indices** (`type NodeIdx = distinct u32;`) inside contiguous slices—which simultaneously improves CPU cache locality and eliminates pointer-chasing overhead.
* **No Dynamic Exceptions / Stack Unwinding:** Error handling uses explicit value returns (`Result[T, E]`, `try`, `catch`). Functions are `nounwind`, and every error path is visible in the source text. (Platform ABIs may still require unwind *tables* for debuggers and C callers; the saving is in runtime machinery, not necessarily in section size.)
* **No Stored Views:** Borrows (references and slices) cannot live in non-borrowing structs (RFC 0003 Rule 1). A tokenizer receives its source on each call or keeps it on the stack in a borrowing struct (`LITMUS.md` L2-1, L2-2). This is the price of having no lifetime annotations.
* **Containers of Linear Values Need Explicit Teardown:** There is no implicit drop, so a `Vec` of linear elements needs `destroy_with` (RFC 0003 §6.3).
* **No User Traits (yet):** Generics have only the built-in `Copy`/`Zero`/`Send`/`Sync` bounds; hashing and ordering go through function pointers (D-016).