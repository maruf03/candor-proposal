# RFC 0002: Lexical Specification, Reserved Words, and Formal $LL(1)$ Grammar

- **RFC Number:** 0002
- **Title:** Lexical Specification, Reserved Words, and Formal $LL(1)$ Grammar
- **Author:** Language Design Working Group
- **Status:** Draft (v0.3: grammar rewritten after mechanical LL(1) check; see `DECISIONS.md` D-001..D-006, D-022, D-023)
- **Type:** Standards Track (Syntax & Grammar)
- **Created:** 2026-10-28
- **Revised:** 2026-10-28

---

## 1. Abstract

This RFC defines the lexical structure, the reserved-word vocabulary, operator precedence, and the formal grammar of **Kore** in EBNF. The grammar in §6 is **mechanically verified LL(1)**: `tools/ll1.py` reports 0 conflicts, and `tools/kparse.py` (a predictive parser generated from the same tables) parses every program in `litmus/`. The previous (v0.2) grammar claimed LL(1) but had 13 conflicts; §7 lists what changed.

The grammar needs **no symbol table** to parse. Decisions that need name resolution (type argument vs index, field vs method, constant vs type in `[N]`) are deferred to semantic analysis.

---

## 2. Reserved Words

Kore reserves **29 keywords and 3 literal words (32 reserved words)**.

```
+----------------------------------------------------------------------------+
|                        KORE RESERVED WORDS (29 + 3)                        |
+------------------+------------------+------------------+-------------------+
| Declarations(11) | Control Flow(10) | Scoped/Error (4) | Binding/Cast (4)  |
+------------------+------------------+------------------+-------------------+
| pub              | if               | defer            | let               |
| import           | else             | errdefer         | mut               |
| fn               | switch           | catch            | unsafe            |
| struct           | case             | try              | as                |
| linear           | while            |                  | Literals (3)      |
| enum             | for              |                  | true              |
| impl             | in               |                  | false             |
| type             | break            |                  | null              |
| distinct         | continue         |                  |                   |
| extern           | return           |                  |                   |
| const            |                  |                  |                   |
+------------------+------------------+------------------+-------------------+
```

`with` and `yield` from v0.2 are **removed** (D-003, D-009). `errdefer`, `try` and `as` are **added** (D-004, D-005, D-023).

**Not keywords (ordinary identifiers, defined by the `core` prelude).** Intrinsic functions (their type arguments are written as ordinary arguments: `size_of(T)`, `zeroed(u8[4096])`): `size_of`, `align_of`, `zeroed`, `trap`, `unreachable`. Prelude types: `Result[T, E]` (D-022). Marker bounds: `Copy`, `Zero`, `Send`, `Sync`. Primitive type names (`i32`, `u8`, `bool`, `void`, ...). `self` is an ordinary parameter name. These can be shadowed; the compiler resolves them in the prelude scope.

### Detailed Keyword Behavior

