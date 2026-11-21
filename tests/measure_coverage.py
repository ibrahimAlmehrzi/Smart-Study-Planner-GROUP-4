"""Statement coverage of the planning modules (NFR-17 asks for at least 70%).

Uses only the Python standard library, so no extra package is needed.
Run from the project folder:  python tests/measure_coverage.py
"""
import ast
import os
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FILES = ["app/planning/priority.py", "app/planning/scheduler.py", "app/planning/reschedule.py", "app/plan_service.py"]
TARGETS = {os.path.join(ROOT, f) for f in FILES}
hits = {f: set() for f in TARGETS}


def tracer(frame, event, _arg):
    name = frame.f_code.co_filename
    if name in TARGETS:
        hits[name].add(frame.f_lineno)
        return tracer
    return None


def statement_lines(path):
    """Line numbers of executable statements (definitions, imports and docstrings are left out)."""
    lines = set()
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if not isinstance(node, ast.stmt) or isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        lines.add(node.lineno)
    return lines


def main():
    os.chdir(ROOT)
    sys.settrace(tracer)
    threading.settrace(tracer)
    suite = unittest.defaultTestLoader.discover("tests", top_level_dir=ROOT)
    result = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
    sys.settrace(None)
    total_run = total = 0
    print(f"{'Module':32s} {'Run':>9s}  Coverage")
    for f in FILES:
        path = os.path.join(ROOT, f)
        stmts = statement_lines(path)
        run = len(stmts & hits[path])
        total_run, total = total_run + run, total + len(stmts)
        print(f"{f:32s} {run:4d}/{len(stmts):4d}  {100 * run / len(stmts):5.1f}%")
    print(f"{'Total':32s} {total_run:4d}/{total:4d}  {100 * total_run / total:5.1f}%")
    print(f"Tests run: {result.testsRun}, failures: {len(result.failures)}, errors: {len(result.errors)}")


if __name__ == "__main__":
    main()
