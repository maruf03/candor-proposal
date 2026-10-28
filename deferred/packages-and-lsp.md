> **DEFERRED, NOT PART OF CANDOR.** Draft package manager (`candor.toml`, `.kpkg`, `api.cn.d` stubs) and language server. The module rules that are in v1 are in `spec/05-modules.md`. Known problems: opaque private-field stubs break by-value ABI classification and hide linearity, LLVM bitcode is not stable across versions so it is not an IP-protection mechanism, and the 5 ms language-server latency was never measured.
> References to "RFC 000N", `DESIGN_REVIEW*.md`, and `DECISIONS.md` point to v0.3 documents recoverable from git (snapshot commit `1f54205`). Code samples use draft syntax and are not guaranteed to parse or typecheck against `spec/`. Kept for the ideas; see `docs/decisions.md` D-21 for when this returns.

# RFC 0006: Module System, Encapsulation, Hybrid Package Management, and Language Server Protocol (LSP)

- **RFC Number:** 0006
- **Title:** Module System, Encapsulation, Hybrid Package Management, and Language Server Protocol (LSP)
- **Author:** Language Design Working Group
- **Status:** Draft (§2.2 example and keyword count corrected 2026-10-28; **§4 precompiled `.kpkg` is under review**: the `api.cn.d` opaque-byte stubs break by-value ABI classification and `Send`/`Sync` derivation, and LLVM bitcode is not stable across LLVM versions; see `DESIGN_REVIEW.md` A9, F3)
- **Type:** Standards Track (Tooling, Modules & Ecosystem)
- **Created:** 2026-10-28

---

## 1. Abstract

This RFC specifies Candor's module encapsulation rules, namespace resolution, hybrid source and precompiled binary package manager (`.kpkg`), declarative project configuration (`candor.toml`), and built-in Language Server Protocol (`candor lsp`) architecture. By introducing only two keywords (`pub` and `import`; with RFC 0002 v0.3 the vocabulary is **29 keywords plus 3 literal words**), Candor supports large-scale modular software engineering and sub-5ms IDE feedback without header files, complex build scripts, or macro preprocessors.

---

## 2. Encapsulation & Visibility (`pub`)

### 2.1 Module-Private by Default
Every top-level declaration (`fn`, `struct`, `linear struct`, `enum`, `type`, `const`, `extern`) and every `struct` field is **private to its defining module (directory)** by default. Adding the `pub` modifier exports the symbol to importing modules.

| Construct | Default Visibility (No `pub`) | Exported Visibility (`pub`) |
| :--- | :--- | :--- |
| **`fn` / `const` / `type`** | Callable/visible only within `.cn` files in the same directory. | Callable/visible to any module that imports this module. |
| **`struct` / `linear struct`** | Type name and all fields are private to the defining module. | Type name is public; only fields explicitly marked `pub` are accessible externally. |
| **`struct` Fields** | Accessible only inside the defining module and its `impl` blocks. | Readable and writable by external modules (subject to `&mut` exclusivity). |
| **`enum`** | Variants are visible only within the defining module. | Type name and all variants are public. |

### 2.2 Opaque Value Structs & C-ABI Layout Invariance
A core requirement of Candor is that encapsulation **never** alters hardware representation:
1. **Layout Invariance:** Adding or removing `pub` on a struct field never changes field ordering, byte offsets, alignment, or tail padding. A struct's layout follows the exact C ABI specification in RFC 0003 regardless of visibility modifiers.
2. **Literal Construction Rule:** If a `pub struct` or `pub linear struct` contains **one or more private fields**, external modules are forbidden from constructing it via a raw struct literal (`Buffer{ ... }`). External callers must invoke an exported constructor function (e.g., `Buffer.allocate(4096)`).
3. **Protection of `linear` Invariants:** Because external modules cannot read, mutate, or overwrite private pointers inside a `pub linear struct`, resource lifecycle invariants are enforced at the module boundary with zero heap indirection or `pimpl` pointer overhead.

