"""Exact check for a deliberately narrow grammar; never executes student text."""

import ast
import re
from fractions import Fraction


def evaluate(text: str) -> Fraction:
    text = text.strip().replace("×", "*").replace("÷", "/").replace("−", "-")
    if len(text) > 120 or not re.fullmatch(r"[\d\s.+*/()\-]+", text):
        raise ValueError("Unsupported expression")
    tree = ast.parse(text, mode="eval")
    if len(list(ast.walk(tree))) > 50:
        raise ValueError("Expression too complex")

    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(ast.get_source_segment(text, node))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return walk(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("Unsupported expression")

    return walk(tree.body)


def check(question: str, answer: str) -> bool | None:
    """Only a plain expression with optional trailing = or =? is supported."""
    expression = re.sub(r"\s*=\s*[?？]?\s*$", "", question.strip())
    try:
        return evaluate(expression) == evaluate(answer)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError):
        return None
