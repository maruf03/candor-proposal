# Kore 2: Types and Semantics

Primitive and compound types, conversions, arithmetic, enums, generics, errors, and the prelude. Memory rules (borrows, linear values, `defer`, initialization, `unsafe`) are in `spec/03-memory.md`.

**Defined behavior.** Every operation in this chapter has one defined result in every build mode, or aborts. There is no undefined behavior in safe code. *Abort* means the process terminates immediately (`trap()`); no `defer` runs.

---

## 1. Types at a Glance

| Category | Types | Copy? |
| :--- | :--- | :--- |
| Integers | `i8 i16 i32 i64 isize u8 u16 u32 u64 usize` | yes |
| Floats | `f32 f64` | yes |
| Other scalars | `bool` (1 byte), `void` | yes |
| Raw pointers | `T*`, `?T*` (nullable), `const T*` | yes |
| Enums | `enum E : u8 { A, B }` (fieldless) | yes |
| Arrays | `T[N]` (value type, `N` a literal or `const`) | iff `T` is |
| Structs | `struct S { ... }` | iff all fields are, and not `linear` |
| Borrow types | `&const T`, `&mut T`, `const T[]`, `T[]` (slices) | no (see `spec/03-memory.md` §2) |
| Linear structs | `linear struct R { ... }`, and anything containing one | no |
| Function pointers | `fn(A, B) -> R` | yes |
| Aliases | `type Name = T;`, `type Id = distinct u32;` | as the base |
| Prelude | `Result[T, E]`, `Buf[T]` | `Result` iff `T` is; `Buf` never |

**`Copy`** is the only marker. It is derived, never declared: scalars, raw pointers, enums, function pointers, and arrays, structs and `Result`s of `Copy` components are `Copy` unless declared `linear`. A value of a `Copy` type may be used any number of times; any other value is **moved** by a by-value use.

---

## 2. Primitive Types

- `i8..i64`, `u8..u64` are two's-complement integers of that width; `isize`/`usize` are pointer-sized.
- `f32`/`f64` follow IEEE 754 with default rounding, no fast-math. NaN compares unordered (`==` false, `!=` true).
- `bool` is `true` or `false`. Conditions (`if`, `while`) must be `bool`: there is no truthiness.
- `void` is the type of a function that returns nothing; it may appear as `Result[void, E]`.

---

## 3. Literals and Conversions

**Integer literals** take the type the context gives them: the declared type of a `let`/`const`, the parameter type of a call, or the other operand of a binary operator. With no context they are `i32`. A literal that does not fit is a compile error; a leading `-` is checked with the literal (`-128: i8` is valid).

**No implicit numeric conversion.** `i32 + i64` is a type error. The implicit conversions that exist, all lossless:

| From | To | Where |
| :--- | :--- | :--- |
| `T[]` | `const T[]` | any |
| `&mut T` | `&const T` | call arguments |
| `T` | `Result[T, E]` | `return` operand |
| `E` | `Result[T, E]` | `return` operand (the error) |
| `T*` | `?T*` | any |

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
| integer to enum | **not allowed** in v1 |
| `distinct` type to or from its base | free; other conversions go through the base type's rules |
| pointer to pointer, integer to pointer, pointer to integer | only inside `unsafe(...)` |

---

## 4. Arithmetic and Operators

- **Overflow aborts.** `+`, `-`, `*` and unary `-` abort on overflow at every width, signed and unsigned, in every build mode. For deliberate wraparound use the intrinsics `wrapping_add`, `wrapping_sub`, `wrapping_mul` (§9).
- **Division.** `/` and `%` on integers abort when the divisor is `0`, and when a signed `MIN` is divided by `-1`, at every width. A constant zero divisor is a compile error. Float `/` is IEEE (infinities, NaN), never aborts.
- **Shifts.** `<<` and `>>` convert the shift amount to the operand's type (truncating), then mask it to `N - 1` for an `N`-bit operand. `>>` is arithmetic for signed, logical for unsigned operands. A constant amount `>= N` is a compile error.
- **Comparison** is non-associative; operands must have the same type. Equality on structs and arrays is not defined (compare fields); scalars, enums and raw pointers compare with `==` and `!=`.
- **Evaluation order** is left to right for operands and call arguments. `&&` and `||` short-circuit. Argument *values* are fully evaluated before the call begins.
- **Bounds.** Indexing an array, slice, or `Buf` aborts if the index is out of range. Slicing `x[lo..hi]` aborts unless `lo <= hi <= len`.

---

## 5. Structs, Enums, Arrays

**Structs** use the platform C layout algorithm so they can cross into C unchanged: each field is placed at the next offset aligned to its natural alignment, and the total size is rounded up to the struct's alignment. Empty structs have size 1. Visibility (`pub`) never changes layout. Padding bytes are unspecified and unobservable in safe code.

Types that are **not C-visible** (slices, `Result`, `Buf`, and any struct containing one) have a compiler-chosen layout and cannot appear in `extern` signatures.

**Enums** are fieldless. Variants are numbered from 0 unless given a value; the backing type defaults to `i32` (`enum E : u8 { ... }` chooses another). A `switch` over an enum must name every variant or have an `else:` arm. Each `case` arm is written `case .Variant:` or `case Enum.Variant:`. If an enum value outside its variants is ever observed (through C), an exhaustive `switch` aborts instead of falling into an undefined default.