| # | Keyword | Syntax Pattern | Semantics |
| :- | :--- | :--- | :--- |
| 1 | **`pub`** | `pub fn init() -> Buffer` | Exports a top-level declaration, struct field, or `impl` method outside the defining directory module (RFC 0006). `pub impl` is rejected. |
| 2 | **`import`** | `import "std/io";` | Imports a module under a mandatory qualifier (`io.read`). |
| 3 | **`fn`** | `fn add(a: i32, b: i32) -> i32` | Function declaration, function-pointer type, or anonymous non-capturing function. |
| 4 | **`struct`** | `struct Point { pub x: f32; y: f32; }` | C-layout value type (RFC 0003 §2.2). |
| 5 | **`linear`** | `pub linear struct Handle { fd: i32; }` | Resource type: must be consumed exactly once (RFC 0003 Rule 3). |
| 6 | **`enum`** | `enum Status : u8 { Ok = 0, Err = 1 }` | Integer-backed enumeration; `switch` over it must be exhaustive or have `else`. |
| 7 | **`impl`** | `impl[T] Vec[T] { pub fn len(self: &const Vec[T]) -> usize {...} }` | Associates functions with a type. No inheritance, no vtables. |
| 8 | **`type`** | `pub type Cb = fn(i32) -> bool;` | Transparent alias, or nominal wrapper with `distinct`. |
| 9 | **`distinct`** | `pub type UserId = distinct u64;` | Nominal type with the representation of its base. |
| 10 | **`extern`** | `extern "C" { [safe] fn getpid() -> i32; }` | Imports C symbols; `extern "C" fn f() {..}` exports a Kore function with the C ABI. Calling a non-`[safe]` import requires `unsafe`. `[safe]` is legal only on imports whose parameters are all non-pointer scalars. |
| 11 | **`const`** | `pub const MAX: usize = 1024;` | Compile-time constant, or read-only qualifier (`const u8*`, `const u8[]`, `&const T`). |
| 12 | **`let`** | `let n = buf.len();` | Immutable binding. Also destructuring: `let (a, b) = f();`, `let Handle{ fd } = h;`. |
| 13 | **`mut`** | `mut total: u64 = 0;` | Mutable binding. Also qualifies exclusive borrows: `&mut T`. |
| 14 | **`if`/`else`** | `if (x > 0) { ... } else { ... }` | Condition must be `bool`. Braces mandatory. |
| 15 | **`switch`/`case`** | `switch (s) { case .Idle: {..} case 1..5: {..} else: {..} }` | No fallthrough. Enum switch exhaustive or `else:`. Integer switch requires `else:`. An exhaustive enum `switch` lowers its implicit default to an abort, never to LLVM `unreachable` (an enum value outside its variants can be observed via `extern`). |
| 16 | **`while`** | `while (running) { ... }` | Pre-tested loop. `while (true)` without `break` diverges. |
| 17 | **`for`/`in`** | `for (i in 0..n)`, `for (x in slice)` | Iteration over a range or slice. |
| 18 | **`break`/`continue`** | `break;` | Run block-scoped `defer`s of exited scopes, then jump. |
| 19 | **`return`** | `return (val, true);` | Evaluates the operand, then runs all `defer`s LIFO, then returns. |
| 20 | **`defer`** | `defer close(fd);` | Runs the statement at every exit of the enclosing block, LIFO (RFC 0003 Rule 4). |
| 21 | **`errdefer`** | `errdefer buf.destroy();` | Like `defer` but runs only on error exits. |
| 22 | **`catch`** | `let f = open() catch (e) { return e; };` | Postfix on any expression: if the error-union value is an error, run the block with `e` bound. The block must diverge (`return`, `break`, `continue`, `trap()`) unless the expression has type `void`, in which case it may fall through. |
| 23 | **`try`** | `let f = try open();` | Unwrap or return the error from the enclosing function (error type must match). |
| 24 | **`unsafe`** | `unsafe { *p = 0; }` | Permits raw-pointer deref/arithmetic, pointer casts, and non-`[safe]` extern calls. |
| 25 | **`as`** | `let h = *k as u64;`, `p as (u8*)` | Explicit conversion (RFC 0003 §2.1). Binds tighter than `*`, looser than prefix and postfix operators. The right-hand type may not end in `*`; write pointer targets in parentheses. |
| 26 | **`true`/`false`/`null`** | `let p: ?u8* = null;` | Literals. `null` is valid only for nullable pointer/reference types. |

---

## 3. Lexical Structure

