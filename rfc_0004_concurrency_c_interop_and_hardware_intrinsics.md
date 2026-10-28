# RFC 0004: Fearless Concurrency, Seamless C ABI Interop, and Hardware Intrinsics

- **RFC Number:** 0004
- **Title:** Fearless Concurrency, Seamless C ABI Interop, and Hardware Intrinsics
- **Author:** Language Design Working Group
- **Status:** Draft (§4.1 revised and §4.2 deferred 2026-10-28; **other sections not yet revised**, see banner)
- **Type:** Standards Track (Concurrency & Runtime Intrinsics)
- **Created:** 2026-10-28

---

## 1. Abstract

This RFC defines Kore's concurrency model, foreign function interface (`extern "C"`), and built-in hardware intrinsics (`VM`, `Futex`, `atomic[T]`). It explains why Kore uses **1:1 native OS threads** rather than green threads (goroutines), and how structurally derived `Send` and `Sync` markers are meant to eliminate data races at compile time. Stackless coroutines are **deferred** (D-009).

> **Open issues (from `DESIGN_REVIEW.md`, not yet resolved in this RFC).** (1) `Send`/`Sync` rules contradict each other (`Mutex[T]*` is `Send`, raw pointers are not) and `Thread` has no lifetime or `join`: a thread can outlive the frame whose data it was given. Likely fix: scoped threads (`Thread.scope`) plus a linear `Arc[T]`; `&const T` is `Send` iff `T: Sync`. (2) `Sync` is defined but never used. (3) The `atomic[T]` API lacks `load`/`store`/`exchange`/`fence`, CAS needs success and failure orderings and an `&mut expected`, and `MemoryOrder` must be a constant expression. (4) No memory model is specified: adopt the C++11/LLVM model by name, and confine data races to `unsafe`. (5) `VM`, `Futex`, `CPU`, `Thread` are undeclared compiler-magic namespaces; they should be `extern "C"` wrappers in `std/sys` and `std/thread` with only `atomic` and prefetch as true intrinsics. (6) Several `VMAdvise`/`VMFlags` values are wrong for Linux (`Sequential = 1` is `MADV_RANDOM`; `HugePage2MB = 64` is `MAP_32BIT`), flags cannot be OR-ed, and `MAP_PRIVATE`/`MAP_SHARED` is mandatory for `mmap`. (7) Platform claims (macOS `__ulock_*` is private API; `VirtualFree` cannot unmap a sub-range) need qualifying. (8) The C-interop story needs the Kore-internal ABI split (D-017): `Result[T, E]`, tuples, and slices cannot appear in `extern "C"` signatures.

---

## 2. Why 1:1 Threads Beat Green Threads for C Interop

Languages with M:N green threads (such as Go) execute user code on tiny growable stacks (2 KB–8 KB) managed by a background runtime scheduler. While convenient for managed code, M:N green threads severely degrade C interoperability:

1. **The Stack-Switching Penalty (`cgo` tax):** C libraries (`sqlite3`, `openssl`, `libuv`, `zlib`) expect standard 2 MB–8 MB OS thread stacks. Calling a C function from a green thread requires pausing the green thread, switching the hardware stack pointer (`RSP`/`SP`) to an OS system stack, updating scheduler locks, calling C, and switching back—turning a 1 ns function call into a 50–150 ns bottleneck.
2. **Scheduler Starvation:** If a green thread invokes a blocking C library function, the underlying OS carrier thread blocks in the kernel unless a heavy runtime monitor thread preempts and migrates the run queue.

### Kore's Concurrency Architecture
Kore achieves zero-cost C calls with 1:1 threads. A second primitive, stackless coroutines, is deferred (D-009):
1. **1:1 OS Threads (`Thread.spawn`):** Every thread is a real OS kernel thread (`pthread_create` / `CreateThread`) with a native stack. Any C function can be called at any time with **0 ns overhead**.
2. **Stackless coroutines (`Task[T]` + `yield`): deferred (D-009).** The v0.2 claim of "millions of tasks driven by `io_uring`" depended on a scheduler and ownership model the RFC never specified; async I/O is a library concern for now (§4.2).

