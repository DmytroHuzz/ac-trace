from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

from ac_trace.manifest import TraceManifest
from ac_trace.test_runner import (
    PytestCaseResult,
    run_pytest,
    selectors_for_criterion,
)


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

FAILED_TEST_STATUSES = {"failed", "error"}


@dataclass(frozen=True)
class MutationSite:
    index: int
    description: str


@dataclass(frozen=True)
class MutationReport:
    criterion_id: str
    code_path: str
    symbol: str
    mutation: str
    status: str
    selectors: list[str]
    test_results: list[PytestCaseResult]
    pytest_output: str


def _location_text(node: ast.AST) -> str:
    line = getattr(node, "lineno", 0)
    column = getattr(node, "col_offset", 0) + 1
    return f"line {line}:{column}"


def _compare_description(node: ast.Compare) -> str | None:
    if len(node.ops) != 1:
        return None
    current_op = type(node.ops[0])
    replacement = COMPARE_MUTATIONS.get(current_op)
    if replacement is None:
        return None
    return f"{_location_text(node)} {current_op.__name__} -> {replacement.__name__}"


def _binop_description(node: ast.BinOp) -> str | None:
    current_op = type(node.op)
    replacement = BINOP_MUTATIONS.get(current_op)
    if replacement is None:
        return None
    return f"{_location_text(node)} {current_op.__name__} -> {replacement.__name__}"


def _constant_description(node: ast.Constant) -> str | None:
    if isinstance(node.value, bool):
        return f"{_location_text(node)} bool {node.value} -> {not node.value}"
    if (
        isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value != 0
    ):
        return f"{_location_text(node)} constant {node.value} -> {node.value + 1}"
    return None


class MutationScopeMixin:
    def __init__(self, symbol: str, line_range: tuple[int, int] | None = None) -> None:
        self.symbol = symbol
        self.line_range = line_range
        self._inside_target = False
        self._scope: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self._scope.append(node.name)
        node = self.generic_visit(node)
        self._scope.pop()
        return node

    def _matches(self, name: str) -> bool:
        qualname = ".".join([*self._scope, name]) if self._scope else name
        return self.symbol in {name, qualname}

    def _within_target_lines(self, node: ast.AST) -> bool:
        if self.line_range is None:
            return True

        node_start = getattr(node, "lineno", None)
        if node_start is None:
            return False
        node_end = getattr(node, "end_lineno", node_start)
        target_start, target_end = self.line_range
        return target_start <= node_start and node_end <= target_end

    def visit_FunctionDef(self, node: ast.FunctionDef):
        return self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        was_inside_target = self._inside_target
        if self._matches(node.name):
            self._inside_target = True
        self._scope.append(node.name)
        node = self.generic_visit(node)
        self._scope.pop()
        self._inside_target = was_inside_target
        return node


class MutationSiteCollector(MutationScopeMixin, ast.NodeVisitor):
    def __init__(self, symbol: str, line_range: tuple[int, int] | None = None) -> None:
        MutationScopeMixin.__init__(self, symbol, line_range)
        self.sites: list[MutationSite] = []
        self._next_index = 0

    def _record(self, description: str) -> None:
        self.sites.append(
            MutationSite(
                index=self._next_index,
                description=description,
            )
        )
        self._next_index += 1

    def visit_Compare(self, node: ast.Compare) -> None:
        self.generic_visit(node)
        if self._inside_target and self._within_target_lines(node):
            description = _compare_description(node)
            if description is not None:
                self._record(description)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.generic_visit(node)
        if self._inside_target and self._within_target_lines(node):
            description = _binop_description(node)
            if description is not None:
                self._record(description)

    def visit_Constant(self, node: ast.Constant) -> None:
        if self._inside_target and self._within_target_lines(node):
            description = _constant_description(node)
            if description is not None:
                self._record(description)


