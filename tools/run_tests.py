"""Run the grammar test suites against spec/01-syntax.md.
  litmus/*.cn, tests/fail/*.cn   must PARSE (tests/fail programs are rejected later, by semantic analysis)
  tests/syntax_fail/*.cn         must be REJECTED by the parser
Exits non-zero if any expectation is violated."""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cnparse

def parses(path, grammar):
    try:
        cnparse.parse(open(path).read(), grammar); return True
    except (SyntaxError, RecursionError):
        return False

def main(grammar="spec/01-syntax.md"):
    bad = 0
    for pattern, want in (("litmus/*.cn", True), ("tests/fail/*.cn", True), ("tests/syntax_fail/*.cn", False)):
        files = sorted(glob.glob(pattern))
        ok = sum(parses(f, grammar) == want for f in files)
        for f in files:
            if parses(f, grammar) != want:
                print(("FAIL (should parse)   " if want else "FAIL (should reject)  ") + f); bad += 1
        print(f"{pattern:24} {ok}/{len(files)} as expected")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