```rust
// File: src/mem/arena.cn (Module: mem)
pub linear struct PageArena {
    pub capacity: usize; // Publicly readable metadata
    pub used: usize;     // Publicly readable metadata
    base_ptr: u8*;       // PRIVATE: external modules cannot corrupt or free base_ptr
}

pub enum VMError : i32 { OutOfMemory = 1 }

impl PageArena {
    pub fn init(size: usize) -> Result[PageArena, VMError] {
        let raw: ?u8* = VM.map(size, VMProtect.ReadWrite, VMFlags.Anonymous);
        if (raw == null) {
            return VMError.OutOfMemory;
        }
        return PageArena{
            capacity: size,
            used: 0,
            base_ptr: raw,
        };
    }

    pub fn destroy(self: PageArena) {
        // Destructuring consumes `self` (RFC 0003 Rule 3); all remaining fields are Copy.
        let PageArena{ capacity, base_ptr, .. } = self;
        unsafe { VM.unmap(base_ptr, capacity); }
    }
}
```

---

## 3. Headerless Module & Namespace System (`import`)

### 3.1 The "1 Directory = 1 Module" Rule
Candor eliminates C's textual `#include` preprocessor headers and Rust's explicit file-tree `mod foo;` boilerplate:
* **Directory Mapping:** Every directory containing `.cn` source files constitutes a single compilation module named after the directory (e.g., `src/net/http/*.cn` $\rightarrow$ module `http`).
* **Intra-Module Sharing:** All `.cn` files within the same directory share the same module scope. They can reference each other's private structs, constants, and functions in any order without `import` statements or forward declarations.

### 3.2 Mandatory Qualified Imports (Zero Namespace Pollution)
All `import` declarations appear at the top of a `.cn` file before top-level declarations:

```rust
import "std/io";
import "std/sync";
import "crypto/sha256";
import http_client "github.com/maruf03/candor-net/http"; // Explicit module alias
```

To guarantee code readability without an IDE ("Zero Magic" Pillar 1):
* **No Wildcard Imports:** Candor has no `import *` or `using namespace` construct.
* **Mandatory Prefix Qualification:** Every symbol imported from another module **must** be accessed through its module qualifier (`io.File`, `sha256.sum(data)`, `http_client.get(url)`). Local symbols defined within the current module are accessed unqualified.
* **Acyclic Module Graph:** The module dependency graph must be a strict Directed Acyclic Graph (DAG). Cyclic imports between directories are rejected at compile time with the exact cycle path printed in diagnostics.

### 3.3 Two-Pass Order-Independent Symbol Resolution
To allow functions and types within a module to reference each other without C-style forward declarations while preserving $LL(1)$ parsing speed, the compiler processes each module in two lightweight passes:

```
+-------------------------------------------------------------------------+
|                  TWO-PASS MODULE RESOLUTION PIPELINE                    |
+-------------------------------------------------------------------------+
| Pass 1: Parallel LL(1) Parsing + Top-Level Signature Indexing           |
|   - Parses each .cn file in the module independently into ASTs          |
|   - Registers all struct/enum/type names and fn signatures in SymTab    |
|   - Validates acyclic value-struct composition and computes C-ABI sizes |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Pass 2: Function Body Semantic Analysis & Linear CFG Verification       |
|   - Resolves qualified imports against dependency Module Symbol Tables  |
|   - Type-checks statements/expressions inside fn and impl bodies        |
|   - Runs Monomorphization, Reference Escape, and Linear Liveness passes |
+-------------------------------------------------------------------------+
```

---

## 4. Hybrid Source & Precompiled Package Management (`.kpkg`)

Candor's package manager supports both **decentralized Git source repositories** (GitHub, GitLab, self-hosted Git) and **precompiled binary packages (`.kpkg`)** for proprietary libraries or pre-built C-wrapped SDKs.

### 4.1 Decentralized Naming & Optional Static Index
* **Direct Repository URLs:** Packages are identified by their canonical repository path (`"github.com/org/repo"`), versioned via Git semantic version tags (`v1.2.0`), and verified via SHA-256 content hashes in `candor.lock`.
* **Static Registry Shorthands:** For common community packages, `candor add <name>` queries a static Git-hosted index (`github.com/candor-lang/registry`) where each package entry is a static JSON file mapping short names to canonical Git URLs and release public keys.