---

## 3. Compile-Time Data-Race Freedom (`Send` & `Sync`)

Kore prevents data races across threads without manual trait boilerplate. The compiler automatically derives two structural properties for every type `T`:

### 3.1 Structural Derivation Rules
1. **`Send` (Safe to transfer ownership across threads):**
   * All scalar primitives (`i32`, `u64`, `f64`, `bool`) are `Send`.
   * A `linear struct` or value `struct` is `Send` if and only if all of its fields are `Send`.
   * `Mutex[T]*` and `Channel[T]*` (where `T: Send`) are `Send`.
   * Raw pointers (`T*`, `?T*`) are **not `Send`**. Slices and references are borrows and can never be sent (RFC 0003 Rule 1). Library types that own memory through a raw pointer need an explicit unsafe opt-in, which is not yet defined (open issue 1).
2. **`Sync` (Safe to share read-only access across threads):**
   * Immutable primitives, `atomic[T]`, and `Mutex[T]` are `Sync`.

### 3.2 Thread Spawning Enforcement
The `std/thread` function `spawn` is checked by the semantic analyzer (its `T: Send` bound is enforced at the call):
```rust
pub fn spawn[T: Send](context: T, entry: fn(T)) -> Thread;   // std/thread; lifetime/join semantics: see Open issues
```
* **Compile-Time Check:** The type `T` passed as `context` **must satisfy `Send`**.
* If `T` is a `linear struct` (e.g., an owned `PageBuffer`), passing it to `Thread.spawn` **consumes** `context` in the parent thread and transfers sole ownership to the child thread.
* Passing a borrowing type (a reference or a slice such as `u8[]`) into `spawn` is rejected: borrowing types cannot be generic arguments and cannot cross threads (RFC 0003 Rule 1). Diagnostic: `Type 'u8[]' is a borrow and cannot cross a thread boundary`. How data is shared between threads is an open issue (see the banner above).

---

## 4. Synchronization Primitives

### 4.1 Data-Bound `Mutex[T]`

In C, mutexes lock lines of code rather than data. In Kore, `Mutex[T]` wraps the protected value and the only way to reach it is through a **linear, borrowing guard**. v0.2 used a `with` block and a `lock()` that returned `&mut T`, which contradicted the rule that references cannot be returned; both are gone (D-003, D-010).

```rust
// std/sync (library code; unsafe confined here)
pub linear struct MutexGuard[T] { m: &const Mutex[T]; }   // linear AND borrowing

impl[T] Mutex[T] {
    pub fn lock(self: &const Mutex[T]) -> MutexGuard[T];     // elision: result borrows `self`
}
impl[T] MutexGuard[T] {
    pub fn get(self: &mut MutexGuard[T]) -> &mut T;          // elision: result borrows the guard
    pub fn unlock(self: MutexGuard[T]);                      // consumes the guard
}

struct SharedCounter {
    processed_bytes: u64;
    active_workers: u32;
}

fn bump(shared: &const Mutex[SharedCounter]) {
    mut guard = shared.lock();
    defer guard.unlock();             // guard: Deferred; may still be borrowed below
    let c = guard.get();              // c: &mut SharedCounter, borrows `guard`
    c.processed_bytes += 4096;
    c.active_workers += 1;
}                                     // unlock runs on every exit path
```

* **Safety from the existing rules, no special cases.** The guard is *linear*, so it must be unlocked exactly once (the `defer` does this on every path, including `try` errors). It is *borrowing* (it holds `&const Mutex[T]`), so it cannot be stored or returned, and the shared borrow **freezes the mutex** while the guard is live, so the mutex cannot be destroyed under it. `c` borrows the guard, so it cannot outlive it (Rule 2). No lifetime annotations appear.
* **Not yet answered (see Open issues):** how a `&const Mutex[T]` reaches another *thread* (borrows cannot cross `Thread.spawn`); mutex construction and ownership; recursive locking, deadlock, `try_lock`, condition variables, `RwLock`; and the undefined `Channel[T]`. `trap()` kills the process, so lock poisoning does not exist.

### 4.2 Stackless Coroutines (`Task[T]` and `yield`): **Deferred**

