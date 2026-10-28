# Candor 2: Types and Semantics

Primitive and compound types, conversions, arithmetic, pointers and slices, enums, generics, constants, and the prelude. Memory conventions (allocation, `defer`, initialization) are in `spec/03-memory.md`.

**Defined behavior.** Arithmetic, shifts, conversions, indexing of arrays and slices, and initialization each have one defined result in every build mode, or abort. *Abort* means the process terminates immediately (`trap()`); no `defer` runs. Pointer misuse is **not** defined: it is the programmer's job, as in C (`spec/03-memory.md` §1).

---

## 1. Types at a Glance

| Category | Types |
| :--- | :--- |
| Integers | `i8 i16 i32 i64 isize u8 u16 u32 u64 usize` |
| Floats | `f32 f64` |
| Other scalars | `bool` (1 byte), `void` |
| Pointers | `T*`, `const T*`. Any pointer may be `null`. |
| Slices | `T[]`, `const T[]`: a `{ptr, len}` pair, a plain value |
| Arrays | `T[N]` (value type, `N` a literal or `const`) |
| Structs | `struct S { ... }` (C layout) |
| Enums | `enum E : u8 { A, B }` (fieldless) |
| Function pointers | `fn(A, B) -> R` (C function pointers) |
| Aliases | `type Name = T;`, `type Id = distinct u32;` |

**Every type is copied by value**, as in C. There are no move rules, no ownership, and no marker bounds. A pointer or slice copy aliases; the programmer decides who frees what.

---

## 2. Primitive Types

- `i8..i64`, `u8..u64` are two's-complement integers of that width; `isize`/`usize` are pointer-sized.
- `f32`/`f64` follow IEEE 754 with default rounding, no fast-math. NaN compares unordered (`==` false, `!=` true).
- `bool` is `true` or `false`. Conditions (`if`, `while`) must be `bool`: there is no truthiness.
- `void` is the type of a function that returns nothing.

---

## 3. Literals and Conversions

**Integer literals** take the type the context gives them: the declared type of a `let`/`const`, the parameter type of a call, or the other operand of a binary operator. With no context they are `i32`. A literal that does not fit is a compile error; a leading `-` is checked with the literal (`-128: i8` is valid).

**No implicit numeric conversion.** `i32 + i64` is a type error. The implicit conversions that exist, all lossless:

| From | To |
| :--- | :--- |
| `T[]` | `const T[]` |
| `T*` | `const T*` |
| `null` | any pointer type |

**`x as T`** is the only explicit conversion:

| Conversion | Behavior |
| :--- | :--- |
| integer to integer | widening extends by the *source* type's signedness (so `-1 as usize` is all ones); narrowing truncates |
| integer to float | nearest value |
| float to integer | **saturates**; NaN becomes 0 |
| float to float | nearest value |
| `bool` to integer | 0 or 1 |
| integer to `bool` | not allowed (write `x != 0`) |
| enum to integer | the variant's value |
| integer to enum | allowed; an exhaustive `switch` over an out-of-range value aborts (§5) |
| `distinct` type to or from its base | free; other conversions go through the base type's rules |
| pointer to pointer, pointer to integer, integer to pointer | allowed, no check: the address is reinterpreted |
| `const T*` to `T*` | allowed (like a C cast); writing through it is the programmer's problem |

---

## 4. Arithmetic, Pointers, Operators

- **Overflow aborts.** `+`, `-`, `*` and unary `-` abort on overflow at every width, signed and unsigned, in every build mode. For deliberate wraparound use `wrapping_add`, `wrapping_sub`, `wrapping_mul` (§8).
- **Division.** `/` and `%` on integers abort when the divisor is `0`, and when a signed `MIN` is divided by `-1`, at every width. A constant zero divisor is a compile error. Float `/` is IEEE, never aborts.
- **Shifts.** `<<` and `>>` convert the shift amount to the operand's type (truncating), then mask it to `N - 1` for an `N`-bit operand. `>>` is arithmetic for signed, logical for unsigned operands. `<<` operates on the bit pattern: it shifts the two's-complement representation and discards bits shifted out, never aborting, for signed operands too (`-1 << 1` is `-2`; `1_i8 << 7` is `-128`). A constant amount `>= N` is a compile error.
- **Pointers** are single-object: `*p`, `p.f` (means `(*p).f`), `&x`, comparison with `==`/`!=` and `as`. There is **no pointer arithmetic and no pointer indexing**: `p + n`, `p - q` and `p[i]` are errors. To reach many objects, hold a **slice** (`T[]`) and index it (bounds-checked); `&s[i]` is the address of an element, `s[off..]` drops a prefix, and `slice(p, n)` is the single unchecked entry from a pointer to a slice. For address math (aligning, offsets), cast to `usize`, compute, and cast back. The arithmetic is ordinary `usize` arithmetic, so `+ - *` still abort on overflow; write `wrapping_add`, `wrapping_sub` or `wrapping_mul` where wraparound is intended. `&x` is the address of a variable, field or element and has type `T*`; `&` of an rvalue is an error.
- **Comparison** is non-associative; operands must have the same type. Equality on structs and arrays is not defined (compare fields); scalars, enums and pointers compare with `==` and `!=`.
- **Evaluation order** is left to right for operands and call arguments. `&&` and `||` short-circuit.
- **Bounds.** Indexing an array or a slice aborts unless `i < len`. Slicing `x[lo..hi]` of an array or slice aborts unless `lo <= hi <= len` (so `x[len..len]` is a valid empty slice). The result's pointer is the base pointer advanced by `lo`; when `lo` is 0 it is the base pointer itself, so slicing an empty slice with a null pointer (`slice(null, 0)[..]`) is valid.