### 4.2 Dual Distribution Architecture: Source vs. Precompiled `.kpkg`

| Feature | Source Distribution (Default) | Precompiled Binary Archive (`.kpkg`) |
| :--- | :--- | :--- |
| **Distribution Artifact** | Git tag/commit checkout of `.cn` source files. | `.kpkg` (`tar.zst`) attached to GitHub/GitLab Releases. |
| **Contents** | `candor.toml` + `src/**/*.cn` | `candor.toml` + `api.cn.d` (Interface Stub) + `lib<name>.bc` / `lib<name>.a` |
| **Cross-Package Inlining** | Full AST monomorphization & LLVM inlining. | Full LLVM Link-Time Optimization (LTO) when linked against `.bc` bitcode! |
| **Intellectual Property** | Open source text. | Implementation bodies stripped; private struct fields obfuscated. |

### 4.3 The Compiler-Generated Interface Stub (`api.cn.d`)
When a package author runs `candor package --precompiled`, the compiler emits an interface stub file (`api.cn.d`) alongside the compiled LLVM bitcode (`lib<name>.bc`) and native static library (`lib<name>.a`).

`api.cn.d` solves the hardest problem in compiled systems languages without C headers:
1. **Exact C-ABI Sizing with Private Field Obfuscation:** If a `pub struct` contains private fields, the compiler replaces contiguous spans of private fields in `api.cn.d` with an opaque byte array annotated with the exact alignment (`[align(A)] _opaque_0: u8[N];`). Downstream compilers compute the exact same `sizeof` and `alignof` for stack allocation and C-ABI passing without seeing internal field names or types.
2. **Concrete Function Stripping:** Non-generic `pub fn` declarations are emitted as bodyless signatures (`pub fn compress(src: const u8[], dst: u8[]) -> Result[usize, Error];`).
3. **Generic Template Preservation:** Because generics are monomorphized on demand, generic `pub fn name[T]` declarations and `impl[T]` method bodies retain their type-checked AST in `api.cn.d`. (v0.2 wrote `pub fn[T]` and `pub impl[T]`, neither of which is valid syntax.)

```rust
// Auto-generated file: candor_zstd/api.cn.d
pub linear struct ZstdEncoder {
    pub compression_level: i32;
    [align(8)] _opaque_private: u8[120]; // Total struct size = 128 bytes, align = 8 bytes
}

impl ZstdEncoder {
    pub fn init(level: i32) -> Result[ZstdEncoder, ZstdError];
    pub fn encode_chunk(self: &mut ZstdEncoder, input: const u8[], output: u8[]) -> Result[usize, ZstdError];
    pub fn close(self: ZstdEncoder);
}

// Generic helper retains body so caller can instantiate for any type T
pub fn encode_struct[T](enc: &mut ZstdEncoder, item: &const T, out: u8[]) -> Result[usize, ZstdError] {
    unsafe {
        let raw_bytes: const u8[] = slice_from_raw[u8](item as (const u8*), size_of(T));   // illustrative; reading padding is an open issue
        return enc.encode_chunk(raw_bytes, out);
    }
}
```

---

## 5. Declarative Project Configuration (`candor.toml` & `candor.lock`)

Candor bans imperative build scripts (no `build.rs`, no `CMakeLists.txt`). All build targets, dependencies, C library links, and PGO settings are declared in `candor.toml`.

```toml
[package]
name = "photon-db"
version = "0.2.0"
candor_version = "0.3"
entry = "src/main.cn"

[build]
target = "native"                  # Or cross-compile: "x86_64-linux-gnu", "aarch64-macos"
opt_level = 3                      # 0 = Debug, 2 = Release, 3 = Max Speed
frame_pointers = true              # Enforces -fno-omit-frame-pointer for zero-cost perf/pprof
lto = "thin"                       # "off", "thin", or "full" (inlines across .cn and .bc packages)
pgo_use = "profiles/prod.profdata" # Optional LLVM PGO profile path

[dependencies]
"github.com/maruf03/candor-uring" = { version = "v0.4.1" }
"github.com/maruf03/candor-zstd"  = { version = "v1.1.0", artifact = "precompiled" }

[c_libraries]
sqlite3 = { pkg_config = "sqlite3", link = "static" }
m       = { link = "dynamic" }
pthread = { link = "dynamic" }
```

