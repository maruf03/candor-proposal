# Micro litmus corpus

Small programs, one rule each, grouped by area. `tools/gen_micro_tests.py` generates them (the files are committed; edit the script, not the files, and regenerate).

Every file starts with two header lines:

```
// SPEC: 02-types §4        the spec section whose rule this tests
// EXPECT: exit 0           or `exit N`, or `trap` (the process aborts)
```

`main` returns 0 when every check passes, and a distinct nonzero code per failing check, so a failure points at one assertion.

| Area | Checks |
| :--- | :--- |
| `arithmetic`, `shifts` | generated from a Python model: every integer width, overflow and edge cases, `wrapping_*`, division rules |
| `lexical`, `types`, `conversions`, `precedence` | literals, sizes, `as` rules, operator precedence |
| `pointers`, `slices`, `arrays`, `structs`, `enums` | the value and pointer model, bounds, layout (`size_of`), `switch` |
| `generics`, `distinct` | monomorphization, inherited operations of `distinct` types |
| `defer`, `scope`, `returns`, `eval_order` | cleanup order, binding scope, fall-through rule, left-to-right evaluation |
| `memory`, `ffi` | heap via `malloc` and `slice`, allocator structs, C calls, callbacks, by-value structs |
| `twins` | the smallest *accepted* variant of each `tests/fail` program (guards against over-rejection) |

**Not here yet:** module tests (`spec/05-modules.md`) need multi-file projects, so they wait until the build command and module root are decided.

Today the runner only checks that each file parses and has valid headers. Once a type checker exists these must type-check; once code generation exists they must build, run, and match `EXPECT`. `python3 tools/spec_coverage.py` lists spec sections that no test cites.
