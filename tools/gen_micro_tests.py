"""Generate the single-rule accept corpus under tests/run/.

The files are committed; this script exists so the corpus can be regenerated and reviewed.
Each file is one rule: `// SPEC: <chapter §n>`, `// EXPECT: exit 0 | trap`, a few lines of Candor.
Arithmetic edge cases come from a Python reference model of spec/02-types.md §4.
Usage: python3 tools/gen_micro_tests.py   (rewrites tests/run/)
"""
import os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "run")
tests = []   # (area, name, spec, expect, code)

def add(area, name, spec, expect, code):
    tests.append((area, name, spec, expect, code.strip("\n") + "\n"))

# ---------------------------------------------------------------- arithmetic model
INTS = [("i8", 8, True), ("i16", 16, True), ("i32", 32, True), ("i64", 64, True),
        ("u8", 8, False), ("u16", 16, False), ("u32", 32, False), ("u64", 64, False)]
def lo(b, s): return -(1 << (b - 1)) if s else 0
def hi(b, s): return (1 << (b - 1)) - 1 if s else (1 << b) - 1
def wrap(v, b, s):
    v &= (1 << b) - 1
    return v - (1 << b) if s and v >> (b - 1) else v
def lit(v): return str(v)

def binfn(t, op, name): return f"fn {name}(a: {t}, b: {t}) -> {t} {{ return a {op} b; }}\n"
def unfn(t, name): return f"fn {name}(a: {t}) -> {t} {{ return -a; }}\n"
def check(call, expect_lit): return f"    if ({call} != {expect_lit}) {{ return 1; }}\n    return 0;\n"
def runs(call): return f"    let r = {call};\n    return 0;\n"
def prog(defs, body): return defs + "\npub fn main() -> i32 {\n" + body + "}\n"

