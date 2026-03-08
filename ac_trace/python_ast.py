from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


AC_DOCSTRING_PATTERN = re.compile(r"\bACs?\s*:\s*(.+)")
ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "route"}


@dataclass(frozen=True)
class PythonSymbol:
    name: str
    qualname: str
    lineno: int
    body_lineno: int
    end_lineno: int
    decorators: tuple[str, ...]

    @property
    def lines(self) -> str:
        return f"{self.lineno}-{self.end_lineno}"

    @property
    def mutate(self) -> bool:
        terminal_names = {decorator.split(".")[-1] for decorator in self.decorators}
        return not bool(terminal_names.intersection(ROUTE_DECORATORS))


@dataclass(frozen=True)
class PythonTestCase:
    path: str
    case_id: str
    selector: str
    ac_ids: list[str]


def _decorator_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = _decorator_name(node.value)
        return f"{root}.{node.attr}" if root else node.attr
    return None


def _parse_docstring_ac_ids(node: ast.AST) -> list[str]:
    docstring = ast.get_docstring(node)
    if not docstring:
        return []

    ids: list[str] = []
    for line in docstring.splitlines():
        match = AC_DOCSTRING_PATTERN.search(line)
        if not match:
            continue
        for raw_id in match.group(1).split(","):
            criterion_id = raw_id.strip()
            if criterion_id and criterion_id not in ids:
                ids.append(criterion_id)
    return ids


def _parse_decorator_ac_ids(decorators: list[ast.expr]) -> list[str]:
    ids: list[str] = []
    for decorator in decorators:
        decorator_name = _decorator_name(decorator)
        if decorator_name is None or decorator_name.split(".")[-1] != "ac":
            continue
        if not isinstance(decorator, ast.Call):
            continue
        for argument in decorator.args:
            if (
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
                and argument.value not in ids
            ):
                ids.append(argument.value)
    return ids


def _merge_unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


class SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.symbols: list[PythonSymbol] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname_parts = [*self.scope, node.name]
        decorators = tuple(
            name
            for decorator in node.decorator_list
            if (name := _decorator_name(decorator)) is not None
        )
        self.symbols.append(
            PythonSymbol(
                name=node.name,
                qualname=".".join(qualname_parts),
                lineno=node.lineno,
                body_lineno=node.body[0].lineno if node.body else node.lineno,
                end_lineno=node.end_lineno or node.lineno,
                decorators=decorators,
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()


def discover_python_symbols(path: Path) -> list[PythonSymbol]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    collector = SymbolCollector()
    collector.visit(tree)
    return collector.symbols


def resolve_python_symbol(path: Path, symbol: str) -> PythonSymbol | None:
    symbols = discover_python_symbols(path)
    exact_matches = [candidate for candidate in symbols if candidate.qualname == symbol]
    if exact_matches:
        return exact_matches[0]

    name_matches = [candidate for candidate in symbols if candidate.name == symbol]
    if len(name_matches) == 1:
        return name_matches[0]
    return None


def discover_pytest_cases(path: Path, project_root: Path) -> list[PythonTestCase]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    relative_path = path.resolve().relative_to(project_root).as_posix()
    cases: list[PythonTestCase] = []

    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name.startswith("test_"):
            ac_ids = _merge_unique(
                _parse_decorator_ac_ids(node.decorator_list)
                + _parse_docstring_ac_ids(node)
            )
            cases.append(
                PythonTestCase(
                    path=relative_path,
                    case_id=node.name,
                    selector=f"{relative_path}::{node.name}",
                    ac_ids=ac_ids,
                )
            )
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            class_ac_ids = _merge_unique(
                _parse_decorator_ac_ids(node.decorator_list)
                + _parse_docstring_ac_ids(node)
            )
            for child in node.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and child.name.startswith("test_"):
                    ac_ids = _merge_unique(
                        class_ac_ids
                        + _parse_decorator_ac_ids(child.decorator_list)
                        + _parse_docstring_ac_ids(child)
                    )
                    case_id = f"{node.name}::{child.name}"
                    cases.append(
                        PythonTestCase(
                            path=relative_path,
                            case_id=case_id,
                            selector=f"{relative_path}::{case_id}",
                            ac_ids=ac_ids,
                        )
                    )

    return cases


def discover_pytest_case_ids(path: Path, project_root: Path) -> set[str]:
    return {case.case_id for case in discover_pytest_cases(path, project_root)}
