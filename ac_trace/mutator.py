from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

from ac_trace.manifest import TraceManifest
from ac_trace.test_runner import run_pytest, selectors_for_criterion


COMPARE_MUTATIONS = {
    ast.GtE: ast.Gt,
    ast.Gt: ast.GtE,
    ast.LtE: ast.Lt,
    ast.Lt: ast.LtE,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}

BINOP_MUTATIONS = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
}


@dataclass(frozen=True)
class MutationReport:
    criterion_id: str
    code_path: str
    symbol: str
    mutation: str
    status: str
    selectors: list[str]
    pytest_output: str


class FunctionMutator(ast.NodeTransformer):
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.changed = False
        self.description = ""
        self._inside_target = False
        self._scope: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self._scope.append(node.name)
        node = self.generic_visit(node)
        self._scope.pop()
        return node

    def _matches(self, name: str) -> bool:
        qualname = ".".join([*self._scope, name]) if self._scope else name
        return self.symbol in {name, qualname}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
        was_inside_target = self._inside_target
        if self._matches(node.name) and not self.changed:
            self._inside_target = True
        self._scope.append(node.name)
        node = self.generic_visit(node)
        self._scope.pop()
        self._inside_target = was_inside_target
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        node = self.generic_visit(node)
        if self._inside_target and not self.changed and len(node.ops) == 1:
            current_op = type(node.ops[0])
            replacement = COMPARE_MUTATIONS.get(current_op)
            if replacement:
                node.ops[0] = replacement()
                self.changed = True
                self.description = f"{current_op.__name__} -> {replacement.__name__}"
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        node = self.generic_visit(node)
        if self._inside_target and not self.changed:
            current_op = type(node.op)
            replacement = BINOP_MUTATIONS.get(current_op)
            if replacement:
                node.op = replacement()
                self.changed = True
                self.description = f"{current_op.__name__} -> {replacement.__name__}"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self._inside_target and not self.changed:
            if isinstance(node.value, bool):
                self.changed = True
                self.description = f"bool {node.value} -> {not node.value}"
                return ast.copy_location(ast.Constant(value=not node.value), node)
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and node.value != 0:
                self.changed = True
                self.description = f"constant {node.value} -> {node.value + 1}"
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node


def mutate_symbol(path: Path, symbol: str) -> str | None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    mutator = FunctionMutator(symbol)
    mutated_tree = mutator.visit(tree)
    if not mutator.changed:
        return None

    ast.fix_missing_locations(mutated_tree)
    path.write_text(f"{ast.unparse(mutated_tree)}\n", encoding="utf-8")
    _clear_bytecode(path)
    return mutator.description


def _clear_bytecode(path: Path) -> None:
    cache_path = Path(importlib.util.cache_from_source(str(path)))
    if cache_path.exists():
        cache_path.unlink()

    cache_dir = path.parent / "__pycache__"
    if cache_dir.exists():
        for candidate in cache_dir.glob(f"{path.stem}.*.pyc"):
            if candidate.exists():
                candidate.unlink()


def run_mutation_check(manifest: TraceManifest, ac_ids: list[str] | None = None) -> list[MutationReport]:
    reports: list[MutationReport] = []

    for criterion in manifest.find_criteria(ac_ids):
        selectors = selectors_for_criterion(criterion)
        for code_ref in criterion.code:
            if not code_ref.symbol or not code_ref.mutate:
                continue

            code_path = code_ref.resolved_path(manifest.project_root)
            original_source = code_path.read_text(encoding="utf-8")

            try:
                mutation = mutate_symbol(code_path, code_ref.symbol)
                if not mutation:
                    reports.append(
                        MutationReport(
                            criterion_id=criterion.id,
                            code_path=code_ref.path,
                            symbol=code_ref.symbol,
                            mutation="no supported mutation found",
                            status="skipped",
                            selectors=selectors,
                            pytest_output="",
                        )
                    )
                    continue

                result = run_pytest(manifest.project_root, selectors)
                status = "killed" if result.returncode != 0 else "survived"
                reports.append(
                    MutationReport(
                        criterion_id=criterion.id,
                        code_path=code_ref.path,
                        symbol=code_ref.symbol,
                        mutation=mutation,
                        status=status,
                        selectors=selectors,
                        pytest_output=result.stdout + result.stderr,
                    )
                )
            finally:
                code_path.write_text(original_source, encoding="utf-8")
                _clear_bytecode(code_path)

    return reports