**Arrays** `T[N]` are values: they live where declared and are copied when `T` is `Copy`. Literals are `[a, b, c]` and `[v; n]` (the value `v` repeated `n` times, `v` must be `Copy`). Pass an array's contents to a function by slicing: `f(buf[..])`.

**Slices** `T[]` / `const T[]` are borrowed `{ptr, len}` views with fields `.len` and `.ptr` (a raw pointer). They are borrow types and follow `spec/03-memory.md` §2. String literals have type `const u8[]`; char literals have type `u8`.

**Calling through a function-pointer field.** If `hash` is a field of function-pointer type, `self.hash(key)` calls it. A struct may not have a field and a method of the same name, so this is never ambiguous.

---

## 6. Generics

Type parameters are written `[T]`, optionally bounded: `[T: Copy]`. Generic structs, functions, aliases and `impl` blocks are **monomorphized**: one copy per distinct argument list, with no runtime cost.

A generic *body* is checked **once**, against its bounds, not once per instantiation (so errors appear in the generic, not at the use site). Inside the body:

- an **unbounded** `T` may be linear: values of type `T` can only be moved, never copied, compared, or used in arithmetic;
- a `T: Copy` value can be copied, but still has no operators: pass comparison and hashing as function pointers (see `litmus/01_hashmap.kr`).

A borrow type can never be a generic argument (`Buf[&const u8]` is rejected).

---

## 7. Errors: `Result`, `try`, `catch`

`Result[T, E]` is the prelude type of a computation that may fail. `E` is a fieldless enum; `T` may be `void`. Both functions and values may be of this type.

**Representation (compiler-internal).** A tag plus the payload. Tag 0 means success; an error is stored as its variant's ordinal plus 1, so error enums are ordinary enums with no numbering restriction. `Result` is not C-visible.

**Producing results.** In a `return`, a value of type `T` or of type `E` is accepted and wrapped (§3). `return;` (or falling off the end) is success for `Result[void, E]`.

**Consuming results.** A `Result` must be consumed; ignoring one is a compile error.

| Form | Meaning |
| :--- | :--- |
| `try expr` | If `expr` succeeded, its value; otherwise return its error from the enclosing function. The enclosing function must return `Result[_, E]` with the **same** `E` (no widening, no conversion). |
| `expr catch (e) { ... }` | Value of `expr` on success; on error, run the block with `e: E` bound. The block must diverge (`return`, `break`, `continue`, `trap()`) unless `expr` has type `Result[void, E]`. |
| `unwrap_or(r, d)` | The payload, or `d` on error (`T: Copy`). |
| `is_err(r)` | `true` if `r` is an error (`T: Copy`). |

Mapping between two error types is written with `catch` (see `litmus/05_typed_arena.kr`):

```
mut a = Arena[Expr].init(8, blank) catch (e) { return ArenaError.Full; };
```

`try` and `catch` are visible at the call site; there is no unwinding. Functions never raise except through `Result` or by aborting.

---

## 8. Compile-Time Constants

`const NAME: T = expr;` declares a constant (top level or in a function). The initializer is a constant expression: literals, other constants, arithmetic, `size_of`/`align_of`, array literals, and string literals. A `const` item may have type `const u8[]` (static data); this is the only place a slice may be stored (`spec/03-memory.md` §2).

---

## 9. Prelude

These names are available everywhere without `import`. They are ordinary identifiers (not keywords) and can be shadowed.

**Types**

| Name | Meaning |
| :--- | :--- |
| `Result[T, E]` | success value or error (§7) |
| `Buf[T]` | owning heap buffer (below) |
| `AllocError` | `enum AllocError { OutOfMemory }` |

**Marker bound**: `Copy` (§1).

**Intrinsics**

| Intrinsic | Signature | Notes |
| :--- | :--- | :--- |
| `size_of(T)`, `align_of(T)` | `-> usize` | `T` is a name-shaped type; use an alias for others |
| `swap(a, b)` | `(&mut T, &mut T)` | exchanges two values; **valid for linear `T`** because both stay owned |
| `trap()`, `unreachable()` | never returns | abort; neither is an optimizer hint |
| `unwrap_or(r, d)`, `is_err(r)` | see §7 | `T: Copy` |
| `is_null(p)` | `(?T*) -> bool` | |
| `unwrap_or_trap(p)` | `(?T*) -> T*` | aborts if null |
| `wrapping_add/sub/mul(a, b)` | `(T, T) -> T` | `T` an integer type; wraps modulo 2^N |

**`Buf[T]`** is the only dynamically sized owning container. It is a compiler-known **linear** type holding a heap block (C `malloc`/`free`), with `T: Copy` and alignment of `T` at most 16.

| Operation | Meaning |
| :--- | :--- |
| `Buf[T].filled(n, v)` | `Result[Buf[T], AllocError]`: `n` copies of `v`. A size that would overflow is `OutOfMemory`. `n == 0` is allowed |
| `b.len()` | `usize` |
| `b[i]` | element by value; aborts if out of range |
| `b[i] = v`, `b[i].f = v` | element assignment (requires `b` to be `mut` or a `&mut` borrow) |
| `b[lo..hi]` | a borrowed slice, valid only as a call argument |
| `b.destroy()` | consumes and frees `b` |

There is no resizing, cloning, or iteration protocol: grow by allocating a new `Buf` and copying. Containers of linear values are not available in v1.