class FunctionMutator(MutationScopeMixin, ast.NodeTransformer):
    def __init__(
        self,
        symbol: str,
        line_range: tuple[int, int] | None = None,
        target_index: int | None = None,
    ) -> None:
        MutationScopeMixin.__init__(self, symbol, line_range)
        self.target_index = target_index
        self.changed = False
        self.description = ""
        self._current_index = 0

    def _target_matches(self) -> bool:
        if self.target_index is None:
            return False
        matches = self._current_index == self.target_index
        self._current_index += 1
        return matches

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        node = self.generic_visit(node)
        if self._inside_target and self._within_target_lines(node) and not self.changed:
            description = _compare_description(node)
            if description is not None and self._target_matches():
                replacement = COMPARE_MUTATIONS[type(node.ops[0])]
                node.ops[0] = replacement()
                self.changed = True
                self.description = description
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        node = self.generic_visit(node)
        if self._inside_target and self._within_target_lines(node) and not self.changed:
            description = _binop_description(node)
            if description is not None and self._target_matches():
                replacement = BINOP_MUTATIONS[type(node.op)]
                node.op = replacement()
                self.changed = True
                self.description = description
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self._inside_target and self._within_target_lines(node) and not self.changed:
            description = _constant_description(node)
            if description is not None and self._target_matches():
                self.changed = True
                self.description = description
                if isinstance(node.value, bool):
                    return ast.copy_location(
                        ast.Constant(value=not node.value),
                        node,
                    )
                return ast.copy_location(
                    ast.Constant(value=node.value + 1),
                    node,
                )
        return node


def _parse_line_range(line_spec: str | None) -> tuple[int, int] | None:
    if line_spec is None:
        return None

    start_text, _, end_text = line_spec.partition("-")
    if not start_text.isdigit() or not end_text.isdigit():
        raise ValueError(f"Invalid line range: {line_spec}")
    start, end = int(start_text), int(end_text)
    if start < 1 or end < start:
        raise ValueError(f"Invalid line range: {line_spec}")
    return start, end


def discover_mutation_sites(
    path: Path,
    symbol: str,
    line_spec: str | None = None,
) -> list[MutationSite]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    collector = MutationSiteCollector(symbol, _parse_line_range(line_spec))
    collector.visit(tree)
    return collector.sites


def mutate_symbol(
    path: Path,
    symbol: str,
    line_spec: str | None = None,
    target_index: int | None = None,
) -> str | None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    mutator = FunctionMutator(symbol, _parse_line_range(line_spec), target_index)
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


def run_mutation_check(
    manifest: TraceManifest,
    ac_ids: list[str] | None = None,
) -> list[MutationReport]:
    reports: list[MutationReport] = []

    for criterion in manifest.find_criteria(ac_ids):
        selectors = selectors_for_criterion(criterion)
        for code_ref in criterion.code:
            if not code_ref.symbol or not code_ref.mutate:
                continue

            code_path = code_ref.resolved_path(manifest.project_root)
            original_source = code_path.read_text(encoding="utf-8")
            sites = discover_mutation_sites(code_path, code_ref.symbol, code_ref.lines)

            if not sites:
                reports.append(
                    MutationReport(
                        criterion_id=criterion.id,
                        code_path=code_ref.path,
                        symbol=code_ref.symbol,
                        mutation="no supported mutation found",
                        status="skipped",
                        selectors=selectors,
                        test_results=[],
                        pytest_output="",
                    )
                )
                continue

            for site in sites:
                try:
                    mutation = mutate_symbol(
                        code_path,
                        code_ref.symbol,
                        code_ref.lines,
                        site.index,
                    )
                    if not mutation:
                        reports.append(
                            MutationReport(
                                criterion_id=criterion.id,
                                code_path=code_ref.path,
                                symbol=code_ref.symbol,
                                mutation=site.description,
                                status="skipped",
                                selectors=selectors,
                                test_results=[],
                                pytest_output="",
                            )
                        )
                        continue

                    result = run_pytest(manifest.project_root, selectors)
                    killed = any(
                        case.status in FAILED_TEST_STATUSES for case in result.cases
                    )
                    status = "killed" if killed else "unkilled"
                    reports.append(
                        MutationReport(
                            criterion_id=criterion.id,
                            code_path=code_ref.path,
                            symbol=code_ref.symbol,
                            mutation=mutation,
                            status=status,
                            selectors=selectors,
                            test_results=result.cases,
                            pytest_output=result.stdout + result.stderr,
                        )
                    )
                finally:
                    code_path.write_text(original_source, encoding="utf-8")
                    _clear_bytecode(code_path)

    return reports