---

## 5. Structs, Enums, Arrays, Slices

**Structs** use the platform C layout algorithm so they can cross into C unchanged: each field is placed at the next offset aligned to its natural alignment, and the total size is rounded up to the struct's alignment. Empty structs have size 1 (the compiler adds one hidden byte; see `spec/06-compiler.md` §4), so they are not C-visible. Visibility (`pub`) never changes layout. Padding bytes are unspecified. Every struct literal names every field. Struct values are passed and returned by value with the C calling convention.

**Enums** are fieldless. Variants are numbered from 0 unless given a value; the backing type defaults to `i32` (`enum E : u8 { ... }` chooses another). A `switch` over an enum must name every variant or have an `else:` arm. Each `case` arm is written `case .Variant:` or `case Enum.Variant:`. If an enum value outside its variants is observed, an exhaustive `switch` aborts.

**Arrays** `T[N]` are values: they live where declared and are copied on assignment, passed by value, and returned by value. Literals are `[a, b, c]` and `[v; n]` (`v` repeated `n` times). Unlike C, an array parameter never decays to a pointer; pass `&a[0]` or a slice for that. A `T[N]` field inside a struct has C layout. (Lowering: `spec/06-compiler.md` §4.)

**Slices** `T[]` / `const T[]` are `{ptr, len}` values with fields `.ptr` (a pointer) and `.len` (`usize`). They are ordinary values: copy them, store them in structs, return them. Nothing tracks what they point at (a slice of a local array dangles after the function returns, as in C). Build one with `a[lo..hi]` (array or slice), `a[..]`, a string literal, or `slice(p, n)` (§8). String literals have type `const u8[]`; char literals have type `u8`.

**Methods and calls.** `x.m(args)` calls `m` declared in `impl` of `x`'s type with `x` as first argument. If `m`'s first parameter is `self: T*` and `x` is a `T` variable, `&x` is passed. If `x` is already a `T*`, it is passed as is. These two conveniences, and `.` on pointers, are the only implicit steps in the language. If a struct field has function-pointer type, `self.hash(key)` calls it; a struct may not have a field and a method of the same name, so this is never ambiguous.

---

## 6. Generics

Type parameters are written `[T]`. Generic structs, functions, aliases and `impl` blocks are **monomorphized**: one copy per distinct argument list, with no runtime cost. A generic *body* is checked at each instantiation, like a C++ template; an error carries the instantiation site. Without traits, a generic cannot use operators on `T` unless every instantiation supports them; pass comparison and hashing as function pointers when a body must stay type-agnostic (`litmus/01_hashmap.cn`).

---

## 7. Compile-Time Constants

`const NAME: T = expr;` declares a constant (top level or in a function). The initializer is a constant expression: literals, other constants, arithmetic, `size_of`, array literals, and string literals. A `const` of type `const u8[]` is static data.

---

## 8. Prelude

These names are available everywhere without `import`. They are ordinary identifiers (not keywords) and can be shadowed. All are compiler intrinsics, because nothing else in the language can express them. (`size_of(T)` is not in this table: it is a keyword form, `spec/01-syntax.md` §2.)

| Intrinsic | Signature | Notes |
| :--- | :--- | :--- |
| `slice(p, n)` | `(T*, usize) -> T[]` | builds a slice from a pointer and a length; no check |
| `trap()` | never returns | abort |
| `wrapping_add/sub/mul(a, b)` | `(T, T) -> T` | `T` an integer type; wraps modulo 2^N |

There is no allocator, container, string, or error type in the prelude. Allocation is an ordinary `extern "C"` call (`malloc`, `free`) or a user-written allocator (`spec/03-memory.md` §3, `litmus/05_allocator_vec.cn`).
