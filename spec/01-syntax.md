# Kore 1: Syntax

Lexical structure, reserved words, operator precedence, and the formal grammar. The grammar in §6 is **mechanically verified**: `tools/ll1.py` reports 0 LL(1) conflicts, and `tools/kparse.py`, a predictive parser built from the same tables, parses every program in `litmus/` and `tests/`. It needs **no symbol table**: decisions that depend on what a name refers to (index versus generic application, field versus method, array length versus type argument) are made by semantic analysis.

---

## 1. Principles

1. **Few words, few forms.** A reader should learn the whole surface in an afternoon. Every construct earns its place (see `docs/decisions.md`, D-03).
2. **Keyword-led declarations.** Every top-level item and local binding starts with a keyword (`fn`, `struct`, `let`, ...), so the parser needs one token of lookahead and error recovery can resynchronize on keywords.
3. **Explicit over implicit.** No operator overloading, no implicit numeric conversion, no truthiness, no hidden calls except `defer` and the two receiver conveniences of a method call (`spec/02-types.md` §5).
4. **C is the model.** When a question has a C answer (pointers, layout, calling convention, by-value structs), Kore gives the C answer, except where C's answer is undefined behavior for arithmetic, bounds or initialization (`spec/02-types.md`).

---

## 2. Reserved Words

Kore reserves **25 keywords and 3 literal words (28 reserved words)**.

```
+--------------------------------------------------------------+
|                  KORE RESERVED WORDS (25 + 3)                |
+------------------+------------------+------------------------+
| Declarations(10) | Control Flow(10) | Other (5)              |
+------------------+------------------+------------------------+
| pub              | if               | defer                  |
| import           | else             | let                    |
| fn               | switch           | mut                    |
| struct           | case             | as                     |
| enum             | while            | size_of                |
| impl             | for              | Literals (3)           |
| type             | in               | true                   |
| distinct         | break            | false                  |
| extern           | continue         | null                   |
| const            | return           |                        |
+------------------+------------------+------------------------+
```

**Not keywords** (ordinary identifiers defined by the prelude, `spec/02-types.md` §8): the intrinsics `slice`, `trap`, `wrapping_add`, `wrapping_sub`, `wrapping_mul`; the primitive type names. `self` is an ordinary parameter name.

### Keyword reference

| Keyword | Syntax | Meaning |
| :--- | :--- | :--- |
| `pub` | `pub fn init() -> Pool` | Exports a top-level item, struct field, or method from its directory module (`spec/05-modules.md`). |
| `import` | `import "std/io";` | Imports a module under a mandatory qualifier (`io.print`). |
| `fn` | `fn add(a: i32, b: i32) -> i32` | Function declaration, or function-pointer type. |
| `struct` | `struct Point { pub x: f32; y: f32; }` | C-layout value type. |
| `enum` | `enum Color : u8 { Red, Green }` | Fieldless enumeration. |
| `impl` | `impl[T] Stack[T] { ... }` | Associates functions with a type. |
| `type` | `type Idx = distinct u32;` | Alias, or nominal wrapper with `distinct`. |
| `distinct` | | See `type`. |
| `extern` | `extern "C" { fn getpid() -> i32; }` | Declares C functions to call. |
| `const` | `const MAX: usize = 1024;` | Compile-time constant; also the read-only qualifier (`const u8*`, `const u8[]`). |
| `let` / `mut` | `let n = f();` `mut i: usize = 0;` | Immutable / mutable binding. Every binding has an initializer. |
| `if` / `else` | `if (x > 0) { } else { }` | Condition must be `bool`; braces mandatory. |
| `switch` / `case` | `switch (c) { case .Red: { } else: { } }` | No fallthrough; enum switches are exhaustive or have `else:`; integer switches need `else:`. |
| `while` | `while (go) { }` | Pre-tested loop. `while (true)` with no `break` diverges. |
| `for` / `in` | `for (i in 0..n)`, `for (x in s)` | Range or slice iteration (elements by value). |
| `break` / `continue` | | Leave or restart the innermost loop, running `defer`s of exited scopes. |
| `return` | `return v;` | Evaluates the operand, runs `defer`s LIFO, returns. |
| `defer` | `defer close(fd);` | Runs at every exit of the enclosing block, LIFO. |
| `as` | `x as u64`, `p as (u8*)` | Explicit conversion. |
| `size_of` | `size_of(Node*)` | Size in bytes of a type, as `usize`. A grammar form because its argument is a type, so pointer and function types are allowed. |
| `true` `false` `null` | | Literals. `null` converts to any pointer type. |

---

## 3. Lexical Structure