for t, b, sg in INTS:
    mn, mx = lo(b, sg), hi(b, sg)
    A = "02-types §4"
    # add / sub / mul
    add("arithmetic", f"{t}_add_overflow_traps", A, "trap", prog(binfn(t, "+", "add"), runs(f"add({mx}, 1)")))
    add("arithmetic", f"{t}_add_at_edge", A, "exit 0", prog(binfn(t, "+", "add"), check(f"add({mx - 1}, 1)", lit(mx))))
    if sg:
        add("arithmetic", f"{t}_sub_underflow_traps", A, "trap", prog(binfn(t, "-", "sub"), runs(f"sub({mn}, 1)")))
        add("arithmetic", f"{t}_sub_at_edge", A, "exit 0", prog(binfn(t, "-", "sub"), check(f"sub({mn + 1}, 1)", lit(mn))))
    else:
        add("arithmetic", f"{t}_sub_below_zero_traps", A, "trap", prog(binfn(t, "-", "sub"), runs("sub(0, 1)")))
        add("arithmetic", f"{t}_sub_to_zero", A, "exit 0", prog(binfn(t, "-", "sub"), check("sub(1, 1)", "0")))
    add("arithmetic", f"{t}_mul_overflow_traps", A, "trap", prog(binfn(t, "*", "mul"), runs(f"mul({mx}, 2)")))
    add("arithmetic", f"{t}_mul_at_edge", A, "exit 0", prog(binfn(t, "*", "mul"), check(f"mul({mx // 2}, 2)", lit(mx // 2 * 2))))
    # division / remainder
    add("arithmetic", f"{t}_div_by_zero_traps", A, "trap", prog(binfn(t, "/", "div"), runs("div(5, 0)")))
    add("arithmetic", f"{t}_rem_by_zero_traps", A, "trap", prog(binfn(t, "%", "rem"), runs("rem(5, 0)")))
    if sg:
        add("arithmetic", f"{t}_neg_min_traps", A, "trap", prog(unfn(t, "neg"), runs(f"neg({mn})")))
        add("arithmetic", f"{t}_neg_at_edge", A, "exit 0", prog(unfn(t, "neg"), check(f"neg({mn + 1})", lit(mx))))
        add("arithmetic", f"{t}_div_min_by_minus_one_traps", A, "trap", prog(binfn(t, "/", "div"), runs(f"div({mn}, -1)")))
        add("arithmetic", f"{t}_rem_min_by_minus_one_traps", A, "trap", prog(binfn(t, "%", "rem"), runs(f"rem({mn}, -1)")))
        add("arithmetic", f"{t}_div_truncates_toward_zero", A, "exit 0", prog(binfn(t, "/", "div"), check("div(-7, 2)", "-3")))
        add("arithmetic", f"{t}_rem_has_dividend_sign", A, "exit 0", prog(binfn(t, "%", "rem"), check("rem(-7, 2)", "-1")))
    else:
        add("arithmetic", f"{t}_div_rounds_down", A, "exit 0", prog(binfn(t, "/", "div"), check("div(7, 2)", "3")))
    # wrapping intrinsics
    W = "02-types §8"
    wf = lambda n: f"fn {n}(a: {t}, b: {t}) -> {t} {{ return wrapping_{n}(a, b); }}\n"
    add("arithmetic", f"{t}_wrapping_add", W, "exit 0", prog(wf("add"), check(f"add({mx}, 1)", lit(mn))))
    add("arithmetic", f"{t}_wrapping_sub", W, "exit 0", prog(wf("sub"), check(f"sub({mn}, 1)", lit(mx))))
    add("arithmetic", f"{t}_wrapping_mul", W, "exit 0", prog(wf("mul"), check(f"mul({mx}, {mx})", lit(wrap(mx * mx, b, sg)))))
    # shifts
    S = "02-types §4"
    shl = f"fn shl(a: {t}, n: {t}) -> {t} {{ return a << n; }}\nfn shr(a: {t}, n: {t}) -> {t} {{ return a >> n; }}\n"
    add("shifts", f"{t}_shl_amount_is_masked", S, "exit 0", prog(shl, check(f"shl(1, {b + 1})", "2")))
    add("shifts", f"{t}_shl_into_top_bit", S, "exit 0", prog(shl, check(f"shl(1, {b - 1})", lit(wrap(1 << (b - 1), b, sg)))))
    if sg:
        add("shifts", f"{t}_shl_negative_operand", S, "exit 0", prog(shl, check("shl(-1, 1)", "-2")))
        add("shifts", f"{t}_shl_negative_amount_masks", S, "exit 0", prog(shl, check("shl(1, -1)", lit(wrap(1 << (b - 1), b, sg)))))
        add("shifts", f"{t}_shr_is_arithmetic", S, "exit 0", prog(shl, check(f"shr({mn}, {b - 1})", "-1")))
    else:
        add("shifts", f"{t}_shr_is_logical", S, "exit 0", prog(shl, check(f"shr({mx}, {b - 1})", "1")))
        add("shifts", f"{t}_shr_amount_is_masked", S, "exit 0", prog(shl, check(f"shr({mx}, {b + 1})", lit(mx >> 1))))

# ---------------------------------------------------------------- hand-written micro tests
def main_only(body): return "pub fn main() -> i32 {\n" + body.strip("\n") + "\n    return 0;\n}\n"
def chk(*pairs):
    out = []
    for i, (cond) in enumerate(pairs, 1):
        out.append(f"    if (!({cond})) {{ return {i}; }}")
    return "\n".join(out) + "\n    return 0;\n"
def M(body): return "pub fn main() -> i32 {\n" + body.strip("\n") + "\n}\n"
def C(*conds): return M(chk(*conds))

H = add
# lexical
H("lexical", "hex_literal", "01-syntax §3", "exit 0", M("let a: u8 = 0xFF;\n" + chk("a == 255")))
H("lexical", "binary_literal", "01-syntax §3", "exit 0", M("let a: u8 = 0b1010;\n" + chk("a == 10")))
H("lexical", "underscore_separator", "01-syntax §3", "exit 0", M("let a: u32 = 1_000_000;\n" + chk("a == 1000000")))
H("lexical", "char_literal_is_u8", "01-syntax §3", "exit 0", M("let c: u8 = 'a';\n" + chk("c == 97")))
H("lexical", "char_escapes", "01-syntax §3", "exit 0", M(chk("'\\n' == 10", "'\\x41' == 65", "'\\0' == 0")))
H("lexical", "string_literal_length", "01-syntax §3", "exit 0", M(chk('"abc".len == 3')))
H("lexical", "string_escape_nul_counts", "01-syntax §3", "exit 0", M(chk('"a\\0b".len == 3')))
H("lexical", "float_literal_forms", "01-syntax §3", "exit 0", M("let a: f64 = 1e3;\nlet b: f64 = 2.5e-1;\n" + chk("a == 1000.0", "b == 0.25")))
H("lexical", "range_does_not_lex_as_float", "01-syntax §3", "exit 0", M("mut n: u32 = 0;\nfor (i in 0..16) { n += 1; }\n" + chk("n == 16")))
H("lexical", "comment_ignored", "01-syntax §3", "exit 0", "// leading comment\npub fn main() -> i32 {\n    return 0; // trailing\n}\n")
H("lexical", "negative_min_literal", "01-syntax §3", "exit 0", M("let a: i8 = -128;\nlet b: i64 = -9223372036854775808;\n" + chk("a == -128", "b < 0")))
H("lexical", "default_literal_type_i32", "01-syntax §3", "exit 0", M("let a = 5;\n" + chk("size_of(i32) == 4", "a == 5")))
# types
H("types", "size_of_scalars", "02-types §1", "exit 0", M(chk("size_of(i8) == 1", "size_of(i16) == 2", "size_of(i32) == 4", "size_of(i64) == 8", "size_of(f32) == 4", "size_of(f64) == 8", "size_of(bool) == 1")))
H("types", "size_of_pointers_and_isize", "02-types §1", "exit 0", M(chk("size_of(usize) == size_of(isize)", "size_of(u8*) == size_of(usize)", "size_of(const u8*) == size_of(usize)", "size_of(fn(i32) -> i32) == size_of(usize)")))
H("types", "size_of_slice_is_two_words", "02-types §1", "exit 0", M(chk("size_of(u8[]) == 2 * size_of(usize)")))
H("types", "bool_condition", "02-types §2", "exit 0", M("let t = true;\nlet f = false;\n" + chk("t && !f", "!(t && f)", "t || f")))
H("types", "float_nan_compares_unordered", "02-types §2", "exit 0",
  "fn nan() -> f64 { let z: f64 = 0.0; return z / z; }\n\n" + M(chk("nan() != nan()", "!(nan() == nan())", "!(nan() < 1.0)", "!(nan() > 1.0)")))
H("types", "float_division_by_zero_is_inf", "02-types §4", "exit 0",
  "fn inf() -> f64 { let z: f64 = 0.0; return 1.0 / z; }\n\n" + M(chk("inf() > 1.0e300")))
H("types", "alias_is_same_type", "02-types §1", "exit 0", "type Count = u32;\nfn id(x: u32) -> u32 { return x; }\n\n" + M("let c: Count = 7;\n" + chk("id(c) == 7")))
H("types", "const_item", "02-types §7", "exit 0", "const N: usize = 4;\nconst M: usize = N * 2 + 1;\n\n" + M(chk("N == 4", "M == 9")))
H("types", "const_in_array_length", "02-types §7", "exit 0", "const N: usize = 3;\n\n" + M("let a: u8[N] = [1, 2, 3];\n" + chk("a[2] == 3", "size_of(u8[N]) == 3")))
H("types", "const_string_slice", "02-types §7", "exit 0", 'const GREETING: const u8[] = "hi";\n\n' + M(chk("GREETING.len == 2", "GREETING[0] == 'h'")))
# conversions
CV = "02-types §3"
H("conversions", "widen_signed_extends", CV, "exit 0", "fn w(x: i8) -> i32 { return x as i32; }\n\n" + C("w(-1) == -1", "w(-128) == -128", "w(127) == 127"))
H("conversions", "widen_unsigned_zero_extends", CV, "exit 0", "fn w(x: u8) -> i32 { return x as i32; }\n\n" + C("w(255) == 255"))
H("conversions", "signed_to_wider_unsigned_uses_source_sign", CV, "exit 0", "fn w(x: i8) -> u32 { return x as u32; }\n\n" + C("w(-1) == 0xFFFFFFFF"))
H("conversions", "minus_one_as_usize_is_all_ones", CV, "exit 0", "fn w(x: i32) -> u64 { return x as u64; }\n\n" + C("w(-1) == 0xFFFFFFFFFFFFFFFF"))
H("conversions", "narrow_truncates", CV, "exit 0", "fn n(x: u16) -> u8 { return x as u8; }\nfn m(x: i64) -> i8 { return x as i8; }\n\n" + C("n(300) == 44", "m(511) == -1", "m(256) == 0"))
H("conversions", "same_width_reinterprets", CV, "exit 0", "fn a(x: u8) -> i8 { return x as i8; }\nfn b(x: i8) -> u8 { return x as u8; }\n\n" + C("a(200) == -56", "b(-1) == 255"))
H("conversions", "int_to_float", CV, "exit 0", "fn f(x: i32) -> f64 { return x as f64; }\n\n" + C("f(3) == 3.0", "f(-2) == -2.0"))
H("conversions", "float_to_int_truncates_toward_zero", CV, "exit 0", "fn t(x: f64) -> i32 { return x as i32; }\n\n" + C("t(3.9) == 3", "t(-3.9) == -3"))
H("conversions", "float_to_int_saturates_high", CV, "exit 0", "fn t(x: f64) -> u8 { return x as u8; }\nfn u(x: f64) -> i32 { return x as i32; }\n\n" + C("t(300.0) == 255", "u(1.0e20) == 2147483647"))
H("conversions", "float_to_int_saturates_low", CV, "exit 0", "fn t(x: f64) -> u8 { return x as u8; }\nfn u(x: f64) -> i32 { return x as i32; }\n\n" + C("t(-5.0) == 0", "u(-1.0e20) == -2147483648"))
H("conversions", "nan_to_int_is_zero", CV, "exit 0", "fn t(x: f64) -> i32 { return x as i32; }\nfn nan() -> f64 { let z: f64 = 0.0; return z / z; }\n\n" + C("t(nan()) == 0"))
H("conversions", "float_to_float", CV, "exit 0", "fn t(x: f64) -> f32 { return x as f32; }\nfn u(x: f32) -> f64 { return x as f64; }\n\n" + C("t(0.5) == 0.5", "u(0.25) == 0.25"))
H("conversions", "bool_to_int", CV, "exit 0", "fn t(x: bool) -> u8 { return x as u8; }\n\n" + C("t(true) == 1", "t(false) == 0"))
H("conversions", "enum_to_int", CV, "exit 0", "enum Color { Red, Green, Blue }\n\n" + C("(Color.Blue as i32) == 2", "(Color.Red as u8) == 0"))
H("conversions", "int_to_enum_in_range", CV, "exit 0", "enum Color { Red, Green, Blue }\nfn pick(n: i32) -> Color { return n as Color; }\n\n" + M("switch (pick(1)) { case .Green: { return 0; } else: { return 1; } }"))
H("conversions", "slice_to_const_slice", CV, "exit 0", "fn total(s: const u8[]) -> u32 { mut t: u32 = 0; for (x in s) { t += x as u32; } return t; }\n\n" + M("mut a: u8[3] = [1, 2, 3];\n" + chk("total(a[..]) == 6")))
H("conversions", "pointer_to_const_pointer", CV, "exit 0", "fn read(p: const i32*) -> i32 { return *p; }\n\n" + M("mut x: i32 = 9;\n" + chk("read(&x) == 9")))
H("conversions", "null_converts_to_any_pointer", CV, "exit 0", "struct S { a: i32; }\n\n" + M("let p: u8* = null;\nlet q: S* = null;\nlet r: fn(i32) -> i32 = null;\n" + chk("p == null", "q == null")))
H("conversions", "pointer_cast_round_trip", CV, "exit 0", M("mut x: u32 = 0x01020304;\nlet bytes = &x as (u8*);\nlet back = bytes as (u32*);\n" + chk("*back == 0x01020304")))
H("conversions", "pointer_to_integer_and_back", CV, "exit 0", M("mut x: i32 = 5;\nlet addr = &x as usize;\nlet p = addr as (i32*);\n" + chk("*p == 5", "addr != 0")))
H("conversions", "const_pointer_cast_away", CV, "exit 0", M("mut x: i32 = 1;\nlet cp: const i32* = &x;\nlet p = cp as (i32*);\n*p = 4;\n" + chk("x == 4")))
# pointers
PT = "02-types §4"
H("pointers", "address_of_and_deref", PT, "exit 0", M("mut x: i32 = 3;\nlet p = &x;\n*p = 8;\n" + chk("x == 8", "*p == 8")))
H("pointers", "write_through_parameter", PT, "exit 0", "fn set(p: i32*, v: i32) { *p = v; }\n\n" + M("mut x: i32 = 0;\nset(&x, 11);\n" + chk("x == 11")))
H("pointers", "swap_through_pointers", PT, "exit 0", "fn swap(a: i32*, b: i32*) { let t = *a; *a = *b; *b = t; }\n\n" + M("mut a: i32 = 1;\nmut b: i32 = 2;\nswap(&a, &b);\n" + chk("a == 2", "b == 1")))
H("pointers", "field_access_through_pointer", PT, "exit 0", "struct P { x: i32; y: i32; }\nfn bump(p: P*) { p.x += 1; p.y = p.x * 2; }\n\n" + M("mut v = P{ x: 1, y: 0 };\nbump(&v);\n" + chk("v.x == 2", "v.y == 4")))
H("pointers", "address_of_field", PT, "exit 0", "struct P { x: i32; y: i32; }\n\n" + M("mut v = P{ x: 1, y: 2 };\nlet p = &v.y;\n*p = 9;\n" + chk("v.y == 9", "v.x == 1")))
H("pointers", "address_of_array_element", PT, "exit 0", M("mut a: i32[3] = [1, 2, 3];\nlet p = &a[1];\n*p = 20;\n" + chk("a[1] == 20", "a[0] == 1")))
H("pointers", "pointer_equality", PT, "exit 0", M("mut x: i32 = 0;\nmut y: i32 = 0;\nlet p = &x;\nlet q = &x;\nlet r = &y;\n" + chk("p == q", "p != r")))
H("pointers", "pointer_to_pointer", PT, "exit 0", M("mut x: i32 = 1;\nmut p = &x;\nlet pp = &p;\n**pp = 6;\n" + chk("x == 6")))
H("pointers", "slice_from_pointer_and_length", "02-types §8", "exit 0", M("mut a: u8[4] = [5, 6, 7, 8];\nlet s = slice(&a[0], 4);\n" + chk("s.len == 4", "s[2] == 7")))
H("pointers", "slice_ptr_field_is_element_address", "02-types §5", "exit 0", M("mut a: u8[4] = [5, 6, 7, 8];\nlet s = a[..];\n" + chk("s.ptr == &a[0]")))
H("pointers", "function_pointer_call", "02-types §1", "exit 0", "fn twice(x: i32) -> i32 { return x * 2; }\n\n" + M("let f: fn(i32) -> i32 = twice;\n" + chk("f(21) == 42")))
H("pointers", "function_pointer_as_argument", "02-types §1", "exit 0", "fn twice(x: i32) -> i32 { return x * 2; }\nfn apply(f: fn(i32) -> i32, v: i32) -> i32 { return f(v); }\n\n" + C("apply(twice, 4) == 8"))
H("pointers", "function_pointer_field", "02-types §5", "exit 0", "struct Op { f: fn(i32) -> i32; }\nfn inc(x: i32) -> i32 { return x + 1; }\n\n" + M("let o = Op{ f: inc };\n" + chk("o.f(1) == 2")))
# slices
SL = "02-types §4"
H("slices", "index_in_range", SL, "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet s = a[..];\n" + chk("s[0] == 1", "s[3] == 4")))
H("slices", "index_at_length_traps", SL, "trap", "fn at(s: const u8[], i: usize) -> u8 { return s[i]; }\n\n" + M("mut a: u8[4] = [1, 2, 3, 4];\nlet v = at(a[..], 4);"))
H("slices", "array_index_out_of_range_traps", SL, "trap", "fn at(a: u8[4], i: usize) -> u8 { return a[i]; }\n\n" + M("let v = at([1, 2, 3, 4], 9);"))
H("slices", "slice_full", SL, "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet s = a[..];\n" + chk("s.len == 4")))
H("slices", "slice_range_length", SL, "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet s = a[1..3];\n" + chk("s.len == 2", "s[0] == 2", "s[1] == 3")))
H("slices", "slice_open_ends", SL, "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet p = a[..2];\nlet q = a[2..];\n" + chk("p.len == 2", "q.len == 2", "q[0] == 3")))
H("slices", "empty_slice_at_start", SL, "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet s = a[0..0];\n" + chk("s.len == 0")))
H("slices", "empty_slice_at_length_is_valid", SL, "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet s = a[4..4];\n" + chk("s.len == 0")))
H("slices", "slice_high_past_length_traps", SL, "trap", "fn cut(s: const u8[], lo: usize, hi: usize) -> usize { return s[lo..hi].len; }\n\n" + M("mut a: u8[4] = [1, 2, 3, 4];\nlet n = cut(a[..], 0, 5);"))
H("slices", "slice_low_above_high_traps", SL, "trap", "fn cut(s: const u8[], lo: usize, hi: usize) -> usize { return s[lo..hi].len; }\n\n" + M("mut a: u8[4] = [1, 2, 3, 4];\nlet n = cut(a[..], 3, 2);"))
H("slices", "slice_of_slice", SL, "exit 0", M("mut a: u8[6] = [1, 2, 3, 4, 5, 6];\nlet s = a[1..5];\nlet t = s[1..3];\n" + chk("t.len == 2", "t[0] == 3")))
H("slices", "slice_of_empty_null_slice_is_valid", SL, "exit 0", M("let e = slice(null as (u8*), 0);\nlet s = e[..];\n" + chk("s.len == 0")))
H("slices", "slice_write_through", "02-types §5", "exit 0", "fn zero(s: u8[]) { for (i in 0..s.len) { s[i] = 0; } }\n\n" + M("mut a: u8[3] = [1, 2, 3];\nzero(a[..]);\n" + chk("a[0] == 0", "a[2] == 0")))
H("slices", "slice_is_a_copyable_value", "02-types §5", "exit 0", "struct View { s: const u8[]; }\n\n" + M("mut a: u8[2] = [7, 8];\nlet v = View{ s: a[..] };\nlet w = v;\n" + chk("w.s[1] == 8", "v.s.len == 2")))
H("slices", "slice_returned_from_function", "02-types §5", "exit 0", "fn tail(s: const u8[]) -> const u8[] { return s[1..]; }\n\n" + M("mut a: u8[3] = [1, 2, 3];\nlet t = tail(a[..]);\n" + chk("t.len == 2", "t[0] == 2")))
H("slices", "for_over_slice_is_by_value", "01-syntax §2", "exit 0", M("mut a: u8[3] = [1, 2, 3];\nmut t: u32 = 0;\nfor (x in a[..]) { t += x as u32; }\n" + chk("t == 6")))
H("slices", "for_range_bounds", "01-syntax §2", "exit 0", M("mut t: i32 = 0;\nfor (i in 2..5) { t += i; }\n" + chk("t == 9")))
H("slices", "empty_range_does_not_loop", "01-syntax §2", "exit 0", M("mut t: u32 = 0;\nfor (i in 3..3) { t += 1; }\n" + chk("t == 0")))
# arrays
AR = "02-types §5"
H("arrays", "array_literal_and_index", AR, "exit 0", M("let a: u8[3] = [10, 20, 30];\n" + chk("a[0] == 10", "a[2] == 30")))
H("arrays", "array_repeat_literal", AR, "exit 0", M("let a: u8[5] = [7; 5];\n" + chk("a[0] == 7", "a[4] == 7")))
H("arrays", "array_assignment_copies", AR, "exit 0", M("mut a: u8[2] = [1, 2];\nmut b = a;\nb[0] = 9;\n" + chk("a[0] == 1", "b[0] == 9")))
H("arrays", "array_passed_by_value", AR, "exit 0", "fn clobber(a: u8[2]) -> u8 { mut b = a; b[0] = 99; return b[0]; }\n\n" + M("let a: u8[2] = [1, 2];\n" + chk("clobber(a) == 99", "a[0] == 1")))
H("arrays", "array_returned_by_value", AR, "exit 0", "fn make() -> u8[3] { return [4, 5, 6]; }\n\n" + M("let a = make();\n" + chk("a[1] == 5")))
H("arrays", "array_inside_struct_copies", AR, "exit 0", "struct Row { c: u8[3]; }\n\n" + M("mut r = Row{ c: [1, 2, 3] };\nmut s = r;\ns.c[0] = 8;\n" + chk("r.c[0] == 1", "s.c[0] == 8")))
H("arrays", "two_dimensional_array", AR, "exit 0", M("let m: u8[3][3] = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];\n" + chk("m[1][2] == 6", "m[2][0] == 7")))
H("arrays", "array_size_of", AR, "exit 0", M(chk("size_of(u8[4]) == 4", "size_of(i32[3]) == 12", "size_of(u16[2][2]) == 8")))
H("arrays", "array_literal_inferred_length", AR, "exit 0", M("let a = [1, 2, 3, 4];\n" + chk("a[3] == 4")))
# structs
ST = "02-types §5"
H("structs", "literal_and_field_read", ST, "exit 0", "struct P { x: i32; y: i32; }\n\n" + M("let p = P{ x: 3, y: 4 };\n" + chk("p.x == 3", "p.y == 4")))
H("structs", "nested_struct", ST, "exit 0", "struct In { v: u8; }\nstruct Out { a: In; b: In; }\n\n" + M("let o = Out{ a: In{ v: 1 }, b: In{ v: 2 } };\n" + chk("o.a.v == 1", "o.b.v == 2")))
H("structs", "assignment_copies", ST, "exit 0", "struct P { x: i32; }\n\n" + M("mut a = P{ x: 1 };\nmut b = a;\nb.x = 5;\n" + chk("a.x == 1", "b.x == 5")))
H("structs", "passed_and_returned_by_value", ST, "exit 0", "struct P { x: i32; }\nfn bump(p: P) -> P { mut q = p; q.x += 1; return q; }\n\n" + M("let a = P{ x: 1 };\nlet b = bump(a);\n" + chk("a.x == 1", "b.x == 2")))
H("structs", "field_order_and_padding_u8_u32", ST, "exit 0", "struct S { a: u8; b: u32; }\n\n" + C("size_of(S) == 8"))
H("structs", "tail_padding", ST, "exit 0", "struct S { a: u32; b: u8; }\n\n" + C("size_of(S) == 8"))
H("structs", "no_padding_when_aligned", ST, "exit 0", "struct S { a: u8; b: u8; c: u16; }\n\n" + C("size_of(S) == 4"))
H("structs", "array_field_layout", ST, "exit 0", "struct S { xs: u8[3]; y: u32; }\n\n" + C("size_of(S) == 8"))
H("structs", "empty_struct_has_size_one", ST, "exit 0", "struct E { }\n\n" + C("size_of(E) == 1"))
H("structs", "empty_struct_field_takes_a_byte", ST, "exit 0", "struct E { }\nstruct W { e: E; x: u8; }\n\n" + C("size_of(W) == 2"))
H("structs", "method_takes_address_of_receiver", ST, "exit 0", "struct Counter { n: u32; }\nimpl Counter { pub fn inc(self: Counter*) { self.n += 1; } }\n\n" + M("mut c = Counter{ n: 0 };\nc.inc();\nc.inc();\n" + chk("c.n == 2")))
H("structs", "method_through_pointer", ST, "exit 0", "struct Counter { n: u32; }\nimpl Counter { pub fn inc(self: Counter*) { self.n += 1; } }\nfn twice(c: Counter*) { c.inc(); c.inc(); }\n\n" + M("mut c = Counter{ n: 0 };\ntwice(&c);\n" + chk("c.n == 2")))
H("structs", "method_by_value_receiver", ST, "exit 0", "struct P { x: i32; }\nimpl P { pub fn get(self: P) -> i32 { return self.x; } }\n\n" + M("let p = P{ x: 6 };\n" + chk("p.get() == 6")))
H("structs", "static_function_in_impl", ST, "exit 0", "struct P { x: i32; }\nimpl P { pub fn origin() -> P { return P{ x: 0 }; } }\n\n" + M("let p = P.origin();\n" + chk("p.x == 0")))
H("structs", "assign_field_of_mut_struct", ST, "exit 0", "struct P { x: i32; y: i32; }\n\n" + M("mut p = P{ x: 1, y: 2 };\np.x = 10;\np.y += 5;\n" + chk("p.x == 10", "p.y == 7")))
# enums
EN = "02-types §5"
H("enums", "default_numbering", EN, "exit 0", "enum E { A, B, C }\n\n" + C("(E.A as i32) == 0", "(E.B as i32) == 1", "(E.C as i32) == 2"))
H("enums", "explicit_values_continue", EN, "exit 0", "enum E { A = 5, B, C = 10, D }\n\n" + C("(E.A as i32) == 5", "(E.B as i32) == 6", "(E.D as i32) == 11"))
H("enums", "negative_value", EN, "exit 0", "enum E { A = -1, B }\n\n" + C("(E.A as i32) == -1", "(E.B as i32) == 0"))
H("enums", "backing_type_sets_size", EN, "exit 0", "enum S : u8 { A, B }\nenum L : u64 { A, B }\nenum D { A, B }\n\n" + C("size_of(S) == 1", "size_of(L) == 8", "size_of(D) == 4"))
H("enums", "switch_all_variants", EN, "exit 0", "enum E { A, B, C }\nfn f(e: E) -> i32 { switch (e) { case .A: { return 1; } case .B: { return 2; } case .C: { return 3; } } }\n\n" + C("f(E.A) == 1", "f(E.C) == 3"))
H("enums", "switch_else_arm", EN, "exit 0", "enum E { A, B, C }\nfn f(e: E) -> i32 { switch (e) { case .A: { return 1; } else: { return 9; } } }\n\n" + C("f(E.A) == 1", "f(E.C) == 9"))
H("enums", "switch_multiple_labels", EN, "exit 0", "enum E { A, B, C }\nfn f(e: E) -> i32 { switch (e) { case .A, .B: { return 1; } case .C: { return 2; } } }\n\n" + C("f(E.B) == 1", "f(E.C) == 2"))
H("enums", "switch_qualified_variant", EN, "exit 0", "enum E { A, B }\nfn f(e: E) -> i32 { switch (e) { case E.A: { return 1; } case E.B: { return 2; } } }\n\n" + C("f(E.B) == 2"))
H("enums", "switch_on_integer_needs_else", EN, "exit 0", "fn f(x: i32) -> i32 { switch (x) { case 1: { return 10; } case 2, 3: { return 20; } else: { return 0; } } }\n\n" + C("f(1) == 10", "f(3) == 20", "f(7) == 0"))
H("enums", "switch_has_no_fallthrough", EN, "exit 0", "fn f(x: i32) -> i32 { mut n: i32 = 0; switch (x) { case 1: { n += 1; } case 2: { n += 10; } else: { n += 100; } } return n; }\n\n" + C("f(1) == 1", "f(2) == 10"))
H("enums", "switch_on_char", EN, "exit 0", "fn f(c: u8) -> i32 { switch (c) { case 'a': { return 1; } case 'b': { return 2; } else: { return 0; } } }\n\n" + C("f('b') == 2", "f('z') == 0"))
H("enums", "out_of_range_enum_switch_traps", EN, "trap", "enum E { A, B }\nfn pick(n: i32) -> E { return n as E; }\nfn f(e: E) -> i32 { switch (e) { case .A: { return 1; } case .B: { return 2; } } }\n\n" + M("let r = f(pick(7));"))
H("enums", "enum_equality", EN, "exit 0", "enum E { A, B }\n\n" + C("E.A == E.A", "E.A != E.B"))
# fall-through rule
FT = "01-syntax §5"
H("returns", "if_else_both_return", FT, "exit 0", "fn f(x: i32) -> i32 { if (x > 0) { return 1; } else { return 2; } }\n\n" + C("f(1) == 1", "f(-1) == 2"))
H("returns", "switch_with_else_all_return", FT, "exit 0", "fn f(x: i32) -> i32 { switch (x) { case 1: { return 10; } else: { return 0; } } }\n\n" + C("f(1) == 10", "f(5) == 0"))
H("returns", "exhaustive_enum_switch_all_return", FT, "exit 0", "enum E { A, B }\nfn f(e: E) -> i32 { switch (e) { case .A: { return 1; } case .B: { return 2; } } }\n\n" + C("f(E.B) == 2"))
H("returns", "while_true_without_break", FT, "exit 0", "fn f(x: i32) -> i32 { while (true) { if (x > 0) { return x; } return 0; } }\n\n" + C("f(3) == 3"))
H("returns", "block_ending_in_return", FT, "exit 0", "fn f() -> i32 { { return 4; } }\n\n" + C("f() == 4"))
H("returns", "return_after_branching", FT, "exit 0", "fn f(x: i32) -> i32 { if (x > 0) { return 1; } return 0; }\n\n" + C("f(1) == 1", "f(0) == 0"))
# generics
GN = "02-types §6"
H("generics", "identity_function", GN, "exit 0", "fn id[T](x: T) -> T { return x; }\n\n" + C("id[i32](5) == 5", "id[u8](200) == 200"))
H("generics", "generic_struct", GN, "exit 0", "struct Pair[A, B] { a: A; b: B; }\n\n" + M("let p = Pair[u8, i32]{ a: 1, b: -2 };\n" + chk("p.a == 1", "p.b == -2")))
H("generics", "distinct_instantiations_are_distinct_types", GN, "exit 0", "struct Pair[A, B] { a: A; b: B; }\n\n" + C("size_of(Pair[u8, u8]) == 2", "size_of(Pair[u64, u64]) == 16", "size_of(Pair[u8, u32]) == 8"))
H("generics", "generic_body_uses_operators", GN, "exit 0", "fn add[T](a: T, b: T) -> T { return a + b; }\n\n" + C("add[i32](2, 3) == 5", "add[f64](0.5, 0.25) == 0.75"))
H("generics", "generic_with_function_pointer", GN, "exit 0", "fn map1[T](x: T, f: fn(T) -> T) -> T { return f(x); }\nfn inc(x: i32) -> i32 { return x + 1; }\n\n" + C("map1[i32](4, inc) == 5"))
H("generics", "generic_impl_method", GN, "exit 0", "struct Box[T] { v: T; }\nimpl[T] Box[T] { pub fn get(self: Box[T]) -> T { return self.v; } }\n\n" + M("let b = Box[u16]{ v: 9 };\n" + chk("b.get() == 9")))
H("generics", "generic_impl_mutating_method", GN, "exit 0", "struct Box[T] { v: T; }\nimpl[T] Box[T] { pub fn set(self: Box[T]*, x: T) { self.v = x; } }\n\n" + M("mut b = Box[i32]{ v: 1 };\nb.set(8);\n" + chk("b.v == 8")))
H("generics", "generic_static_function", GN, "exit 0", "struct Box[T] { v: T; }\nimpl[T] Box[T] { pub fn make(x: T) -> Box[T] { return Box[T]{ v: x }; } }\n\n" + M("let b = Box[u8].make(3);\n" + chk("b.v == 3")))
H("generics", "nested_generic_types", GN, "exit 0", "struct Box[T] { v: T; }\nstruct Pair[A, B] { a: A; b: B; }\n\n" + M("let x = Box[Pair[u8, u8]]{ v: Pair[u8, u8]{ a: 1, b: 2 } };\n" + chk("x.v.b == 2")))
H("generics", "generic_alias", GN, "exit 0", "struct Pair[A, B] { a: A; b: B; }\ntype IntPair[T] = Pair[T, T];\n\n" + M("let p = IntPair[u8]{ a: 1, b: 2 };\n" + chk("p.a + p.b == 3")))
H("generics", "generic_size_of_parameter", GN, "exit 0", "fn bytes[T](n: usize) -> usize { return n * size_of(T); }\n\n" + C("bytes[u32](3) == 12", "bytes[u8](3) == 3"))
H("generics", "generic_over_pointer_type", GN, "exit 0", "type BytePtr = u8*;\nfn id[T](x: T) -> T { return x; }\n\n" + M("mut b: u8 = 1;\nlet p = id[BytePtr](&b);\n" + chk("*p == 1")))
# distinct
DT = "02-types §3.1"
H("distinct", "literal_initializes", DT, "exit 0", "type Meters = distinct u32;\n\n" + M("let m: Meters = 40;\n" + chk("m == 40")))
H("distinct", "arithmetic_inherited", DT, "exit 0", "type Meters = distinct u32;\n\n" + M("let a: Meters = 40;\nlet b: Meters = 2;\n" + chk("a + b == 42", "a - b == 38", "a * b == 80", "a / b == 20", "a % b == 0")))
H("distinct", "overflow_still_traps", DT, "trap", "type Meters = distinct u32;\nfn big() -> Meters { return 4294967295; }\n\n" + M("let r = big() + 1;"))
H("distinct", "comparison_yields_bool", DT, "exit 0", "type Meters = distinct u32;\n\n" + M("let a: Meters = 1;\nlet b: Meters = 2;\n" + chk("a < b", "b >= a", "a != b")))
H("distinct", "bitwise_and_shift", DT, "exit 0", "type Flags = distinct u8;\n\n" + M("let a: Flags = 12;\nlet b: Flags = 10;\nlet n: Flags = 1;\n" + chk("(a & b) == 8", "(a | b) == 14", "(a ^ b) == 6", "(a << n) == 24")))
H("distinct", "explicit_conversions_both_ways", DT, "exit 0", "type Meters = distinct u32;\n\n" + M("let m: Meters = 7;\nlet raw = m as u32;\nlet back = raw as Meters;\n" + chk("raw == 7", "back == m")))
H("distinct", "wrapping_intrinsics_accept_distinct", DT, "exit 0", "type Id = distinct u8;\nfn w(a: Id, b: Id) -> Id { return wrapping_add(a, b); }\n\n" + M("let m: Id = 255;\n" + chk("w(m, 2) == 1")))
H("distinct", "index_needs_usize_conversion", DT, "exit 0", "type Handle = distinct usize;\n\n" + M("mut a: u8[3] = [4, 5, 6];\nlet h: Handle = 1;\n" + chk("a[h as usize] == 5")))
H("distinct", "distinct_struct_field", DT, "exit 0", "type Meters = distinct u32;\nstruct Leg { d: Meters; }\n\n" + M("let l = Leg{ d: 10 };\n" + chk("l.d == 10")))
H("distinct", "generic_over_distinct", DT, "exit 0", "type Meters = distinct u32;\nfn add[T](a: T, b: T) -> T { return a + b; }\n\n" + M("let a: Meters = 1;\nlet b: Meters = 2;\n" + chk("add[Meters](a, b) == 3")))
H("distinct", "distinct_has_base_size", DT, "exit 0", "type Meters = distinct u32;\ntype P = distinct u8*;\n\n" + C("size_of(Meters) == 4", "size_of(P) == size_of(usize)"))
H("distinct", "distinct_pointer_deref", DT, "exit 0", "type P = distinct i32*;\n\n" + M("mut x: i32 = 5;\nlet p = &x as P;\n" + chk("*p == 5")))
H("distinct", "distinct_of_distinct_is_new_type", DT, "exit 0", "type A = distinct u32;\ntype B = distinct u32;\n\n" + M("let a: A = 5;\nlet b = a as u32 as B;\n" + chk("b == 5")))
# defer
DF = "03-memory §4"
H("defer", "runs_at_end_of_block", DF, "exit 0", M("mut n: u32 = 0;\n{ defer n = 7; }\n" + chk("n == 7")))
H("defer", "runs_lifo", DF, "exit 0", M("mut log: u32 = 0;\n{ defer log = log * 10 + 1; defer log = log * 10 + 2; }\n" + chk("log == 21")))
H("defer", "runs_on_return", DF, "exit 0", "fn f(out: u32*) { defer *out = 9; return; }\n\n" + M("mut n: u32 = 0;\nf(&n);\n" + chk("n == 9")))
H("defer", "return_value_evaluated_before_defer", DF, "exit 0", "fn f() -> u32 { mut x: u32 = 5; defer x = 99; return x; }\n\n" + C("f() == 5"))
H("defer", "sees_variable_not_snapshot", DF, "exit 0", "fn f(out: u32*) { mut x: u32 = 1; defer *out = x; x = 5; }\n\n" + M("mut n: u32 = 0;\nf(&n);\n" + chk("n == 5")))
H("defer", "runs_each_loop_iteration", DF, "exit 0", M("mut n: u32 = 0;\nfor (i in 0..3) { defer n += 1; }\n" + chk("n == 3")))
H("defer", "runs_on_break", DF, "exit 0", M("mut n: u32 = 0;\nwhile (true) { defer n += 1; break; }\n" + chk("n == 1")))
H("defer", "runs_on_continue", DF, "exit 0", M("mut n: u32 = 0;\nfor (i in 0..3) { defer n += 1; continue; }\n" + chk("n == 3")))
H("defer", "block_form", DF, "exit 0", M("mut n: u32 = 0;\n{ defer { n += 1; n += 1; } }\n" + chk("n == 2")))
H("defer", "skipped_when_not_reached", DF, "exit 0", "fn f(early: bool, out: u32*) { if (early) { return; } defer *out = 7; }\n\n" + M("mut a: u32 = 0;\nmut b: u32 = 0;\nf(true, &a);\nf(false, &b);\n" + chk("a == 0", "b == 7")))
H("defer", "nested_blocks_run_inner_first", DF, "exit 0", M("mut log: u32 = 0;\n{ defer log = log * 10 + 2;\n  { defer log = log * 10 + 1; }\n}\n" + chk("log == 12")))
H("defer", "break_runs_only_inner_scopes", DF, "exit 0", M("mut log: u32 = 0;\ndefer log = 0;\nwhile (true) { defer log += 1; break; }\n" + chk("log == 1")))
H("defer", "abort_skips_defer", DF, "trap", "fn boom(z: u32) -> u32 { return 1 / z; }\n\n" + M("mut n: u32 = 0;\ndefer n = 1;\nlet r = boom(0);"))
H("defer", "runs_in_called_function_before_caller_continues", DF, "exit 0", "fn f(out: u32*) { defer *out = *out * 10 + 2; *out = *out * 10 + 1; }\n\n" + M("mut n: u32 = 0;\nf(&n);\n" + chk("n == 12")))
# scope
SC = "03-memory §5"
H("scope", "inner_block_shadows_outer", SC, "exit 0", M("let x: i32 = 1;\n{ let x: i32 = 2; if (x != 2) { return 1; } }\n" + chk("x == 1")))
H("scope", "initializer_sees_outer_binding", SC, "exit 0", M("let x: i32 = 5;\n{ let x: i32 = x + 1; if (x != 6) { return 1; } }\n" + chk("x == 5")))
H("scope", "initializer_sees_parameter", SC, "exit 0", "fn f(x: i32) -> i32 { { let x: i32 = x * 2; return x; } }\n\n" + C("f(4) == 8"))
H("scope", "for_variable_scoped_to_loop", SC, "exit 0", M("mut n: i32 = 0;\nfor (i in 0..3) { n += i; }\nlet i: u32 = 100;\n" + chk("n == 3", "i == 100")))
H("scope", "case_body_can_shadow", SC, "exit 0", "fn f(x: i32) -> i32 { switch (x) { case 1: { let x: i32 = 50; return x; } else: { return x; } } }\n\n" + C("f(1) == 50", "f(2) == 2"))
H("scope", "shadow_in_loop_body", SC, "exit 0", M("let x: i32 = 1;\nmut n: i32 = 0;\nfor (i in 0..3) { let x: i32 = 10; n += x; }\n" + chk("n == 30", "x == 1")))
H("scope", "declaration_order_inside_block", SC, "exit 0", M("let a: i32 = 1;\nlet b: i32 = a + 1;\nlet c: i32 = b + 1;\n" + chk("c == 3")))
H("scope", "top_level_items_in_any_order", "05-modules §4", "exit 0", "fn a() -> i32 { return b() + 1; }\nfn b() -> i32 { return 1; }\n\n" + C("a() == 2"))
H("scope", "mutual_recursion", "05-modules §4", "exit 0", "fn even(n: u32) -> bool { if (n == 0) { return true; } return odd(n - 1); }\nfn odd(n: u32) -> bool { if (n == 0) { return false; } return even(n - 1); }\n\n" + C("even(10)", "odd(7)"))
H("scope", "type_declared_after_use", "05-modules §4", "exit 0", "fn f() -> Late { return Late{ x: 1 }; }\nstruct Late { x: i32; }\n\n" + C("f().x == 1"))
# eval order
EV = "02-types §4"
MK = "fn mark(log: u32*, d: u32) -> u32 { *log = *log * 10 + d; return d; }\n"
H("eval_order", "call_arguments_left_to_right", EV, "exit 0", MK + "fn pair(a: u32, b: u32) -> u32 { return a * 100 + b; }\n\n" + M("mut log: u32 = 0;\nlet r = pair(mark(&log, 1), mark(&log, 2));\n" + chk("log == 12", "r == 102")))
H("eval_order", "binary_operands_left_to_right", EV, "exit 0", MK + "\n" + M("mut log: u32 = 0;\nlet r = mark(&log, 1) + mark(&log, 2);\n" + chk("log == 12", "r == 3")))
H("eval_order", "earlier_operand_value_is_captured", EV, "exit 0", "fn bump(p: i32*) -> i32 { *p = 10; return 2; }\nfn sum(a: i32, b: i32) -> i32 { return a + b; }\n\n" + M("mut x: i32 = 1;\nlet r = sum(x, bump(&x));\n" + chk("r == 3", "x == 10")))
H("eval_order", "earlier_operand_captured_in_binary_op", EV, "exit 0", "fn bump(p: i32*) -> i32 { *p = 10; return 2; }\n\n" + M("mut x: i32 = 1;\nlet r = x + bump(&x);\n" + chk("r == 3")))
H("eval_order", "and_short_circuits", EV, "exit 0", MK + "\n" + M("mut log: u32 = 0;\nlet r = false && (mark(&log, 1) != 0);\n" + chk("!r", "log == 0")))
H("eval_order", "or_short_circuits", EV, "exit 0", MK + "\n" + M("mut log: u32 = 0;\nlet r = true || (mark(&log, 1) != 0);\n" + chk("r", "log == 0")))
H("eval_order", "and_evaluates_right_when_left_true", EV, "exit 0", MK + "\n" + M("mut log: u32 = 0;\nlet r = true && (mark(&log, 3) != 0);\n" + chk("r", "log == 3")))
H("eval_order", "nested_calls_complete_first", EV, "exit 0", MK + "fn id(x: u32) -> u32 { return x; }\n\n" + M("mut log: u32 = 0;\nlet r = id(mark(&log, 1)) + id(mark(&log, 2));\n" + chk("log == 12", "r == 3")))
H("eval_order", "struct_literal_fields_in_order", EV, "exit 0", MK + "struct P { a: u32; b: u32; }\n\n" + M("mut log: u32 = 0;\nlet p = P{ a: mark(&log, 1), b: mark(&log, 2) };\n" + chk("log == 12")))
H("eval_order", "array_literal_in_order", EV, "exit 0", MK + "\n" + M("mut log: u32 = 0;\nlet a = [mark(&log, 1), mark(&log, 2), mark(&log, 3)];\n" + chk("log == 123", "a[2] == 3")))
# ffi
FF = "04-ffi §2"
H("ffi", "plain_c_call", FF, "exit 0", 'extern "C" { fn getpid() -> i32; }\n\n' + C("getpid() > 0"))
H("ffi", "c_call_with_arguments", FF, "exit 0", 'extern "C" { fn abs(x: i32) -> i32; }\n\n' + C("abs(-5) == 5", "abs(7) == 7"))
H("ffi", "pointer_argument_and_size_t_return", FF, "exit 0", 'extern "C" { fn strlen(s: const u8*) -> usize; }\n\n' + C('strlen("abc\\0".ptr) == 3'))
H("ffi", "struct_returned_by_value", FF, "exit 0", 'struct DivT { quot: i32; rem: i32; }\nextern "C" { fn div(a: i32, b: i32) -> DivT; }\n\n' + M("let r = div(7, 2);\n" + chk("r.quot == 3", "r.rem == 1")))
H("ffi", "callback_to_c", FF, "exit 0", 'extern "C" { fn qsort(base: u8*, n: usize, size: usize, cmp: fn(const u8*, const u8*) -> i32); }\nfn cmp(a: const u8*, b: const u8*) -> i32 {\n    let x = *(a as (const u32*));\n    let y = *(b as (const u32*));\n    if (x < y) { return -1; }\n    if (x > y) { return 1; }\n    return 0;\n}\n\n' + M("mut a: u32[4] = [3, 1, 4, 2];\nqsort(&a[0] as (u8*), 4, size_of(u32), cmp);\n" + chk("a[0] == 1", "a[1] == 2", "a[2] == 3", "a[3] == 4")))
H("ffi", "malloc_free_round_trip", FF, "exit 0", 'extern "C" { fn malloc(n: usize) -> u8*; fn free(p: u8*); }\n\n' + M("let p = malloc(16);\nif (p == null) { return 1; }\nlet s = slice(p, 16);\ns[0] = 7;\ns[15] = 9;\nlet ok = s[0] == 7 && s[15] == 9;\nfree(p);\n" + chk("ok")))
H("ffi", "memset_fills_buffer", FF, "exit 0", 'extern "C" { fn memset(p: u8*, c: i32, n: usize) -> u8*; }\n\n' + M("mut a: u8[4] = [0; 4];\nlet r = memset(&a[0], 7, 4);\n" + chk("a[0] == 7", "a[3] == 7")))
H("ffi", "enum_as_integer_argument", FF, "exit 0", 'enum Mode : i32 { A = 3 }\nextern "C" { fn abs(x: i32) -> i32; }\n\n' + C("abs(Mode.A as i32) == 3"))
H("ffi", "c_visible_nested_struct_with_array", FF, "exit 0", 'struct Pt { xy: i32[2]; }\nstruct Seg { a: Pt; b: Pt; }\nextern "C" { fn use_seg(s: Seg) -> i32; }\n\n' + M("return 0;"))
H("ffi", "void_callback_return_allowed", FF, "exit 0", 'extern "C" { fn atexit(cb: fn() -> void) -> i32; }\n\n' + M("return 0;"))
H("ffi", "pointer_to_non_c_visible_type_is_allowed", FF, "exit 0", 'struct View { s: u8[]; }\nextern "C" { fn take(v: View*); }\n\n' + M("return 0;"))
H("ffi", "function_pointer_value_passed_to_c", FF, "exit 0", 'extern "C" { fn atexit(cb: fn() -> void) -> i32; }\nfn done() { }\n\n' + M("let r = atexit(done);\n" + chk("r == 0")))

