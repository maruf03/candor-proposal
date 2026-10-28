# Kore

A small, statically typed, ahead-of-time compiled systems language: memory safe without a garbage collector or lifetime annotations, defined behavior outside `unsafe`, and direct C interop.

**Status:** specification v1 (draft). **No compiler exists yet.** The grammar is mechanically verified; the ownership rules are checked by hand against 5 programs and 35 must-reject programs.

```rust
linear struct Fd { raw: i32; }

extern "C" {
    fn dup(fd: i32) -> i32;
    fn close(fd: i32) -> i32;
}

pub enum DupError { Failed }

impl Fd {
    pub fn dup(raw: i32) -> Result[Fd, DupError] {
        let copy = unsafe(dup(raw));           // calling C is always `unsafe(...)`
        if (copy < 0) { return DupError.Failed; }
        return Fd{ raw: copy };
    }
    pub fn close(self: Fd) {
        let Fd{ raw } = self;                  // destructuring consumes the handle
        unsafe(close(raw));
    }
}

pub fn main() -> i32 {
    let f = Fd.dup(1) catch (e) { return 1; };
    defer f.close();                           // cannot be forgotten: `f` is linear
    return 0;
}
```

## The Idea

Borrows (`&const`, `&mut`, slices) exist **only for the duration of a call**: they cannot be returned, stored, or named, so they cannot dangle and need no lifetimes. Resources are `linear`: consumed exactly once, on every path. `defer` and `errdefer` make cleanup path-complete. 29 keywords, one marker (`Copy`), no traits, no closures, no macros.

The trade-offs (no returned references, `Copy`-only containers, single-threaded in v1) are listed in `spec/00-overview.md` §4.

## Layout

| Path | Contents |
| :--- | :--- |
| `spec/00-overview.md` ... `06-compiler.md` | the specification: overview, syntax, types, memory, FFI, modules, compiler plan |
| `docs/decisions.md` | every decision with alternatives and costs; what is deferred and why |
| `docs/litmus.md` | what the five litmus programs showed |
| `litmus/` | five programs that must be accepted |
| `tests/fail/`, `tests/syntax_fail/` | programs that must be rejected (semantically / by the parser) |
| `tools/` | LL(1) checker, parser, keyword check, test runner |
| `deferred/` | parked designs: concurrency, returned borrows, LLVM backend, packages and LSP |

## Checking the Grammar and Tests

```bash
python3 tools/ll1.py spec/01-syntax.md             # conflicts: 0
python3 tools/check_keywords.py spec/01-syntax.md  # keyword box, grammar, parser agree
python3 tools/run_tests.py spec/01-syntax.md       # litmus + tests behave as expected
```

## Next

`spec/06-compiler.md` §5: first an ownership-check prototype (accept `litmus/`, reject `tests/fail/`), then the Rust compiler emitting C.