- **Source:** UTF-8. Non-ASCII bytes appear only in comments and string literals. No BOM. Line endings `\n` or `\r\n`. Whitespace is space, tab, `\r` and `\n` only, and is insignificant; statements end with `;`. Digits are `0`-`9`, identifiers and char literals are ASCII.
- **Comments:** `// ...` to end of line. `/// ...` is a doc comment (lexed as a comment; tooling may attach it to the next declaration). No block comments. `//` inside a string is part of the string.
- **Identifiers:** `[A-Za-z_][A-Za-z0-9_]*`. Reserved words cannot be identifiers.
- **Integer literals:** decimal `123`, hex `0xFF`, binary `0b1010`, with `_` between digits (`1_000`). No suffixes. A literal's type comes from context (the other operand of a binary operator, the declared type, the parameter type), defaulting to `i32`. A literal that does not fit its type is a compile error. A leading `-` is range-checked together with the literal, so `-128` is a valid `i8`.
- **Float literals:** `1.5`, `1e9`, `2.5e-3`. A `.` belongs to a number only when a digit follows, so `0..16` lexes as `0` `..` `16`.
- **String literals:** `"..."` with escapes `\n \r \t \\ \" \0 \xNN`. Type `const u8[]`, length known, **not** NUL-terminated.
- **Char literals:** `'a'`, `'\n'`, `'\xNN'`. Type `u8`.
- **Operators (maximal munch):** `<<= >>= -> .. << >> <= >= == != && || += -= *= /= %= &= |= ^=` and `+ - * / % & | ^ ~ ! < > = . , ; : ( ) { } [ ]`. Because of maximal munch, `u8*= null` lexes `*=`: write `u8* = null`.

---

## 4. Operator Precedence (highest to lowest)

| Level | Operators | Assoc. |
| :-: | :--- | :--- |
| 1 | postfix: `.f`, `[i]`, `[a..b]`, `[T, U]` (generic application), `(args)`, `{fields}` | left |
| 2 | prefix: `-` `!` `~` `*` (dereference) `&` (address of) | right |
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

Bitwise operators bind tighter than comparison and looser than `+`/`-` (Rust's order, not C's), so `flags & MASK == 0` means `(flags & MASK) == 0` and `a + b << 2` means `(a + b) << 2`. Assignment is a statement, not an expression. There is no ternary operator. `*k as u64 * C` means `((*k) as u64) * C`.

---

## 5. Notes on the Surface Syntax

- **Generic arguments.** `[...]` after a name is the same token sequence in types and expressions: `Vec[i32]`, `Vec[u8].new(a)`, `Map[K, V]{ ... }`, `foo[i32](x)`, `foo[Pair[u8, u8]](x)`. In an expression the contents are an expression list, so `a[i]` and `Vec[i32]` both parse as an index; **semantic analysis** decides which (as in Go). Consequence: an explicit type argument in an expression must be *name-shaped* (names, qualified names, bracket suffixes such as `Vec[u8]`, `u8[4096]`). Pointer and function types (`u8*`, `fn(i32)`) cannot be written there; give them a `type` alias.
- **Bracket suffixes in types.** `T[]` is a slice, `T[16]` an array, `Vec[i32]` a generic application. All parse as `Ident "[" ... "]"`; semantic analysis tells them apart by whether the head names a generic type and whether the bracket holds a literal.
- **Conversions** are `expr as T`. The type after `as` is a name with optional bracket suffixes; a type ending in `*` must be parenthesized, `p as (u8*)`, so `x as u8 * y` is always a multiplication.
- **Pointer-to-function** types need parentheses: `(fn() -> u8)*`. (`fn() -> u8*` is a function returning a pointer.)
- **Errors** are ordinary values: an enum code, a negative integer, a null pointer, or a struct holding a status; there is no special syntax (`docs/decisions.md`, D-06).
- **Struct literals** are a postfix `{ f: v, ... }` on a type name: `Point{ x: 1, y: 2 }`, `Pair[i32, i32]{ a: 1, b: 2 }`. Every condition is parenthesized, so `{` after an expression never starts a block.
- **Array literals** are `[a, b, c]` and the repeat form `[v; n]`.
- **Ranges are half-open.** `a..b` is `[a, b)` in `for`, in slicing `a[lo..hi]`, and nowhere else; `a[..n]`, `a[n..]`, `a[..]` omit an end.
- **Semantic restrictions kept out of the grammar:** `..` in a slice index is valid on arrays and slices only; `defer` bodies may not contain `return`/`break`/`continue`; `else:` must be the last `case` arm; `break`/`continue` must be inside a loop; `return;` is valid only in a `void` function; a struct may not have a field and a method with the same name; `pub impl` is rejected.