- **Source:** UTF-8. Non-ASCII bytes are legal only inside comments and string literals. A BOM is rejected. Line endings `\n` and `\r\n`. Whitespace (space, tab, CR, LF) is insignificant; statements end with `;`.
- **Comments:** `// ...` to end of line; `/// ...` is a doc comment. Both are lexed as comments (no grammar role); tooling may attach `///` text to the following declaration. There are no block comments. A `//` inside a string literal is part of the string.
- **Identifiers:** `[A-Za-z_][A-Za-z0-9_]*`. A reserved word cannot be an identifier.
- **Integer literals:** decimal `123`, hex `0xFF`, binary `0b1010`; `_` separators allowed (`1_000`). No suffixes. A literal's type comes from context (default `i32` if unconstrained); a literal that does not fit its type is a compile error. A leading `-` is range-checked together with the literal, so `-128` is a valid `i8`.
- **Float literals:** `1.5`, `1e9`, `2.5e-3`. A `.` belongs to a number only when a digit follows it, so `0..16` lexes as `0` `..` `16`.
- **String literals:** `"..."` with escapes `\n \r \t \\ \" \0 \xNN`. Type `const u8[]` (length known, **not** NUL-terminated; C interop passes `s.ptr` and `s.len`).
- **Char literals:** `'a'`, `'\n'`, `'\xNN'`. Type `u8` (ASCII / byte). Unicode scalars are out of scope for v0.3.
- **Punctuation and operators (maximal munch):** `<<= >>= -> .. << >> <= >= == != && || += -= *= /= %= &= |= ^=` and the single characters `+ - * / % & | ^ ~ ! < > = . , ; : ( ) { } [ ] ?`. Maximal munch means `u8*= null` lexes `*=`; write `u8* = null`.
- **Attributes:** `[name]` or `[name(args)]` before a declaration or field. Defined: `align(N)`, `packed`, `safe` (extern imports only).

---

## 4. Operator Precedence (highest to lowest)

| Level | Operators | Assoc. |
| :-: | :--- | :--- |
| 1 | postfix: `.f`, `[i]`, `[a..b]`, `[T, U]` (generic application; resolved in sema), `(args)`, `{fields}` | left |
| 2 | prefix: `-` `!` `~` `*` (deref) `&mut` `&const` `try` | right |
| 3 | `as` T | left |
| 4 | `*` `/` `%` | left |
| 5 | `+` `-` | left |
| 6 | `<<` `>>` | left |
| 7 | `&` | left |
| 8 | `^` | left |
| 9 | `\|` | left |
| 10 | `==` `!=` `<` `<=` `>` `>=` | **non-associative** (`a < b == c` is a syntax error) |
| 11 | `&&` | left |
| 12 | `\|\|` | left |
| 13 | `catch (e) { }` (postfix on the whole expression) | none |

Bitwise operators bind **tighter** than comparison and **looser** than `+`/`-` (Rust order, not C order), so `flags & MASK == 0` means `(flags & MASK) == 0` (in C it silently means `flags & (MASK == 0)`), and `a + b << 2` means `(a + b) << 2`. Chained comparisons (`a < b == c`) are syntax errors. Assignment (`=`, `+=`, ...) is a statement, not an expression. There is no ternary operator. Conversions use `x as T` (D-023): `*k as u64 * C` means `((*k) as u64) * C`.

---

## 5. Design Notes on the Surface Syntax