Removed from v0.3 (D-009). v0.2 defined no executor, `await`, result access, or cancellation; the example was a `MSG_DONTWAIT` busy loop; coroutine frames saved slices that outlive their sources; dropping a suspended task leaked its linear locals; and the frame size (known only after LLVM's CoroSplit) conflicts with struct layout in RFC 0003. Until a design exists that answers those, async I/O is a library concern (an event loop over `epoll`/`io_uring` with owned buffers passed by value and returned on completion, as in Monoio/Glommio). `yield` is no longer a reserved word.

---

## 5. Hardware & OS Kernel Intrinsics

Kore provides built-in intrinsic namespaces (`atomic[T]`, `VM`, `Futex`, and `CPU`) that lower directly to hardware instructions or OS syscalls without runtime dependencies.

### 5.1 Hardware Atomics (`atomic[T]`)
Supported for `T` $\in \{ \text{bool}, \text{i8}..\text{i64}, \text{u8}..\text{u64}, \text{usize}, \text{isize}, T^* \}$. Direct assignment (`a = 1`) is forbidden on `atomic[T]` to force explicit memory ordering:

```rust
enum MemoryOrder {
    Relaxed,
    Acquire,
    Release,
    AcquireRelease,
    SeqCst,
}

// Usage:
mut state: atomic[u64] = 0;
let old: u64 = state.fetch_add(1, MemoryOrder.AcquireRelease);
let ok: bool = state.compare_exchange(&mut expected, desired, MemoryOrder.SeqCst);
```
* **LLVM Lowering:** Lowers directly to `atomicrmw add` and `cmpxchg` instructions with zero function call overhead.

### 5.2 Virtual Memory Intrinsics (`VM`)
Allows userland libraries to implement high-performance Arena, Slab, and Bump allocators directly atop the hardware MMU:

```rust
enum VMProtect : u32 { None = 0, Read = 1, Write = 2, ReadWrite = 3, Exec = 4 }
enum VMFlags   : u32 { Shared = 1, Private = 2, Anonymous = 32, HugePage2MB = 64 }
enum VMAdvise  : u32 { Normal = 0, Sequential = 1, WillNeed = 3, DontNeed = 4 }

// Pseudo-signatures: dotted names are not valid Kore (RFC 0002 §7). These belong in `std/sys` (open issue 5):
fn VM.map(size: usize, prot: VMProtect, flags: VMFlags) -> ?u8*;
fn VM.unmap(ptr: u8*, size: usize) -> bool;
fn VM.protect(ptr: u8*, size: usize, prot: VMProtect) -> bool;
fn VM.advise(ptr: u8*, size: usize, advice: VMAdvise) -> bool;
```
* **Lowering:** Emits direct Linux/macOS `mmap`/`munmap`/`mprotect`/`madvise` syscalls or Windows `VirtualAlloc`/`VirtualFree` calls.

### 5.3 Fast Userland Synchronization (`Futex`)
Exposes direct kernel address-wait primitives for building zero-allocation mutexes, semaphores, and work-stealing queues:

```rust
// Pseudo-signature, as above. Atomically verifies (*addr == expected) and puts thread to sleep in kernel
fn Futex.wait(addr: &const atomic[u32], expected: u32, timeout_ns: u64) -> bool;

// Wakes up to 'count' threads waiting on 'addr'
fn Futex.wake(addr: &const atomic[u32], count: u32) -> u32;
```
* **Lowering:** Maps to `SYS_futex` on Linux, `__ulock_wait`/`__ulock_wake` on macOS, and `WaitOnAddress`/`WakeByAddressSingle` on Windows.

### 5.4 Cache-Line Alignment & Prefetch Attributes
* `[align(64)]` on a `struct` or field forces 64-byte alignment in the LLVM type definition, preventing multi-core false sharing across L1/L2 cache lines.
* `CPU.prefetch_read(ptr)` and `CPU.prefetch_write(ptr)` lower directly to `@llvm.prefetch.p0(ptr, i32 0, i32 3, i32 1)` (read) and `@llvm.prefetch.p0(ptr, i32 1, i32 3, i32 1)` (write).