# precedence
PR = "01-syntax §4"
H("precedence", "multiplication_before_addition", PR, "exit 0", C("1 + 2 * 3 == 7", "(1 + 2) * 3 == 9"))
H("precedence", "bitwise_and_binds_tighter_than_equality", PR, "exit 0", M("let flags: u32 = 6;\nlet mask: u32 = 4;\n" + chk("flags & mask == 4", "flags & 1 == 0")))
H("precedence", "addition_before_shift", PR, "exit 0", M("let a: u32 = 1;\nlet b: u32 = 1;\n" + chk("a + b << 2 == 8")))
H("precedence", "and_before_or", PR, "exit 0", M("let t = true;\nlet f = false;\n" + chk("t || f && f", "!(f && f || f)")))
H("precedence", "not_binds_tighter_than_equality", PR, "exit 0", M("let a = true;\nlet b = false;\n" + chk("!a == b", "!b == a")))
H("precedence", "unary_minus_before_multiplication", PR, "exit 0", M("let a: i32 = 3;\nlet b: i32 = 2;\n" + chk("-a * b == -6")))
H("precedence", "subtraction_is_left_associative", PR, "exit 0", M("let a: i32 = 10;\nlet b: i32 = 3;\nlet c: i32 = 2;\n" + chk("a - b - c == 5", "a / b * c == 6")))
H("precedence", "bit_operator_ladder", PR, "exit 0", M("let a: u32 = 1;\nlet b: u32 = 2;\nlet c: u32 = 3;\nlet d: u32 = 6;\n" + chk("a | b ^ c & d == 1 | (2 ^ (3 & 6))")))
H("precedence", "cast_binds_tighter_than_multiplication", PR, "exit 0", M("let x: u8 = 200;\nlet c: u64 = 3;\n" + chk("x as u64 * c == 600")))
H("precedence", "cast_chain_is_left_to_right", PR, "exit 0", M("let x: i32 = -1;\n" + chk("x as u8 as u32 == 255")))
H("precedence", "deref_before_arithmetic", PR, "exit 0", M("mut v: i32 = 4;\nlet p = &v;\n" + chk("*p + 1 == 5", "*p * 2 == 8")))
H("precedence", "postfix_before_prefix", PR, "exit 0", "struct P { x: i32; }\n\n" + M("let p = P{ x: 3 };\nmut a: i32[2] = [5, 6];\n" + chk("-p.x == -3", "-a[1] == -6")))
H("precedence", "comparison_below_arithmetic", PR, "exit 0", C("1 + 1 < 3", "2 * 2 >= 4", "(1 < 2) == true"))
H("precedence", "compound_assignment_forms", "01-syntax §2", "exit 0", M("mut x: i32 = 10;\nx += 5;\nx -= 3;\nx *= 2;\nx /= 4;\nx %= 4;\nmut y: u32 = 6;\ny &= 3;\ny |= 8;\ny ^= 1;\ny <<= 2;\ny >>= 1;\n" + chk("x == 2", "y == 22")))
# memory model and calling convention
H("memory", "heap_block_viewed_as_slice", "03-memory §2", "exit 0", 'extern "C" { fn malloc(n: usize) -> u8*; fn free(p: u8*); }\n\n' + M("let raw = malloc(4 * size_of(u32));\nif (raw == null) { return 1; }\nlet xs = slice(raw as (u32*), 4);\nxs[0] = 10;\nxs[3] = 40;\nlet ok = xs[0] + xs[3] == 50;\nfree(raw);\n" + chk("ok")))
H("memory", "pointer_and_slice_share_storage", "03-memory §2", "exit 0", M("mut a: u8[4] = [1, 2, 3, 4];\nlet s = a[..];\nlet p = &a[2];\n*p = 9;\n" + chk("s[2] == 9")))
H("memory", "slice_length_check_uses_length_not_allocation", "03-memory §2", "trap", "fn at(s: const u8[], i: usize) -> u8 { return s[i]; }\n\n" + M("mut a: u8[8] = [0; 8];\nlet v = at(a[0..4], 6);"))
H("memory", "allocator_as_struct_of_function_pointers", "03-memory §3", "exit 0", 'extern "C" { fn malloc(n: usize) -> u8*; fn free(p: u8*); }\nstruct Alloc { alloc: fn(usize) -> u8*; release: fn(u8*); }\nfn m(n: usize) -> u8* { return malloc(n); }\nfn f(p: u8*) { free(p); }\n\n' + M("let a = Alloc{ alloc: m, release: f };\nlet p = a.alloc(8);\nif (p == null) { return 1; }\nlet s = slice(p, 8);\ns[7] = 3;\nlet ok = s[7] == 3;\na.release(p);\n" + chk("ok")))
H("memory", "uninitialized_heap_is_not_defined_but_written_data_is", "03-memory §1", "exit 0", 'extern "C" { fn calloc(n: usize, size: usize) -> u8*; fn free(p: u8*); }\n\n' + M("let p = calloc(4, 1);\nif (p == null) { return 1; }\nlet s = slice(p, 4);\nlet ok = s[0] == 0 && s[3] == 0;\nfree(p);\n" + chk("ok")))
H("ffi", "several_imports_in_one_block", "04-ffi §1", "exit 0", 'extern "C" {\n    fn getpid() -> i32;\n    fn abs(x: i32) -> i32;\n    fn labs(x: i64) -> i64;\n}\n\n' + C("getpid() > 0", "abs(-1) == 1", "labs(-9) == 9"))
H("ffi", "scalar_widths_round_trip", "04-ffi §3", "exit 0", 'extern "C" { fn labs(x: i64) -> i64; fn abs(x: i32) -> i32; }\n\n' + C("labs(-4294967296) == 4294967296", "abs(-2147483647) == 2147483647"))
H("ffi", "bool_is_one_byte_in_structs", "04-ffi §3", "exit 0", "struct Flags { a: bool; b: bool; }\n\n" + C("size_of(Flags) == 2"))
H("ffi", "float_argument_and_return", "04-ffi §3", "exit 0", 'extern "C" { fn sqrt(x: f64) -> f64; fn sqrtf(x: f32) -> f32; }\n\n' + C("sqrt(9.0) == 3.0", "sqrtf(16.0) == 4.0"))

