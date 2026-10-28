# Kore 5: Modules

One directory is one module. There are no header files, no forward declarations, and no build scripts.

---

## 1. Directory = Module

Every directory containing `.kr` files is a module named after the directory (`src/net/http/*.kr` is module `http`). All files in a directory share one scope: they can use each other's private declarations in any order, with no `import` between them.

A program is a root directory containing `fn main() -> i32`, whose return value is the process exit code.

## 2. Imports

`import` declarations come first in a file:

```
import "std/io";
import "util/hash";
import fast "util/hash_simd";      // optional alias
```

- The string is a path to a directory: relative to the project root, or under the standard-library root (`std/...`). There is no network resolution in v1.
- The qualifier is the last path segment, or the alias. **Every imported name is accessed through its qualifier** (`io.print`, `hash.of(x)`). There is no wildcard import and no unqualified imported name. Names from the file's own module are unqualified.
- The module graph must be acyclic. A cycle is a compile error that prints the cycle.

## 3. Visibility

Everything is private to its directory module unless marked `pub`.

| Item | Without `pub` | With `pub` |
| :--- | :--- | :--- |
| function, `const`, `type`, `enum`, `struct` | visible in this module only | visible to importers (an enum exports all its variants) |
| struct field | accessible in this module only | readable and writable by importers (assignment needs a `mut` binding or a non-`const` pointer) |
| `impl` method | this module only | importers |

`pub impl` is rejected; mark the methods.

- **Construction.** If a `pub struct` has one or more private fields, other modules cannot build it with a struct literal; they call a `pub` constructor function.
- **Layout is independent of visibility:** adding or removing `pub` never changes field order, offsets, or size.
- **Privacy is encapsulation, not safety.** It keeps an API small; it does not protect memory (`spec/03-memory.md` §1).

## 4. Resolution

Compilation of a module is two passes: (1) parse all files and register every type, struct layout and function signature; (2) resolve imports and check function bodies. Because pass 1 completes before pass 2, declarations may appear in any order and mutually refer.

## 5. Building

The compiler builds a directory: `kore build <dir> -o <binary> [--link name]...`, where each `--link` passes `-l<name>` to the C linker. There is no package manager, registry, lock file, manifest, or precompiled-package format in v1; they are deferred (`deferred/packages-and-lsp.md`).
