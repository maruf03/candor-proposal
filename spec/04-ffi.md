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

- **Allowed in a signature:** scalars, pointers, enums, structs (C layout, by value), and function pointers over those.
- **Not allowed:** slices (`{ptr, len}` is not a C type: pass `s.ptr` and `s.len`), arrays by value, and any struct that contains a slice, directly or through nested structs or arrays. Array *fields* inside a struct are fine (C layout). Empty structs are not allowed either: Candor gives them size 1, C gives them size 0 or 1 depending on the compiler.
- **Strings are not NUL-terminated.** Append the terminator yourself (`"path\0"`) and pass `.ptr`.
- **C return conventions are yours to read.** `mmap` returns `MAP_FAILED`, `read` returns `-1` with `errno`. Check them where you call. `errno` has no accessor; import `__errno_location`.

## 3. Calling Convention

Candor functions use the platform C ABI for scalars, pointers, enums and structs. Slices are passed as a two-field struct, which is how Candor-to-Candor calls work but never appears in an import.

## 4. Not yet

Deferred until a litmus program needs them: variadic imports (`printf`, `open`) and naming or exporting Candor functions under a chosen C symbol (both need a compiler directive), C unions and bitfields, C globals (`stdout`, `environ`), `packed` and `align` layouts (to be added as directives when a program needs exact control), threads calling into Candor.
