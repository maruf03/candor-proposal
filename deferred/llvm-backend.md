> **DEFERRED, NOT PART OF CANDOR.** Draft LLVM IR lowering, DWARF, and PGO notes. v1 emits C instead (`spec/06-compiler.md`). Several claims here are known to be wrong or unverified (error-union register assignment is not the C ABI, `perf script | pprof` needs a converter, frame-pointer cost is understated).
> References to "RFC 000N", `DESIGN_REVIEW*.md`, and `DECISIONS.md` point to v0.3 documents recoverable from git (snapshot commit `1f54205`). Code samples use draft syntax and are not guaranteed to parse or typecheck against `spec/`. Kept for the ideas; see `docs/decisions.md` D-21 for when this returns.

# RFC 0005: Reference Compiler Architecture (`candorc`), LLVM IR Lowering, and Zero-Overhead Observability

- **RFC Number:** 0005
- **Title:** Reference Compiler Architecture (`candorc`), LLVM IR Lowering, and Zero-Overhead Observability
- **Author:** Language Design Working Group
- **Status:** Draft (status and keyword count corrected 2026-10-28; **§5.2 ABI lowering and §3 implementation-language choice are under review**, see `DECISIONS.md` D-017 and `DESIGN_REVIEW.md` section C)
- **Type:** Standards Track (Compiler Backend & Observability)
- **Created:** 2026-10-28

---

## 1. Abstract

This RFC specifies the internal architecture of the Candor reference compiler (`candorc`), including frontend AST data structures, the on-demand generic monomorphizer, the Control Flow Graph (CFG) verifier for `linear` resources, exact Candor-to-LLVM-IR lowering templates, zero-overhead hardware profiling (`perf` / `pprof` via DWARF v5 and frame pointers), and two-phase Profile-Guided Optimization (PGO).

---

## 2. Five-Stage Compiler Pipeline

`candorc` is structured as a modular 5-stage pipeline where stages 1–3 are shared between batch compilation (`candor build`) and the interactive Language Server (`candor lsp`):

```
[ Source Files (*.cn) & Precompiled Stubs (api.cn.d) ]
                         |
                         v
+--------------------------------------------------------+
| Stage 1: Lexer & Fault-Tolerant LL(1) Parser           |
|   - Stateless UTF-8 scanner (29 keywords + 3 literals)              |
|   - Single-token lookahead recursive descent parser    |
+--------------------------------------------------------+
                         |
                         v
+--------------------------------------------------------+
| Stage 2: Two-Pass Module & Type Resolver               |
|   - Pass 2a: Top-level type, struct layout & fn table  |
|  - Pass 2b: Expression type checking & generic bounds  |
|   - On-demand AST Monomorphization for [T] templates   |
+--------------------------------------------------------+
                         |
                         v
+--------------------------------------------------------+
| Stage 3: CFG Ownership & Concurrency Verifier          |
|   - Downward Reference escape & exclusivity check      |
|   - Linear variable consumption dataflow verification  |
|   - Auto-derivation of Send / Sync at thread boundaries|
+--------------------------------------------------------+
                         |
                         v
+--------------------------------------------------------+
| Stage 4: LLVM IR Lowering & Instrumentation            |
|  - Struct layout, Candor and C calling conventions       |
|  - LIFO 'defer'/'errdefer' expansion, definite init    |
|   - DWARF v5 debug info + PGO counter injection        |
+--------------------------------------------------------+
                         |
                         v
+--------------------------------------------------------+
| Stage 5: LLVM Optimization Passes & LLD Linker         |
|   - mem2reg, InstCombine, IndVarSimplify    |
|   - ThinLTO bitcode linking (.bc) -> Native Binary     |
+--------------------------------------------------------+
```

---

## 3. Core Frontend Data Structures (Illustrative; implementation language undecided)

Implementing `candorc` in Go keeps the compiler codebase concise, strongly typed, and easy to maintain:

