# Litmus Programs: Results

Five realistic programs in `litmus/`, written against RFC 0002 v0.3 (syntax) and RFC 0003 v0.3 (ownership). Purpose: find where the rules hurt **before** building a compiler.

**What was verified, and what was not.**
- **Syntax: mechanically.** All five parse with `tools/kparse.py` (a table-driven parser generated from the RFC 0002 grammar). The *old* grammar fails on the same code (first failure: the old grammar had no `x as T` / bracket-expression form, and `items[i]` was ambiguous).
- **Semantics: by hand.** There is no type checker or borrow checker yet. Each program was walked against RFC 0003 Rules 1-5 manually. A hand walk can miss things a compiler would catch; treat the verdicts as design evidence, not proof. The next milestone is a checker that rejects the `ERROR:` examples in RFC 0003 and accepts these files.

**Assumed std surface** (not specified yet): `mem.Buf[T: Copy + Zero]` (owning, linear), `mem.Allocator` (struct of fn pointers), `mem.AllocError`; intrinsics `cast`, `size_of`, `align_of`, `zeroed`, `trap`.

## Summary

| # | Program | Syntax | Semantics under RFC 0003 | Needed a workaround? |
| :-: | :--- | :-: | :--- | :--- |
| 1 | `01_hashmap.kr` | OK | Passes | Elements must be `Copy + Zero`; hash/eq as fn pointers |
| 2 | `02_tokenizer.kr` | OK | Passes | Source cannot be stored in a non-borrowing struct |
| 3 | `03_arena_graph.kr` | OK | Passes cleanly | None (this is the pattern the RFCs recommend) |
| 4 | `04_echo_server.kr` | OK | Passes | `[safe]` extern attribute; threads not expressible yet |
| 5 | `05_allocator.kr` | OK | Passes only with a restriction | Stateful allocators cannot be exposed safely |

## Bugs found in my own first drafts (the point of the exercise)

| Draft bug | Caught by | Fix |
| :--- | :--- | :--- |
| `Map` used `Buf.init_zeroed` but only required `Copy`; `Copy` includes non-null `T*`, which is not zero-valid | Rule 5 (`Zero`) | Separate `Zero` marker; `Map[K: Copy + Zero, ...]` |
| DFS stack sized `nodes.len()`; a dense graph pushes more entries and would trap | Reading the loop against bounds-check semantics | Size by `edges.len() + 1` (a runtime trap, never corruption) |
| Calls to `socket`/`listen`/`close` outside `unsafe` while others were inside | Rule "extern calls are unsafe" | `[safe]` on integer-only imports; `unsafe` around the rest |
| `mmap` failure checked with `== null`; C returns `MAP_FAILED` (`-1`) | Writing the `extern` signature honestly | `mmap` imported as returning `usize`; compare to `-1 as usize`. Lesson: raw C return conventions are a trap; `std/sys` must wrap them in `Result[T, E]` |
| `Buf` had a field and a method both named `len` | Rule "no field/method name clash" | Field renamed `count` |
| `Buf.init_zeroed` computed `n * size_of(T)` with wraparound but stored `count: n`, so a huge `n` gave a tiny block that `get`'s bounds check believed was large (out-of-bounds from safe code). **Missed by round 1; found by three round-2 reviewers.** | Round-2 review | Overflow guard before the multiply; `malloc(0)` special-cased |
| `write` to a closed peer raises SIGPIPE and kills the server | Round-2 review | `send(..., MSG_NOSIGNAL)` |
| `close` declared `[safe]`, so safe code could close a descriptor owned by a linear `Fd` | Round-2 review | `close` is no longer `[safe]`; only `Fd.close` calls it, inside `unsafe` |
| `Bump` allocator handed out `ctx: u8*` that could dangle (see L5-1) | Soundness walk | Reduced to `Region` with no pointer exposure |

## Findings

### Program 1: hash map
* **L1-1 (design cost): containers of `linear` values are not expressible.** `Buf[T]` frees memory but cannot run destructors for elements, so it requires `T: Copy + Zero`. `Map[Str, Connection]` cannot be written. Needs `destroy_with(fn(T))` and a drain protocol; tracked in RFC 0003 §6.3.
* **L1-2 (ergonomics): no operator-based generics.** Without traits, `K` cannot be hashed or compared; `Map` stores `hash`/`eq` as function pointers (Zig/Odin style). It works and is explicit, but every constructor takes two extra arguments.
* **L1-3 (validated): `get` returning `?&const V` works with elision.** One borrowing parameter (`self`), `key: K` by value. The returned borrow freezes `m` while `r` is live; `defer m.destroy()` is legal because `r`'s last use (`*r`) is evaluated before the defer runs. **This needs non-lexical (liveness) borrows**: a lexical borrow scope would reject `demo`.
* **L1-4 (validated): `errdefer` is a convenience, not a necessity.** `init` acquires three buffers. Without `errdefer` each failure path needs an explicit `catch (e) { keys.destroy(); return e; }`, which grows quadratically with the number of acquisitions; `errdefer` keeps it readable.
* **L1-5 (validated): `destroy` bottoms out via destructuring** (`let Map{ keys, vals, used, .. } = self;`): `..` skips `count`, `hash`, `eq`, all `Copy`.

