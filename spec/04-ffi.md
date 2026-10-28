# Candor 4: C Interoperability

Candor is built to sit next to C. Every Candor function is emitted as a C function, every struct as a C struct with the same layout, and every call as a C call. An `extern "C"` import is an ordinary function call with no wrapper, no marshalling, and no runtime. There is no `unsafe` marker: calling C is like calling any other function.

---

## 1. Imports

```
extern "C" {
    fn getpid() -> i32;
    fn read(fd: i32, buf: u8*, n: usize) -> isize;
    fn accept(fd: i32, addr: u8*, len: u32*) -> i32;
    fn qsort(base: u8*, n: usize, size: usize, cmp: fn(const u8*, const u8*) -> i32);
}
```

An `extern` block declares functions; it has no bodies. Names bind to the C symbol of the same name (Candor functions are namespaced by module, imports are not), so choose method and function names that do not collide with an import you use unqualified. Extra libraries are linked with a build option (`spec/05-modules.md` §5).

## 2. Type Mapping

| Candor | C |
| :--- | :--- |
| `i8 i16 i32 i64`, `u8 u16 u32 u64`, `isize`, `usize` | `int8_t`..`int64_t`, `uint8_t`..`uint64_t`, `intptr_t`, `size_t` |
| `f32`, `f64` | `float`, `double` |
| `bool` | `uint8_t` holding 0 or 1 |
| `T*`, `const T*` | `T*`, `const T*`; `null` is `NULL` |
| `enum E : u8` | the backing integer type |
| `struct S` | the same C struct, by value or by pointer |
| `fn(A) -> R` | a C function pointer; a Candor function can be passed as a callback |
| `void` return | `void` |

Rules that follow:

- **C-visible types** are defined recursively. The recursion works on *value types*; where a type may appear is a separate rule (below).
  - scalars (`bool`, integers, floats) and enums;
  - a **pointer** (`T*`, `const T*`) to **any** type: the pointee is opaque to C and need not be C-visible;
  - a function pointer whose parameter types are C-visible (and not `void`) and whose return type is C-visible or `void`;
  - an **array** `T[N]` is C-visible iff `T` is C-visible (including arrays of arrays: `u8[4][4]` is `uint8_t[4][4]` in C, laid out row after row);
  - a struct that has at least one field and **all** of whose fields are C-visible value types (`void` is not a value type, so it cannot be a field);
  - an alias or `distinct` type is C-visible iff its base type is.
- **Where a C-visible type may appear in a signature.** A parameter may be a scalar, enum, pointer, function pointer, or struct. A return type may be any of those or `void`; this holds for callbacks too (`fn() -> void`, `fn(i32) -> i32`). **Arrays are never parameters or return types**, only struct fields: C would decay them to pointers, so `fn consume(m: u8[4])` is rejected while `struct Matrix { cells: u8[4][4]; }` passed by value is fine.
- **Not C-visible**, and therefore not allowed by value anywhere in a signature: slices (`{ptr, len}` is not a C type: pass `s.ptr` and `s.len`); **empty structs** (Candor gives them size 1 through a hidden byte, C gives 0 or 1); and any struct or array that contains a non-C-visible type at any depth, so `struct Box { e: Empty; x: u8; }` and `struct S { s: u8[]; }` are both rejected. Pointers *to* such types are still fine.
- **Strings are not NUL-terminated.** Append the terminator yourself (`"path\0"`) and pass `.ptr`.
- **C return conventions are yours to read.** `mmap` returns `MAP_FAILED`, `read` returns `-1` with `errno`. Check them where you call. `errno` has no accessor; import `__errno_location`.

## 3. Calling Convention

Candor functions use the platform C ABI for scalars, pointers, enums and structs. Slices are passed as a two-field struct, which is how Candor-to-Candor calls work but never appears in an import.

## 4. Not yet

Deferred until a litmus program needs them: variadic imports (`printf`, `open`) and naming or exporting Candor functions under a chosen C symbol (both need a compiler directive), C unions and bitfields, C globals (`stdout`, `environ`), `packed` and `align` layouts (to be added as directives when a program needs exact control), threads calling into Candor.