```go
package ast

type SourceSpan struct {
    FileID uint32
    Start  uint32
    End    uint32
    Line   uint32
    Column uint32
}

type TypeNode interface {
    Span() SourceSpan
    TypeString() string
}

type StructField struct {
    IsPub      bool
    AlignAttr  uint32 // 0 if default, or power-of-two (e.g., 64)
    Name       string
    Type       TypeNode
    ByteOffset uint64 // Populated during Pass 2a C-ABI layout calculation
}

type StructDecl struct {
    Span       SourceSpan
    IsPub      bool
    IsLinear   bool
    AlignAttr  uint32
    Name       string
    TypeParams []string
    Fields     []StructField
    TotalSize  uint64
    TotalAlign uint64
}

type FnDecl struct {
    Span       SourceSpan
    IsPub      bool
    Name       string
    TypeParams []string
    Params     []ParamDecl
    ReturnType TypeNode // nil implies void
    Body       *BlockStmt
}
```

---

## 4. On-Demand Generic Monomorphization Algorithm

Candor avoids both runtime boxing (Java/C# reference generics) and Turing-complete compile-time evaluation (Zig/C++ template metaprogramming). Generics are lowered via deterministic AST template instantiation:

1. **Template Registration:** During Pass 2a, any `struct`, `impl`, or `fn` with a non-empty `TypeParams` slice (`[T, U]`) is stored in the `GenericTemplateTable` without generating LLVM IR.
2. **Instantiation Key Hashing:** When Pass 2b encounters a concrete instantiation such as `RingQueue[PacketHeader]`, it constructs a canonical mangled key: `_K9RingQueue_I12PacketHeaderE`.
3. **Cache Lookup & Deep Clone:**
   * If `_K9RingQueue_I12PacketHeaderE` exists in `MonomorphizedCache`, return its resolved `TypeID`.
   * Otherwise, deep-clone the `StructDecl` and associated `ImplDecl` AST nodes, substituting every occurrence of `TypeParam("T")` with `ConcreteType("PacketHeader")`.
4. **Layout & Verification:** Run the struct-layout algorithm on the cloned concrete AST and queue it for code generation. Generic *bodies* are type-checked, borrow-checked and linearity-checked **once**, against their declared bounds (`Copy`, `Zero`, `Send`, `Sync`; D-016); instantiation does not re-run those checks.

---

## 5. Concrete Lowering Templates to LLVM IR

### 5.1 Definite Initialization & Defined Wrapping Arithmetic
To guarantee zero Undefined Behavior (RFC 0001), every local is initialized at its declaration (RFC 0003 Rule 5; there is no implicit zero-fill), and integer arithmetic omits LLVM's `nsw`/`nuw` poison flags:

```rust
// Candor Source:
pub fn accumulate(items: const i32[]) -> i32 {
    mut sum: i32 = 0;
    for (x in items) {
        sum += x;
    }
    return sum;
}
```

```llvm
; Lowered LLVM IR (prior to mem2reg optimization):
%slice.i32 = type { ptr, i64 }

define i32 @accumulate(ptr noalias readonly align 4 %items.ptr, i64 %items.len) #0 {   ; no `nocapture`: an elided borrow may be returned
entry:
  %sum = alloca i32, align 4
  store i32 0, ptr %sum, align 4
  %idx = alloca i64, align 8
  store i64 0, ptr %idx, align 8
  br label %loop.cond

loop.cond:
  %i = load i64, ptr %idx, align 8
  %cmp = icmp ult i64 %i, %items.len
  br i1 %cmp, label %loop.body, label %loop.exit

loop.body:
  %elem.ptr = getelementptr inbounds i32, ptr %items.ptr, i64 %i
  %x = load i32, ptr %elem.ptr, align 4
  %cur = load i32, ptr %sum, align 4
  ; Note: plain 'add i32' without 'nsw' guarantees defined 2's complement wraparound
  %next = add i32 %cur, %x
  store i32 %next, ptr %sum, align 4
  %i.next = add i64 %i, 1
  store i64 %i.next, ptr %idx, align 8
  br label %loop.cond

loop.exit:
  %ret.val = load i32, ptr %sum, align 4
  ret i32 %ret.val
}

attributes #0 = { nounwind "frame-pointer"="all" }
```

### 5.2 Register-Pair Error Unions (`Result[T, E]`) and LIFO `defer` Expansion

> **Under review (D-017).** The `{ i64, i32 }` register assignment below is an illustration of a *Candor-internal* convention, not the platform C ABI: it does not match SysV for mixed int/float payloads, returns no sret pointer in `RAX`, and does not apply on Windows x64. The sample IR is also missing `attributes #0` and `declare i32 @close(i32)`, so it would not pass `llvm-as` as written.

Error unions where `sizeof(T) <= 8` map directly to two hardware registers (`RAX` for payload, `RDX` for error tag), and `defer` statements are expanded inline at each scope exit block without C++ `.eh_frame` unwind tables:

```rust
// Candor Source:
pub fn process_fd(raw_fd: i32) -> Result[u64, SysError] {
    defer close(raw_fd);
    if (raw_fd < 0) {
        return SysError.InvalidFd;
    }
    return 4096;
}
```

```llvm
; Lowered LLVM IR:
declare i32 @close(i32)

; Return struct { i64 payload (RAX), i32 error_tag (EDX) }
define { i64, i32 } @process_fd(i32 %raw_fd) #0 {
entry:
  %is_neg = icmp slt i32 %raw_fd, 0
  br i1 %is_neg, label %err.ret, label %ok.ret

err.ret:
  ; LIFO defer expansion on early error return path:
  %0 = call i32 @close(i32 %raw_fd)
  ret { i64, i32 } { i64 0, i32 9 } ; SysError.InvalidFd = 9

ok.ret:
  ; LIFO defer expansion on normal return path:
  %1 = call i32 @close(i32 %raw_fd)
  ret { i64, i32 } { i64 4096, i32 0 } ; tag 0 = success (error enums never use 0, D-018)
}

attributes #0 = { nounwind "frame-pointer"="all" }
```

---

## 6. Zero-Overhead Observability (`perf` / `pprof`) & LLVM PGO

### 6.1 Zero-Overhead Hardware Profiling
Because Candor has no garbage collector or virtual machine, it achieves 100% compatibility with OS kernel sampling profilers (`Linux perf`, `macOS Instruments`, `eBPF profile`) and `pprof` flamegraphs with **zero runtime instrumentation overhead**:

1. **Frame Pointer Preservation:** `candorc` sets the LLVM function attribute `"frame-pointer"="all"` on all generated functions. Every function prologue emits `push rbp; mov rbp, rsp` (3 bytes, $< 0.5\%$ execution impact), allowing hardware PMU interrupts to unwind the call stack in $O(\text{depth})$ kernel time without reading DWARF unwind tables.
2. **DWARF v5 Debug Tables:** `candorc` drives `llvm::DIBuilder` to emit `DICompileUnit`, `DISubprogram`, `DILocalVariable`, and exact line/column locations (`DILocation`), enabling line-by-line CPU and memory attribution in `pprof` and `gdb`/`lldb`.

```bash
# Zero-overhead production profiling workflow:
$ candor build --release
$ perf record -F 999 -g -- ./bin/app
$ perf script | pprof -http=:8080 -
```

### 6.2 Two-Phase Profile-Guided Optimization (PGO)
`candorc` exposes LLVM's native Instrumentation PGO pipeline directly via CLI flags:

1. **Instrumentation Build (`candor build --pgo-gen`):**
   * Inserts `@llvm.instrprof.increment` intrinsics along CFG edges.
   * Links `libclang_rt.profile` to write execution counts to `default.profraw` at process exit.
2. **Profile Merging & Optimized Build (`candor build --pgo-use=app.profdata`):**
   * Invokes `llvm-profdata merge -output=app.profdata default.profraw`.
   * Runs LLVM's `PGOInstrumentationUse` pass, annotating branch instructions with `!prof !{!"branch_weights", i32 2000, i32 1}` metadata.
   * Unlocks aggressive hot-path inlining, cold error-block outlining (moving `catch` blocks out of L1 instruction cache lines), and loop vectorization.