### Program 2: tokenizer
* **L2-1 (design cost, main one): a view cannot be stored in a normal struct.** `Lexer` has no `src` field; every call receives `src`. This is memory-safe but easy to misuse (pass a different buffer to the next call).
* **L2-2 (mitigation works, partly): borrowing structs.** `Cursor{ src, lex }` is inferred borrowing, so it may exist as a local and be passed by `&mut`, bundling parser context. It **cannot** be returned (except via elision), stored in a `Buf`, put in a non-borrowing struct, or sent to a thread. A recursive-descent parser that stays on the stack is fine; a parser that is itself stored (for example in an LSP server's per-file state) must own its source (`Buf[u8]`) and re-borrow it per call.
* **L2-3 (ergonomic cost of elision): `Token.text(self, src)` is rejected** (two borrowing parameters). It had to become a free function `text(src, t)` with `Token` by value. Expect this friction in any API that mixes a borrowed receiver with a borrowed input.
* **Verdict on the core bet:** workable for a tokenizer, but this is where Rust-style lifetimes would have helped most. Open question for the author: is "no stored views" an acceptable cost? The escape hatches (owned `Buf`, indices, borrowing structs on the stack) all worked here.

### Program 3: arena graph
* **L3-1 (validated): the arena-index pattern works cleanly.** Cyclic structure with zero references. Rule 2 is barely exercised here: the copies of `first_edge`/`edge_count` are a style choice (nothing in that loop mutates `self`), so this program is weak evidence for liveness-based checking. It is good evidence that index-based graphs need no references at all.
* **L3-2 (spec gap closed): implicit deref.** `self.nodes.get_mut(i).visited = true;` and `self.node(n).visited` only read well with auto-deref on `.` through references; now specified in RFC 0003 Rule 2.
* **L3-3 (spec gap closed): `return seen;` in a function returning `Result[u32, E]`** needs the return-position coercion `T -> Result[T, E]`; now in RFC 0003 §2.1.

### Program 4: TCP echo server
* **L4-1 (validated): linear `Fd` + `defer` per loop iteration** closes a descriptor on every path (`try` failure and the normal end of each iteration; the loop has no `break`), and `srv` is closed on all errors. This is the strongest evidence for Rules 3-4.
* **L4-2 (spec gap closed): extern call safety.** Without `[safe]`, every `close(raw)` needs an `unsafe` block. `[safe]` on integer-only imports keeps the FFI layer readable; the grammar now allows attributes on extern imports.
* **L4-3 (blocked on RFC 0004): concurrency.** Thread-per-connection would be `Thread.spawn(conn, handle)`, moving a linear `Fd` by value, which Rule 3 supports. But `Thread` lifecycle/join and `Send` are unresolved (review items C1/C2/H1 in `DESIGN_REVIEW.md`), so the server is single-threaded. Epoll/`yield`-based async was cut (D-009).
* **L4-4 (gap): no `errno`.** Failures collapse to `NetError.Io`; the cause is lost. `std/sys` needs an `errno()` accessor.
* **L4-5 (rule needed): `while (true)` without `break` diverges**, otherwise `serve` has a missing-return path; stated in RFC 0002 §2.

### Program 5: allocator and buffer
* **L5-1 (real hole, design decision needed): stateful allocators dangle.** `Buf` stores an `Allocator`, whose `ctx` is a raw pointer to allocator state. Copy the `Allocator`, destroy the arena, and `Buf::get` still "works" in *safe* code: use-after-free. Borrowing (Rule 1) cannot fix it because `Buf` must be storable. Resolution adopted for v0.3: **safe std exposes only stateless allocators** (`heap()`); a page region is *intended* to hand out **typed indices, not pointers** (`Region` in program 5 currently has only `init`/`destroy`; the index-handle API is not written yet, and program 3 uses `Buf`, not `Region`), and any pointer-returning arena is an `unsafe` contract. Real arenas with lifetimes remain an open problem (candidates: Austral-style regions, generational handles).
* **L5-2 (validated): `unsafe` is confined to the allocator shims, `Region`, and `Buf`** in program 5. Programs 1-3 contain no `unsafe` at all; program 4 uses it only around C calls. This is the intended "trusted std, safe user code" split.
* **L5-3 (hazard): raw C return conventions** (`MAP_FAILED`, `-1` errors, `NULL`) are easy to get wrong (see bug table). `std/sys` should import raw functions privately and export `Result[T, E]` wrappers.
* **L5-4 (spec gap closed): `trap()`** must be a diverging intrinsic so `if (i >= count) { trap(); }` leaves `get` with a defined return path.

## What these programs do *not* test

Concurrency (Send/Sync, `Mutex`, atomics), coroutines (removed from v0.3), generic *instantiation* errors, `distinct` conversions beyond `cast`, the C ABI of error unions, `pub`/module boundaries across directories, and anything performance-related.

## Verdict on RFC 0003's core claim

For these five programs, "no lifetime annotations, second-class borrows, linear owners, indices for graphs" **held**, with two real costs (L2-1 stored views, L1-1 linear containers) and one real hole that forced a restriction (L5-1 stateful allocators). That is a better position than v0.2, whose rules would have let these same programs compile while allowing the review's counter-examples (stored slices, unsound getters, zero-initialized non-null pointers).
