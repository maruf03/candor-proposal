# Kore 4: C Interoperability

Kore calls C directly: an `extern "C"` import compiles to an ordinary C call with no wrapper, no marshalling, and no runtime. Scope for v1 is deliberately narrow: **importing C functions with scalar and pointer signatures.** Everything else is deferred (§5).

---

## 1. Imports

```
extern "C" {
    fn getpid() -> i32;
    fn read(fd: i32, buf: u8*, n: usize) -> isize;
    fn accept(fd: i32, addr: ?u8*, len: ?u32*) -> i32;
}
```

An `extern` block declares functions; it has no bodies. Names bind to the C symbol of the same name (functions in Kore modules are namespaced, imports are not), so choose method and function names that do not collide with an import you use unqualified. Linking extra libraries is a command-line option of the build (`spec/05-modules.md` §5).

## 2. Calling C is `unsafe`

Every call to an imported function must be wrapped in `unsafe(...)`:

```
let pid = unsafe(getpid());
unsafe(close(raw));
```

There is no way to mark an import as safe: whether a C function is memory-safe cannot be checked, and a safe wrapper function is one line. Put the `unsafe(...)` in a small Kore wrapper that returns a `Result` and let the rest of the program stay in safe code (`litmus/04_echo_server.kr`).

## 3. Type Mapping

An import's parameter and return types are limited to **C-visible** types:

| Kore | C |
| :--- | :--- |
| `i8 i16 i32 i64`, `u8 u16 u32 u64`, `isize`, `usize` | `int8_t`..`int64_t`, `uint8_t`..`uint64_t`, `intptr_t`, `size_t` |
| `f32`, `f64` | `float`, `double` |
| `bool` | `uint8_t` holding 0 or 1 (never pass a C `_Bool` you did not produce) |
| `T*` | non-null `T*` |
| `?T*` | `T*` that may be null |
| `const T*` | `const T*` |
| `void` return | `void` |

Rules that follow:

- **Nullable C pointers are `?T*`.** If C may return or accept `NULL`, say so in the signature. Declaring it `T*` is a lie that the compiler cannot detect.
- **Enums are not allowed** in import signatures (C enums are integers, and an out-of-range value would be an invalid Kore enum). Use the integer type.
- **Slices, `Buf`, `Result`, structs, arrays, and function pointers are not allowed** in import signatures. Pass `s.ptr` and `s.len` for a slice. Structs by value need ABI classification and are deferred.
- **Strings are not NUL-terminated.** Append the terminator yourself (`"path\0"`) and pass `.ptr`.
- **C return conventions are yours to translate.** `mmap` returns `MAP_FAILED` (`-1`), not null; `read` returns `-1` with `errno`. Wrap immediately and return a `Result`. `errno` has no accessor in v1 (call `__errno_location` yourself).

## 4. Calling Convention

Imports use the platform C ABI. Kore-to-Kore calls use a compiler-chosen convention for `Result`, slices, and `Buf`, which never appears at a C boundary. Because Kore functions cannot be exported to C in v1 (§5), there is nothing to match in the other direction.

## 5. Not in v1

Deferred until a litmus program needs them (`docs/decisions.md`, D-03): exporting Kore functions with the C ABI, callbacks (C-ABI function pointers), variadic imports (`printf`, `open`), C unions and bitfields, by-value structs, C globals (`stdout`, `environ`), `packed` and `align` layouts, threads calling into Kore.