### Standard CLI Workflow
* `candor build` — Resolves the module DAG, compiles `.cn` modules to LLVM IR, links `.bc`/`.a` dependencies and C libraries via `lld`, and outputs a single native binary.
* `candor fetch` — Downloads dependencies into `~/.candor/pkg/` and writes cryptographic SHA-256 digests to `candor.lock`.
* `candor package --precompiled` — Emits `dist/<name>-<target>.kpkg` containing `api.cn.d`, `lib<name>.bc`, and `lib<name>.a`.
* `candor lsp` — Starts the Language Server Protocol daemon over standard input/output (`stdio`).

---

## 6. Fault-Tolerant Language Server (`candor lsp`) Architecture

Traditional batch compilers abort on the first syntax or type error, making them unusable for live IDE feedback. Candor's frontend is architected so the exact same parser and semantic analyzer power both `candor build` and `candor lsp` with **$<$ 5 ms latency**.

### 6.1 Keyword-Anchored $LL(1)$ Error Recovery
Because Candor's keyword-anchored grammar requires every statement to terminate with `;` or `}` and every top-level item to begin with an anchor keyword (`pub`, `fn`, `struct`, `linear`, `enum`, `impl`, `type`, `extern`, `const`), the parser recovers from incomplete user edits deterministically:

1. **Statement-Level Synchronization:** If an expression inside a function body is incomplete (e.g., the user just typed `let x = ptr.`), the parser records a `Diagnostic`, consumes tokens until the next `;` or `}`, and emits a synthetic `Expr::Poison` node.
2. **Poison Type Suppression:** The semantic analyzer assigns `Type::Poison` to `Expr::Poison`. Any downstream expression operating on `Type::Poison` silently propagates `Type::Poison` without emitting secondary cascading error messages.
3. **Top-Level Synchronization:** If a function signature is malformed, the parser skips ahead to the next top-level keyword anchor (`pub`, `fn`, `struct`, etc.), preserving valid ASTs and symbol definitions for the rest of the file.

### 6.2 In-Memory Workspace Index & Symbol Map
During Pass 1 and Pass 2, the semantic analyzer populates an interval tree per file mapping byte offsets (`SourceSpan`) to resolved `SymbolRecord` entries:

```go
type SymbolRecord struct {
    Name          string
    Kind          SymbolKind // Fn, Struct, LinearStruct, Field, LocalVar, Param
    ResolvedType  Type
    DefSpan       SourceSpan
    DocComment    string
    // C-ABI Layout Metadata (for Structs and Fields)
    ByteSize      uint64
    ByteAlign     uint64
    FieldOffset   uint64
    TailPadding   uint64
    // Ownership & Concurrency Metadata
    LinearState   LinearStatus // Unconsumed, Consumed, Deferred, ErrDeferred
    IsSend        bool
    IsSync        bool
}
```

### 6.3 Core LSP Capabilities Matrix

| LSP Method | Candor Compiler Pass Executed | IDE Feature Delivered |
| :--- | :--- | :--- |
| **`textDocument/didChange`** | Updates in-memory `VFS` buffer; re-runs Lexer + Parser + Sema on current module only ($< 5\text{ ms}$). | Real-time diagnostics for syntax errors, type mismatches, **reference escapes**, and **unconsumed `linear` leaks**. |
| **`textDocument/hover`** | $O(\log N)$ lookup in file's `SymbolRecord` interval tree. | Displays function signature, `Send`/`Sync` status, and **exact C-ABI struct size, alignment, field byte offsets, and hidden padding**. |
| **`textDocument/definition`** | Reads `SymbolRecord.DefSpan` across local `.cn` files or `.kpkg` `api.cn.d` stubs. | Instant jump-to-definition across source modules and precompiled packages. |
| **`textDocument/completion`** | Evaluates receiver type `T` prior to `.` or module name prior to `.`. | Lists visible `pub` fields, `impl` methods on `T`, or exported symbols from an imported module. |