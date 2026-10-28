# Kore Design Review, Round 2 (against v0.3)

Five reviewers (grammar, ownership soundness, semantics/ABI, concurrency/FFI, regression audit) re-read the whole repository after the v0.3 fixes. Claims below marked **VERIFIED** were re-checked by me against the files or by running `tools/`; **UNVERIFIED** means reasoning only (no checker exists, and the LLVM/psABI points are from memory). No spec file was changed in this round.

## 1. Verdict

v0.3 is a large step forward and the tooling is real: `ll1.py` reports 0 conflicts, the 5 litmus programs parse, and the keyword count (28 + 3) holds. The headline safety claim is **still not established**. One structural gap (what happens to a borrow's *source* and *destination*) lets safe code create dangling borrows, so emitting `noalias` today would still miscompile. Beyond that, my own v0.3 text contains false statements, stale residue, and one real bug in a litmus program.

| Round-1 finding | Round-2 status |
| :--- | :--- |
| A1 `lock()` vs Rule 1 | **Fixed in the type rules** (`MutexGuard` is consistent with RFC 0003). Thread story still open. |
| A2 slices bypass Rule 1 | Rule exists; **circumvented by out-param stores** (S-3 below) |
| A3 raw pointers | Fixed, **weakened by `[safe]` on pointer-taking externs** (H-6) |
| A4 `destroy` fails leak check | **Fixed** (destructuring). RFC 0006 still has leftovers (`VMError`, flags). |
| A5 zero-init | **Fixed** (definite init + `Zero`). Stale text remains in RFC 0005. |
| A6 `noalias` | **Not safe to emit** until S-1..S-5 are closed |
| A7 live `&const` freeze | **Fixed**, but scope death of the borrowed local is not covered (S-2) |
| A8 error-union ABI | Direction only; RFC text still wrong (unchanged) |
| A9 `api.kr.d` stubs | Open (unchanged) |
| A10 grammar not LL(1) | **Fixed and mechanically verified.** Some prose claims about it are false (§4). |

## 2. Critical: ownership soundness (new holes in the v0.3 rules)

All five are **UNVERIFIED** against a checker, but **VERIFIED** that the rule text contains no clause preventing them (grep of RFC 0003) and that the grammar accepts the shapes (parser probe).

* **S-1: returned borrow provenance is never checked in the callee.** Rule 1 is a call-site rule. `fn bad(a: &const u32) -> &const u32 { let x: u32 = 5; return &const x; }` has exactly one borrowing parameter, so it passes, and the caller believes the result is tied to `a`. Likewise returning `b.get(0)` where `b` is a local `Buf` destroyed by a `defer`.
* **S-2: scope death of a borrowed local is not a conflict.** `mut r = &const a; { let x = 5; r = &const x; } use(*r);` and the loop-carried form. Rule 2's freeze list covers writes and moves only.
* **S-3: borrows can be stored through references.** `fn link(dst: &mut Holder, src: &const u32) { dst.r = src; }` or `fn store(c: &mut Cursor, s: const u8[]) { c.src = s; }`. A caller passes a short-lived slice and later uses `cur`. Rule 1's soundness argument ("a borrow only lives in a local or parameter") is false for this case. `&mut &const T` is also accepted by the grammar and not banned.
* **S-4: `defer` bodies are not modelled in the liveness/freeze CFG.** `let g = m.lock(); defer g.unlock(); defer m.destroy();` runs `destroy` first (LIFO), leaving the guard borrowing a destroyed mutex. Registration only moves `m` to `Deferred`.
* **S-5: a `defer` in an inner block on an outer variable.** `let f = open(); { defer f.close(); } f.read(buf);` is accepted; the variable is never moved to `Consumed` when the inner block exits. (The loop form may be rejected only by accident.)

**Proposed minimal rules (my recommendation):** (1) a returned borrow must have provenance rooted in the sole borrowing parameter's referent, or be static; a borrow of a local never leaves its scope. (2) A borrow may be assigned only into frame-owned locals declared **after** its source in an enclosing-or-equal scope; **never** into a place reached through a reference or parameter. (3) Lower `defer`/`errdefer` bodies into the CFG at every exit edge, LIFO, and run liveness, freeze and linear checks on the lowered CFG. (4) A `defer` may consume only variables declared in its own block.

## 3. High

* **H-1: `Buf.init_zeroed` overflow, found independently by three reviewers (VERIFIED, my bug).** `litmus/05_allocator.kr:57` computes `n * size_of::[T]()` with wrapping multiply but stores `count: n`; a huge `n` gives a small block that `get`'s bounds check believes is large, so safe code gets an out-of-bounds read/write. Fix: checked multiply returning `AllocError`; also `malloc(0)` may return NULL (reported as OOM), and `heap_alloc` returns null for `align > 16`.
* **H-2: no safe way to share data with a thread.** The "N workers increment a shared counter" program fails on every route: borrows can't be sent (Rule 1, D-016), by-value moves into one thread, `Mutex[T]*` needs `unsafe` and has no lifetime, no statics, no closures, `Channel` undefined. Joinable thread arrays also fail Rule 3 (assigning into a linear element place). **Minimal fix:** scoped threads (a built-in signature that lets a borrowing context cross threads only inside a scope that joins), plus a linear `Arc[T]`. The scoped-thread rule is a lifetime relation in disguise and needs a built-in signature.
* **H-3: marker types cannot be declared for std types.** `Copy`/`Zero`/`Send`/`Sync` are auto-derived only. `Buf`, `Mutex`, `Arc` hold raw pointers, so they are never `Send`; interior mutability is a hard-coded list (`atomic`, `Mutex`) with no inference or opt-in. RFC 0002 `[unsafe_send]` already parses but no RFC defines it. **Need:** defined, unsafe-only attributes (`[unsafe_send(...)]`, `[unsafe_sync(...)]`, `[interior]`), with interior-mutability and non-`Copy` inferred upward like linearity.
* **H-4: `Mutex` and `atomic` are `Copy` by derivation** (concurrency reviewer; follows from Rule 3 as written). `let snap = *shared;` would copy the protected data without locking. Make them non-`Copy`, and make non-`Copy` infectious.
* **H-5: `unsafe` is not an expression; no array literals; `catch` cannot yield a value (VERIFIED by parser).** Litmus 4/5 use `mut rc: i32 = 0; unsafe { rc = bind(..); }`, which cannot work for non-`Zero` results (`&T`, linear values). `catch (e) { 0 }` is rejected, so "recover with a default" is inexpressible. `[1,2,3]` is rejected.
* **H-6: `[safe]` on externs is unsound for pointer parameters, and `[safe] close` breaks `Fd` linearity.** Raw pointers are safely creatable and may dangle, so `[safe] fn memcpy(dst: u8*, ..)` cannot be memory-safe. Even `[safe] close(fd: i32)` lets safe code close an fd owned by a linear `Fd` (resource safety, not memory safety). **Fix:** `[safe]` only for signatures with no pointer parameters; keep `close` non-`[safe]`.
* **H-7: `VM.*` takes `u8*` and is not `unsafe`.** Safe code can unmap memory a live `Buf` owns. `VM.map` returns `?u8*` but `mmap` returns `MAP_FAILED` (the bug litmus 5 already fixed in `Region`).
* **H-8: UB table still wrong.** Row 3 division is still `i64.min / -1` only (`i32.min / -1` is `sdiv` UB in LLVM, `%` too, AArch64 `sdiv` doesn't trap; two guards needed, or define `MIN / -1 = MIN`). `unreachable()` listed as a safe intrinsic must lower to a trap, not LLVM `unreachable`. Enum values out of range (extern returns) make an exhaustive-`switch` default UB unless it lowers to a trap. Literal typing is under-specified (`cast::[u64](0xFFFFFFFF)` is an error while `cast::[usize](-1)` works by accident).

## 4. Errors in my own v0.3 text (VERIFIED)

| Where | Problem |
| :--- | :--- |
| RFC 0002 §4, D-006 | Says `flags & MASK == 0` "is a syntax error". It parses as `(flags & MASK) == 0` (Rust's behavior, fine). Only `a < b == c` is rejected. |
| RFC 0002 §5 | "Parenthesize `fn() -> (E!T)`" is a silent trap: `fn() -> E!T` parses as `(fn() -> E) ! T` and only sema can reject it. Same for `?E!T`, `&mut E!T`. |
| RFC 0002 §5 | Lists "`&` must be followed by `mut`/`const`" as kept out of the grammar, but the grammar enforces it. |
| D-004, LITMUS L1-4 | Calls `errdefer` "necessary"/"cannot be written" without it. It can: `let v = f() catch (e) { keys.destroy(); return e; };`. It is a convenience that costs a keyword, a state and path-exact analysis. |
| LITMUS L4-1 | Claims `defer` closes the fd on `break`; `04_echo_server.kr` has no `break`. |
| LITMUS L3-1 | Says copying fields before the loop is "exactly what the checker wants"; nothing there mutates `self`, so it is not evidence for liveness. |
| LITMUS L5-1, D-019 | Say a region "hands out typed indices". `Region` has only `init`/`destroy`; program 3 uses `Buf`. Not implemented anywhere. |
| `05_allocator.kr` comment | Cites "finding L5-2" for the `Copy + Zero` rationale; the right finding is L1-1. |
| D-006 | Says counts were "counted by script"; no such script exists. `kparse.py` holds a second keyword list nothing checks against RFC 0002. |
| README | "hand-checked on 5 programs" overstates; this round's hand walk found five issues the first missed. |
| RFC 0006 status line | "§2.2 corrected" overstates: `VMError` is declared nowhere, `VMFlags.Anonymous` alone (no `Private`) still fails on Linux. |
| `DECISIONS.md` | A1 marked Resolved though `Mutex` has no constructor, thread story, or interior-mutability rule. D-017's "Decided (direction only)" status isn't defined; `--no-noalias` (D-012) appears in no RFC; two dropped findings (`extern struct` split, `i64.min` grammar) are in no row. |
| Taste calls unlabeled | D-003 (`with`), D-005, D-006, D-018, D-020 are taste calls; only D-001 says so. |

**Stale residue (all VERIFIED by grep):** RFC 0001 "4-rule ownership verifier" (now 5), row 6 "Linear slices", Pillar 3 "every struct uses C layout" vs RFC 0003 §2.2; RFC 0005 §5.1 "zero-initialized on entry", `SysError.None = 0`, `nocapture` on a slice param that elision may return, §4 step 4 verifying ownership per instantiation (D-016 says once against bounds); RFC 0004 §2 heading "Stackless Coroutines Beat Green Threads", §3.1 sends slices "with linear ownership", bare `&expected` / `&atomic[u32]` (rejected by the grammar), dotted `fn Futex.wait`/`fn VM.map` still declared though RFC 0002 §7 says they're invalid; RFC 0006 §6.1 "29-keyword grammar".

## 5. Medium

* Linear temporaries are untracked: `Fd.wrap(raw, e);` as a statement discards a linear value without error; `make_fd().raw` reads a field of a dropped temporary; autoref of an rvalue has no lifetime rule.
* Borrowing-ness is under-defined: `?&const T` and fn types with `&` parameters aren't in Rule 1's list; `T -> ?T` coercion is missing from §2.1; no `never` type, so a user function can't be declared divergent; fn pointer types need the same elision rule as declarations; mutability must be inherited through `&const` paths.
* Safe replacement of linear places is inexpressible (`swap`/`replace`/`take`); litmus 1 hides it by omitting `grow`. A checked `replace(dst: &mut T, v: T) -> T` intrinsic is sound for linear `T`.
* Linear values are forgeable inside the defining module (`Fd{raw: 0}` twice), so "no double free" holds only modulo module authors; the directory-wide module boundary widens that. State this honestly.
* A failed `try f(linear_arg)` leaves the callee owning the argument; with payload-free errors it can never be handed back.
* Adding a borrowed field to a `pub` struct flips it second-class (hidden semver break); `.kpkg` stubs must record linear, borrowing and `Send` properties.
* String-keyed maps are blocked: slices can't be generic arguments, strings aren't `Copy`, and `get(&self, &K)` is rejected by elision (two borrowing params).
* Shift: amount type, signedness of `>>`, constant over-shift; casts: bool, f32/f64, `distinct`, enum-from-integer path undefined. `E!T` cannot compose across different error enums (no widening). No C-ABI function-pointer type, so C callbacks (`qsort`, `signal`) can't be typed. `setjmp`/`vfork` need a `returns_twice` import attribute. SIGPIPE kills the echo server (`write` to a closed peer). No tuple field access (`x.0`), no variadic imports, no labeled `break`.
* `kparse.py` bugs (minor): strips `//` inside string literals; raises non-`SyntaxError` on malformed input; lexer looser than §3 (multi-char char literals, `...` token).
* RFC 0005 §6 observability claims were never revised and remain wrong (frame pointer is 4 bytes, `perf script | pprof` needs a converter, "zero overhead").

## 6. What held up (round 2 could not break it)

Joins and loop-invariance for linear state are conservative; errdefer cancellation is path-exact given the join rule; `Buf.destroy(self)` while a `get` borrow is live is rejected; `f(p,p)` and `v.push(f(&mut v))` are rejected; element-path collapse is conservative; null narrowing for locals is sound; `noalias` on `&mut S` with a derived `&mut S.f` is sound; the `{ }`-after-expression postfix creates no mis-parse; precedence table matches the EBNF; the `MutexGuard` design is the strongest single fix.

## 7. Single best change (reviewer recommendation, my assessment)

The regression reviewer recommends a `from` clause: `fn text(self: &const Token, src: const u8[]) -> const u8[] from src;` naming which parameters a returned borrow depends on. It is the cheapest sound way to relate two borrowing parameters, removes the `pick` / `Token.text` / string-map friction, and supplies the dependency summary that closes S-1 and S-3 (an `&mut` parameter can only receive borrows from parameters it lists). It is a design change to the language's central bet, so it is **your call**; my ordering would be: first adopt the cheap rules in §2 (they are necessary either way), then decide on `from`. Austral-style regions and Rust named lifetimes are heavier; Hylo subscripts are comparable but more machinery.

## 8. Feasibility (reviewer estimate, UNVERIFIED)

* ~5-7 person-months for one strong engineer to compile and run all five litmus programs through a **C-emitting backend** (`-fwrapv -fno-strict-aliasing`, `noalias` as `restrict`, sanitizers for free); 12+ months for LLVM with DWARF and ABI. Implement the checker in Rust or OCaml; the Go + LLVM tension disappears with C emission.
* **Highest-risk component:** the Rule 1 + Rule 2 borrow checker. **Cheap experiment (~1 week):** a ~500-line Python toy IR with places, borrows and call summaries, running the compile-fail corpus (RFC 0003 ERROR examples, round-1 counter-examples, S-1..S-5, H-1). If derived-value liveness forces special cases, the "no lifetime syntax" bet is in trouble.
* **Test strategy:** an `// ERROR:` compile-fail corpus plus the five litmus files as accepts; a soundness oracle that runs accepted random programs under ASan/UBSan.
* The repository is **not under version control**, so v0.2 is unrecoverable and several "v0.2 had X" claims can't be audited. Run `git init`.

## 9. Prioritised "fix next"

1. Close S-1..S-5 in RFC 0003 (provenance, scope death, no stores through references, lower defers into the CFG, defer scope rule).
2. Fix `Buf.init_zeroed` (checked multiply) and the other litmus bugs; mark `[safe]` pointer-parameter externs and `close` correctly.
3. Define marker/interior-mutability declarations and make `Mutex`/`atomic` non-`Copy` (H-3, H-4).
4. Decide and specify scoped threads + `Arc`, or explicitly defer threads out of v0.3.
5. Add `unsafe` blocks as expressions, array literals, and a value-yielding `catch` (or `unwrap_or`).
6. Correct the false statements and stale residue in §4; add a script that checks the keyword set across RFC 0002 and `kparse.py`.
7. Fix the UB table (division at every width, `unreachable()`, enum out-of-range, literal typing).
8. Decide the `from` clause (your call).
9. `git init`; build the toy borrow-checker prototype and compile-fail corpus before more RFC prose.
10. Rewrite RFC 0003 §5 / RFC 0005 §5.2 ABI text per D-017, and re-label D-009, D-010, D-016, D-021 as **Provisional** pending your approval.