- **Generic type arguments.** `[...]` after a name is the same token sequence in types and expressions: `Vec[i32]`, `Mutex[Counter]*`, `mem.Buf[K].init_zeroed(a, cap)`, `Map[K, V]{ ... }`, `foo[i32](x)`, `size_of(Vec[i32])`. In expression position the contents are an expression list, so `a[i]` and `Vec[i32]` parse identically (as an index) and **semantic analysis decides** whether the head names a generic type/function or a value (Go's approach; D-023). The parser needs no symbol table. Consequence: an explicit type argument in an expression must be *expression-shaped* (names, qualified names, bracket suffixes such as `Vec[i32]` and `u8[4096]`); a pointer, nullable or function type (`u8*`, `?T*`, `fn(i32)`) cannot be written there, so give it a `type` alias or let inference supply it (`let p: T* = ...`).
- **Bracket suffixes in types.** `T[]` is a slice, `T[16]` an array, `Vec[i32]` a generic application. All three parse as `Ident "[" ... "]"`; semantic analysis decides which, by whether the head names a generic type and whether the bracket holds a literal. Array length is an integer literal or a named `const`.
- **Conversions** are `expr as T` (D-023): integer widening and narrowing (truncating/sign-extending by source type, defined), float to int (**saturating**, NaN to 0), int to float, and pointer casts (`unsafe` for pointer-to-pointer and integer-to-pointer). Anything else is a type error. The type after `as` is a name with optional bracket suffixes; a type ending in `*` must be parenthesized, `p as (u8*)`, so `x as u8 * y` is always a multiplication.
- **Error unions** are the prelude type `Result[T, E]` (D-022), an ordinary generic application: `fn open(p: const u8[]) -> Result[Fd, IoError]`, `Result[void, E]` for no payload. There is no `!` type operator, so `fn() -> Result[u8, E]` needs no parentheses and cannot misparse. `E` is a fieldless enum with no 0-valued variant (RFC 0003 §5.2). Use a generic alias to shorten a family: `type IoResult[T] = Result[T, IoError];`.
- **Pointer-to-function** needs parentheses: `(fn() -> u8)*`. (Without this, `fn() -> u8*` would be ambiguous.)
- **Struct literals** are a postfix `{ f: v, ... }` on a type expression: `Point{ x: 1, y: 2 }`, `mem.Region{ ... }`, `Pair[i32, i32]{ a: 1, b: 2 }`. Because every condition is parenthesized, `{` after an expression never starts a block.
- **Ranges are half-open.** `a..b` is `[a, b)` in `for (i in 0..n)`, in slicing `a[lo..hi]`, and in `case 1..5:` (which covers 1, 2, 3, 4). `a[..n]`, `a[n..]`, `a[..]` omit an end.
- **Semantic restrictions deliberately kept out of the grammar** (the grammar already requires `mut` or `const` after a type-position `&`): `..` in a destructuring pattern must be last; `defer` bodies may not contain `return`/`break`/`continue`/`try`; `else:` must be the last `case` arm; `break` and `continue` must be inside a loop; `return;` is valid only in a `void` or `Result[void, E]` function; a struct may not have a field and a method with the same name; `pub impl` is rejected; `case` ranges require integer scrutinees.

---

## 6. Formal $LL(1)$ EBNF Grammar

Lexical classes `Ident`, `IntLit`, `FloatLit`, `StringLit`, `CharLit` are terminals (§3). Quoted strings are literal tokens.

```ebnf
Module          = { ImportDecl } { AttributeList TopDecl } ;
ImportDecl      = "import" [ Ident ] StringLit ";" ;
AttributeList   = { "[" Ident [ "(" [ ExprList ] ")" ] "]" } ;

TopDecl         = [ "pub" ] ( FnDecl | StructDecl | EnumDecl | TypeDecl
                            | ExternDecl | ConstDecl | ImplDecl ) ;

FnDecl          = "fn" Ident [ TypeParams ] "(" [ ParamList ] ")" [ "->" Type ] ( Block | ";" ) ;
FnSignature     = "fn" Ident "(" [ ParamList ] ")" [ "->" Type ] ;
ParamList       = Param [ "," [ ParamList ] ] ;
Param           = Ident ":" Type ;

StructDecl      = [ "linear" ] "struct" Ident [ TypeParams ] "{" { FieldDecl } "}" ;
FieldDecl       = AttributeList [ "pub" ] Ident ":" Type ";" ;
EnumDecl        = "enum" Ident [ ":" Ident ] "{" [ EnumVariants ] "}" ;
EnumVariants    = EnumVariant [ "," [ EnumVariants ] ] ;
EnumVariant     = Ident [ "=" [ "-" ] IntLit ] ;
ImplDecl        = "impl" [ TypeParams ] Ident [ TypeArgs ] "{" { AttributeList [ "pub" ] FnDecl } "}" ;
TypeDecl        = "type" Ident [ TypeParams ] "=" [ "distinct" ] Type ";" ;
ExternDecl      = "extern" StringLit ( "{" { AttributeList FnSignature ";" } "}" | FnDecl ) ;
ConstDecl       = "const" Ident ":" Type "=" Expr ";" ;

TypeParams      = "[" TypeParam { "," TypeParam } "]" ;
TypeParam       = Ident [ ":" Ident { "+" Ident } ] ;
TypeArgs        = "[" Type { "," Type } "]" ;

Type            = PrefixType ;
PrefixType      = "&" ( "mut" | "const" ) PrefixType
                | "?" PrefixType
                | "const" PrefixType
                | FnType
                | PostType ;
FnType          = "fn" "(" [ TypeList ] ")" [ "->" PrefixType ] ;
PostType        = TypeAtom { "*" | "[" Bracket } ;
Bracket         = "]" | BracketItem { "," BracketItem } "]" ;
BracketItem     = IntLit | Type ;
TypeAtom        = Ident [ "." Ident ]
                | "(" Type [ "," Type { "," Type } ] ")" ;
TypeList        = Type { "," Type } ;

Block           = "{" { Stmt } "}" ;
Stmt            = VarStmt | ConstDecl | IfStmt | SwitchStmt | WhileStmt | ForStmt
                | ReturnStmt | DeferStmt | UnsafeStmt | BreakStmt | ContinueStmt
                | ExprStmt ;
VarStmt         = ( "let" | "mut" ) VarTarget "=" Expr ";" ;
VarTarget       = Ident ( [ ":" Type ] | StructPat )
                | "(" Ident { "," Ident } ")" ;
StructPat       = "{" PatItems "}" ;
PatItems        = PatItem [ "," [ PatItems ] ] ;
PatItem         = Ident [ ":" Ident ] | ".." ;
IfStmt          = "if" "(" Expr ")" Block [ "else" ( IfStmt | Block ) ] ;
SwitchStmt      = "switch" "(" Expr ")" "{" { CaseArm } "}" ;
CaseArm         = "case" CaseItem { "," CaseItem } ":" Block
                | "else" ":" Block ;
CaseItem        = Expr [ ".." Expr ] ;
WhileStmt       = "while" "(" Expr ")" Block ;
ForStmt         = "for" "(" Ident "in" Expr [ ".." Expr ] ")" Block ;
ReturnStmt      = "return" [ Expr ] ";" ;
DeferStmt       = ( "defer" | "errdefer" ) ( Stmt | Block ) ;
UnsafeStmt      = "unsafe" Block ;
BreakStmt       = "break" ";" ;
ContinueStmt    = "continue" ";" ;
ExprStmt        = Expr [ AssignOp Expr ] ";" ;
AssignOp        = "=" | "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;

Expr            = OrExpr [ "catch" "(" Ident ")" Block ] ;
OrExpr          = AndExpr { "||" AndExpr } ;
AndExpr         = CmpExpr { "&&" CmpExpr } ;
CmpExpr         = BitOrExpr [ CmpOp BitOrExpr ] ;
CmpOp           = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
BitOrExpr       = BitXorExpr { "|" BitXorExpr } ;
BitXorExpr      = BitAndExpr { "^" BitAndExpr } ;
BitAndExpr      = ShiftExpr { "&" ShiftExpr } ;
ShiftExpr       = AddExpr { ( "<<" | ">>" ) AddExpr } ;
AddExpr         = MulExpr { ( "+" | "-" ) MulExpr } ;
MulExpr         = CastExpr { ( "*" | "/" | "%" ) CastExpr } ;
CastExpr        = UnaryExpr { "as" CastType } ;
CastType        = TypeAtom { "[" Bracket } ;
UnaryExpr       = ( "-" | "!" | "~" | "*" | "try" ) UnaryExpr
                | "&" ( "mut" | "const" ) UnaryExpr
                | PostfixExpr ;
PostfixExpr     = PrimaryExpr { PostfixOp } ;
PostfixOp       = "." Ident
                | "[" Index "]"
                | "(" [ ExprList ] ")"
                | "{" [ FieldInits ] "}" ;
Index           = ".." [ Expr ] | Expr [ ".." [ Expr ] | "," Expr { "," Expr } ] ;
FieldInits      = FieldInit [ "," [ FieldInits ] ] ;
FieldInit       = Ident ":" Expr ;
PrimaryExpr     = IntLit | FloatLit | StringLit | CharLit
                | "true" | "false" | "null"
                | Ident
                | "." Ident
                | AnonymousFn
                | "(" Expr [ "," Expr { "," Expr } ] ")" ;
AnonymousFn     = "fn" "(" [ ParamList ] ")" [ "->" Type ] Block ;
ExprList        = Expr [ "," [ ExprList ] ] ;
```

---

## 7. What Changed From v0.2 and Why

| v0.2 problem (verified by `tools/ll1.py`) | v0.3 resolution |
| :--- | :--- |
| `items[i]` parses as index *or* generic application | Expression-position `[...]` takes an expression list and always parses as an index; semantic analysis decides index versus generic application (D-023). The parser needs no symbol table |
| `(Type) expr` vs `(Expr)` vs tuple literal share a prefix; `(a * b)` reads as a cast to `a*` | Casts are `x as T` (D-023) with a restricted right-hand type (no trailing `*` without parentheses). One `"(" Expr ["," ...] ")"` rule for grouping and tuples |
| `&const T`: `const` consumed by `&` or by the inner type | `&` must be followed by `mut`/`const` |
| `fn() -> u8*`: pointer to fn or pointer return? | `FnType` takes no suffixes; use `(fn() -> u8)*` |
| Trailing-comma lists (`{ "," X } [","]`) needed 2-token lookahead | Right-recursive `X ["," [List]]` |
| `PostfixOp` optional `(...)` after `. Ident` conflicted with next postfix | Field access and call are separate postfix ops; sema decides field-of-fn-pointer vs method |
| `ReturnStmt [Expr \| TupleLit]` overlap; `VarStmt` two alternatives sharing `let|mut` | Tuples are expressions; single `VarStmt` with left-factored `VarTarget` |
| `catch` only legal inside `let` | `catch` is a postfix on any `Expr` |
| `A!B` ambiguity inside fn types (and `fn() -> E!T` silently misparsing) | Error unions are the type `Result[T, E]` (D-022); the `!` type operator is gone |
| `case .Idle:` did not parse; no `default`; no ranges | Implicit-member `.Ident` primary; `else:` arm; `CaseItem = Expr [".." Expr]` |
| `[packed]` unwritable (attributes required parentheses) | `"[" Ident ["(" args ")"] "]"` |
| `fn Thread.spawn`, `fn VM.map` invalid | Those are library functions (`std/thread`, `std/sys`); no dotted `fn` names |
| Operator precedence undocumented and C-surprising | Explicit table in §4, Rust-style bitwise levels, non-associative comparison |
| Lexical spec missing | §3 |
| 27 / 29 / 31 keyword count | §2: 29 keywords + 3 literals, checked by `tools/check_keywords.py` |

## 8. Verification

```bash
python3 tools/ll1.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md      # conflicts: 0
python3 tools/kparse.py rfc_0002_lexical_specification_and_formal_ll_1_grammar.md litmus/*.kr   # 5 x OK
```

The checker validates that, for every nonterminal, alternatives have disjoint FIRST sets and that nullable alternatives do not overlap FOLLOW. It does not validate semantics; `litmus/` plus `LITMUS.md` exercise those.