# ---------------------------------------------------------------- near-miss twins of tests/fail
def twin(n, spec, defs, body="return 0;"):
    add("twins", n, spec, "exit 0", defs.strip("\n") + "\n\npub fn main() -> i32 {\n    " + body + "\n}\n")
twin("01_assign_mut", "01-syntax §2", "fn f() { mut x: i32 = 1; x = 2; }", "f();\n    return 0;")
twin("02_write_through_mut_pointer", "02-types §1", "fn f(p: u8*) { *p = 1; }", "mut b: u8 = 0;\n    f(&b);\n    return 0;")
twin("03_write_through_mut_slice", "02-types §5", "fn f(s: u8[]) { s[0] = 1; }", "mut a: u8[1] = [0];\n    f(a[..]);\n    return 0;")
twin("04_explicit_widening", "02-types §3", "fn f(a: i32) -> i64 { return a as i64; }", "let r = f(1);\n    return 0;")
twin("05_literal_at_limit", "02-types §3", "fn f() { let x: u8 = 255; }", "f();\n    return 0;")
twin("06_integer_compared_not_cast", "02-types §3", "fn f(x: i32) -> bool { return x != 0; }", "let r = f(1);\n    return 0;")
twin("07_bool_condition", "02-types §2", "fn f(x: i32) { if (x != 0) { } }", "f(1);\n    return 0;")
twin("08_pointer_explicit_cast", "02-types §3", "fn f(p: u8*) { let q: i32* = p as (i32*); }", "mut b: u8 = 0;\n    f(&b);\n    return 0;")
twin("09_null_to_pointer", "02-types §3", "fn f() { let p: u8* = null; }", "f();\n    return 0;")
twin("10_divide_by_nonzero_constant", "02-types §4", "fn f(x: i32) -> i32 { return x / 1; }", "let r = f(1);\n    return 0;")
twin("11_shift_below_width", "02-types §4", "fn f(x: u8) -> u8 { return x << 7; }", "let r = f(1);\n    return 0;")
twin("12_slice_from_pointer", "02-types §5", "fn f(p: u8*) { let s = slice(p, 4); }", "mut a: u8[4] = [0; 4];\n    f(&a[0]);\n    return 0;")
twin("13_struct_field_equality", "02-types §4", "struct P { x: i32; }\nfn f(a: P, b: P) -> bool { return a.x == b.x; }", "let p = P{ x: 1 };\n    let r = f(p, p);\n    return 0;")
twin("14_address_of_variable", "02-types §4", "fn g() -> i32 { return 1; }\nfn f() { let v = g(); let p = &v; }", "f();\n    return 0;")
twin("15_complete_struct_literal", "03-memory §5", "struct P { x: i32; y: i32; }\nfn f() { let p = P{ x: 1, y: 2 }; }", "f();\n    return 0;")
twin("16_switch_with_else", "02-types §5", "enum C { R, G }\nfn f(c: C) { switch (c) { case .R: { } else: { } } }", "f(C.R);\n    return 0;")
twin("17_defer_plain_statement", "03-memory §4", "fn f() { defer { } }", "f();\n    return 0;")
twin("18_break_inside_loop", "01-syntax §5", "fn f() { while (true) { break; } }", "f();\n    return 0;")
twin("19_all_paths_return", "06-compiler §3", "fn f(x: i32) -> i32 { if (x > 0) { return 1; } return 0; }", "let r = f(1);\n    return 0;")
twin("20_bare_return_in_void", "01-syntax §5", "fn f() { return; }", "f();\n    return 0;")
twin("21_field_and_method_differ", "01-syntax §5", "struct S { len: usize; }\nimpl S { pub fn size(self: S*) -> usize { return 0; } }", "mut s = S{ len: 1 };\n    let r = s.size();\n    return 0;")
twin("22_pub_on_methods", "01-syntax §5", "struct S { x: i32; }\nimpl S { pub fn get(self: S) -> i32 { return self.x; } }", "let s = S{ x: 1 };\n    let r = s.get();\n    return 0;")
twin("23_mutable_binding_not_const", "02-types §7", "fn f() { mut n: i32 = 1; n = 2; }", "f();\n    return 0;")
twin("24_known_variant", "02-types §5", "enum C { R, G }\nfn f() { let c = C.G; }", "f();\n    return 0;")
twin("25_defined_name", "05-modules §4", "fn f() { let x = 1; let y = x; }", "f();\n    return 0;")
twin("26_right_argument_count", "02-types §5", "fn g(a: i32) { }\nfn f() { g(1); }", "f();\n    return 0;")
twin("27_constant_initializer", "02-types §7", "const N: i32 = 1 + 1;", "return N - 2;")
twin("28_address_math_through_usize", "02-types §4", "fn f(p: u8*) -> u8* { return ((p as usize) + 1) as (u8*); }", "mut a: u8[2] = [0; 2];\n    let q = f(&a[0]);\n    return 0;")
twin("29_index_a_slice_built_from_pointer", "02-types §4", "fn f(p: u8*) -> u8 { return slice(p, 4)[0]; }", "mut a: u8[4] = [0; 4];\n    let r = f(&a[0]);\n    return 0;")
twin("30_index_with_usize", "02-types §4", "fn f(a: u8[4], i: i32) -> u8 { return a[i as usize]; }", "let r = f([0; 4], 1);\n    return 0;")
twin("31_extern_struct_with_field", "04-ffi §2", "struct Box { x: u8; }\nextern \"C\" { fn consume(b: Box); }", "return 0;")
twin("32_extern_pointer_to_struct_with_slice", "04-ffi §2", "struct View { s: u8[]; }\nextern \"C\" { fn consume(v: View*); }", "return 0;")
twin("33_extern_array_via_pointer", "04-ffi §2", "extern \"C\" { fn consume(a: u8*); }", "return 0;")
twin("34_shadow_in_nested_block", "03-memory §5", "fn f(x: i32) { { let x: i32 = x; } }", "f(1);\n    return 0;")
twin("35_distinct_names_in_block", "03-memory §5", "fn f() { let x: i32 = 1; let y: i32 = 2; }", "f();\n    return 0;")
twin("36_shadow_parameter_in_nested_block", "03-memory §5", "fn f(x: i32) { { let x: i32 = 2; } }", "f(1);\n    return 0;")
twin("37_distinct_converted", "02-types §3.1", "type Distance = distinct u32;\nfn f(a: Distance, b: u32) -> Distance { return a + (b as Distance); }", "let r = f(1, 2);\n    return 0;")
twin("38_distinct_index_via_usize", "02-types §3.1", "type Idx = distinct usize;\nfn f(a: u8[4], i: Idx) -> u8 { return a[i as usize]; }", "let r = f([0; 4], 1);\n    return 0;")

# ---------------------------------------------------------------- write
if os.path.isdir(OUT): shutil.rmtree(OUT)
counts = {}
for area, name, spec, expect, code in tests:
    n = counts.get(area, 0) + 1; counts[area] = n
    d = os.path.join(OUT, area); os.makedirs(d, exist_ok=True)
    fname = f"{name}.cn" if area == "twins" else f"{n:03d}_{name}.cn"
    with open(os.path.join(d, fname), "w") as f:
        f.write(f"// SPEC: {spec}\n// EXPECT: {expect}\n{code}")
print(sum(counts.values()), "files:", ", ".join(f"{a} {c}" for a, c in sorted(counts.items())))
