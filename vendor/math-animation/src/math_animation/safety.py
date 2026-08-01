"""Static gates for expressions and the opt-in custom-Manim escape hatch.

These checks improve diagnostics but do not replace process/container isolation.
"""

from __future__ import annotations

import ast

_ALLOWED_FUNCTIONS = {"sin", "cos", "tan", "exp", "log", "sqrt", "abs"}
_ALLOWED_EXPRESSION_NAMES = {"x", "pi", "e", "np", *_ALLOWED_FUNCTIONS}
_BLOCKED_CALLS = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "input",
    "breakpoint",
}
_BLOCKED_ATTRIBUTES = {
    "system",
    "popen",
    "spawn",
    "fork",
    "remove",
    "unlink",
    "rmdir",
    "rmtree",
    "write_text",
    "write_bytes",
    "read_text",
    "read_bytes",
}
_ALLOWED_IMPORT_ROOTS = {"manim", "math", "numpy"}


class _FunctionNormalizer(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id == "pi":
            return ast.copy_location(
                ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr="pi"),
                node,
            )
        if node.id == "e":
            return ast.copy_location(
                ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr="e"),
                node,
            )
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCTIONS:
            if node.func.id == "abs":
                return node
            node.func = ast.Attribute(
                value=ast.Name(id="np", ctx=ast.Load()), attr=node.func.id
            )
        return node


class _VectorFunctionNormalizer(ast.NodeTransformer):
    def __init__(self, variable_names: set[str]):
        self.variable_names = variable_names

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id == "pi" and node.id not in self.variable_names:
            return ast.copy_location(
                ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr="pi"),
                node,
            )
        if node.id == "e" and node.id not in self.variable_names:
            return ast.copy_location(
                ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr="e"),
                node,
            )
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCTIONS:
            if node.func.id == "abs":
                node.func = ast.Name(id="abs", ctx=ast.Load())
            else:
                node.func = ast.Attribute(
                    value=ast.Name(id="np", ctx=ast.Load()),
                    attr=node.func.id,
                )
        return node


def normalize_math_expression(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid function expression: {exc}") from exc

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Attribute,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(
                f"unsupported expression syntax: {type(node).__name__}"
            )
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_EXPRESSION_NAMES:
            raise ValueError(f"unsupported expression name: {node.id!r}")
        if isinstance(node, ast.Attribute):
            if (
                not isinstance(node.value, ast.Name)
                or node.value.id != "np"
                or node.attr not in _ALLOWED_FUNCTIONS | {"pi", "e"}
            ):
                raise ValueError("only approved numpy math attributes are allowed")
        if isinstance(node, ast.Call):
            target = node.func
            valid = (
                isinstance(target, ast.Name)
                and target.id in _ALLOWED_FUNCTIONS
                or isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "np"
                and target.attr in _ALLOWED_FUNCTIONS
            )
            if not valid:
                raise ValueError("only approved math functions are callable")
    normalized = _FunctionNormalizer().visit(tree)
    ast.fix_missing_locations(normalized)
    return ast.unparse(normalized.body)


def normalize_vector_expression(
    expression: str,
    *,
    variable_names: set[str],
) -> str:
    """Validate and vectorize a point-cloud expression.

    Expressions may reference only explicitly supplied scalar/array variables,
    arithmetic operators, and the small approved math-function set. The
    resulting source uses NumPy functions and is safe to evaluate on arrays in
    generated Manim code.
    """

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid vector expression: {exc}") from exc

    allowed_names = {*variable_names, "pi", "e", *_ALLOWED_FUNCTIONS}
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(
                f"unsupported vector expression syntax: {type(node).__name__}"
            )
        if isinstance(node, ast.Name) and node.id not in allowed_names:
            raise ValueError(f"unsupported vector expression name: {node.id!r}")
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _ALLOWED_FUNCTIONS
            ):
                raise ValueError("only approved math functions are callable")

    normalized = _VectorFunctionNormalizer(variable_names).visit(tree)
    ast.fix_missing_locations(normalized)
    return ast.unparse(normalized.body)


def validate_custom_scene_source(source: str, expected_scene_class: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"custom scene has invalid Python: {exc}") from exc

    scenes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in _ALLOWED_IMPORT_ROOTS:
                    raise ValueError(f"blocked import: {alias.name!r}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                raise ValueError(f"blocked import: {node.module!r}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BLOCKED_CALLS:
                raise ValueError(f"blocked call: {node.func.id}()")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in _BLOCKED_ATTRIBUTES:
                raise ValueError(f"blocked attribute access: {node.attr!r}")
        elif isinstance(node, ast.ClassDef):
            bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
            if bases & {"Scene", "ThreeDScene", "MovingCameraScene"}:
                scenes.append(node.name)

    if scenes != [expected_scene_class]:
        raise ValueError(
            "custom source must define exactly the declared Scene subclass; "
            f"declared={expected_scene_class!r}, found={scenes!r}"
        )
