# The Kore Programming Language (`kore-lang`)

**Status:** Draft specification (v0.3.0). **No compiler exists yet.** All RFCs are Draft.  
**Planned backend:** LLVM (implementation language and first backend still undecided; see `DESIGN_REVIEW.md` section C)  
**License:** MIT / Apache-2.0 Dual License  

---

## Overview

**Kore** is a statically typed, ahead-of-time compiled systems programming language aiming at deterministic performance, compile-time memory safety without a garbage collector or lifetime annotations, and direct C interoperability.

### Architectural Summary Matrix

| Dimension | Kore Design Choice | Status |
| :--- | :--- | :--- |
| **Syntax & Surface** | 29 keywords + 3 literal words; $LL(1)$ grammar, **mechanically verified** (`tools/ll1.py`: 0 conflicts) | RFC 0002 v0.3, verified |
| **Modules & Packages** | Headerless 1-directory = 1-module; source packages | RFC 0006 (precompiled `.kpkg` under review) |
| **Polymorphism** | Monomorphized generics with built-in marker bounds (`Copy`, `Zero`, `Send`, `Sync`); no user traits yet | RFC 0003 / 0005 |
| **Memory Model** | Second-class borrows (references and slices) with single-source elision, liveness-based exclusivity, `linear` resources, `defer`/`errdefer`, definite initialization. No lifetime annotations, no GC | RFC 0003 v0.3, walked by hand on 5 programs (no checker yet; see `DESIGN_REVIEW_R2.md`) |
| **Undefined Behavior** | Goal: zero UB in safe code. Open items listed in RFC 0001 | Draft, incomplete |
| **C Interop** | `extern "C"` with platform C ABI at the boundary; Kore-internal convention for `Result[T, E]`, tuples, slices | Direction decided (D-017), RFC text pending |
| **Concurrency** | 1:1 OS threads, `Send`/`Sync` markers. Coroutines deferred | RFC 0004: **open issues** |
| **Tooling** | Planned `kore lsp`, DWARF, PGO | Aspirational; latency and platform claims unmeasured |

---

## Repository Structure

| Document | Title | Focus Area |
| :--- | :--- | :--- |
| `README.md` | Repository Overview | This file |
| `rfc_0001_core_philosophy_and_architecture.md` | RFC 0001: Core Philosophy & UB | Pillars, UB table, accepted trade-offs |
| `rfc_0002_lexical_specification_and_formal_ll_1_grammar.md` | RFC 0002: Lexical Spec & Grammar | Reserved words, lexical rules, precedence, verified EBNF |
| `rfc_0003_type_system_abi_layout_and_memory_safety.md` | RFC 0003: Type System & Memory Safety | Layout, pointers/borrows, the five ownership rules |
| `rfc_0004_concurrency_c_interop_and_hardware_intrinsics.md` | RFC 0004: Concurrency & Intrinsics | Threads, `Mutex`, atomics, `VM`, `Futex` (open issues at top) |
| `rfc_0005_compiler_architecture_llvm_ir_lowering_and_pgo.md` | RFC 0005: Compiler Architecture | Pipeline, monomorphization, LLVM lowering, PGO |
| `rfc_0006_modules_encapsulation_package_manager_and_lsp.md` | RFC 0006: Modules, Packages & LSP | `pub`, `import`, `kore.toml`, LSP design |
| `DECISIONS.md` | Decision log | Every v0.3 decision, alternatives, costs, review-finding status |
| `DESIGN_REVIEW.md` | Design review (v0.2) | Five-lens review of v0.2 and the findings behind v0.3 |
| `DESIGN_REVIEW_R2.md` | Design review, round 2 (v0.3) | Re-review after the fixes: remaining soundness holes, regressions, errors in v0.3 text |
| `LITMUS.md`, `litmus/` | Litmus programs | Five programs that stress-test the rules, with findings |
| `tools/` | Grammar tools | LL(1) checker and a parser generated from the RFC grammar |

---

## Code Showcase

```rust
// File: src/main.kr
import "std/io";
import mem "github.com/maruf03/photon-db/mem";

pub fn main() -> i32 {
    let arena: mem.PageArena = mem.PageArena.init(65536) catch (err) {
        return 1;
    };
    defer arena.destroy();   // arena: Deferred; still borrowable and its Copy fields readable

    io.println("Allocated arena bytes:");
    io.print_u64(arena.capacity as u64);
    return 0;
}
```

More realistic programs (hash map, tokenizer, arena graph, TCP echo server, allocator) are in `litmus/`.

---

## Verifying the Grammar

```bash
python3 tools/ll1.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md                       # conflicts: 0
python3 tools/kparse.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md litmus/*.kr          # 5 x OK
python3 tools/check_keywords.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md              # box, grammar, kparse agree
```

## What Is Not Done

No lexer, parser, type checker, borrow checker, or code generator exists; the semantic rules have been checked by hand only. Not yet specified: concurrency soundness (`Send`/`Sync`, thread lifetimes, memory model), `Result[T, E]` ABI text, sum types, globals, closures, a string library, `std`, precompiled packages. See the open-issue banners in the RFCs and the status table in `DECISIONS.md`.