---

## 6. Formal Grammar

Lexical classes `Ident`, `IntLit`, `FloatLit`, `StringLit`, `CharLit` are terminals (§3). Quoted strings are literal tokens.

```ebnf
Module          = { ImportDecl } { TopDecl } ;
ImportDecl      = "import" [ Ident ] StringLit ";" ;

TopDecl         = [ "pub" ] ( FnDecl | StructDecl | EnumDecl | TypeDecl
                            | ExternDecl | ConstDecl | ImplDecl ) ;

FnDecl          = "fn" Ident [ TypeParams ] "(" [ ParamList ] ")" [ "->" Type ] ( Block | ";" ) ;
FnSignature     = "fn" Ident "(" [ ParamList ] ")" [ "->" Type ] ;
ParamList       = Param [ "," [ ParamList ] ] ;
Param           = Ident ":" Type ;

StructDecl      = "struct" Ident [ TypeParams ] "{" { FieldDecl } "}" ;
FieldDecl       = [ "pub" ] Ident ":" Type ";" ;
EnumDecl        = "enum" Ident [ ":" Ident ] "{" [ EnumVariants ] "}" ;
EnumVariants    = EnumVariant [ "," [ EnumVariants ] ] ;
EnumVariant     = Ident [ "=" [ "-" ] IntLit ] ;
ImplDecl        = "impl" [ TypeParams ] Ident [ TypeArgs ] "{" { [ "pub" ] FnDecl } "}" ;
TypeDecl        = "type" Ident [ TypeParams ] "=" [ "distinct" ] Type ";" ;
ExternDecl      = "extern" StringLit "{" { FnSignature ";" } "}" ;
ConstDecl       = "const" Ident ":" Type "=" Expr ";" ;

TypeParams      = "[" Ident { "," Ident } "]" ;
TypeArgs        = "[" Type { "," Type } "]" ;

Type            = PrefixType ;
PrefixType      = "const" PrefixType
                | FnType
                | PostType ;
FnType          = "fn" "(" [ TypeList ] ")" [ "->" PrefixType ] ;
PostType        = TypeAtom { "*" | "[" Bracket } ;
Bracket         = "]" | BracketItem { "," BracketItem } "]" ;
BracketItem     = IntLit | Type ;
TypeAtom        = Ident [ "." Ident ]
                | "(" Type ")" ;
TypeList        = Type { "," Type } ;

Block           = "{" { Stmt } "}" ;
Stmt            = VarStmt | ConstDecl | IfStmt | SwitchStmt | WhileStmt | ForStmt
                | ReturnStmt | DeferStmt | BreakStmt | ContinueStmt
                | ExprStmt ;
VarStmt         = ( "let" | "mut" ) VarTarget "=" Expr ";" ;
VarTarget       = Ident [ ":" Type ] ;
IfStmt          = "if" "(" Expr ")" Block [ "else" ( IfStmt | Block ) ] ;
SwitchStmt      = "switch" "(" Expr ")" "{" { CaseArm } "}" ;
CaseArm         = "case" Expr { "," Expr } ":" Block
                | "else" ":" Block ;
WhileStmt       = "while" "(" Expr ")" Block ;
ForStmt         = "for" "(" Ident "in" Expr [ ".." Expr ] ")" Block ;
ReturnStmt      = "return" [ Expr ] ";" ;
DeferStmt       = "defer" ( Stmt | Block ) ;
BreakStmt       = "break" ";" ;
ContinueStmt    = "continue" ";" ;
ExprStmt        = Expr [ AssignOp Expr ] ";" ;
AssignOp        = "=" | "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;

Expr            = OrExpr ;
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
UnaryExpr       = ( "-" | "!" | "~" | "*" | "&" ) UnaryExpr
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
                | "size_of" "(" Type ")"
                | ArrayLit
                | "(" Expr ")" ;
ArrayLit        = "[" [ Expr [ ";" Expr | "," Expr { "," Expr } ] ] "]" ;
ExprList        = Expr [ "," [ ExprList ] ] ;
```

---

## 7. Verification

```bash
python3 tools/ll1.py spec/01-syntax.md                       # conflicts: 0
python3 tools/kparse.py spec/01-syntax.md litmus/*.kr tests/fail/*.kr
python3 tools/check_keywords.py spec/01-syntax.md            # box, grammar, parser agree
```

The checker proves that, for every nonterminal, alternatives have disjoint FIRST sets and nullable alternatives do not overlap FOLLOW. It does not check semantics; `litmus/` and `tests/fail/` exercise those once a compiler exists.
