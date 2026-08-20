"""PLUTON V2 — Safe Deterministic Arithmetic AST Evaluator.

Evaluates mathematical expressions deterministically via Python AST parsing.
Zero arbitrary eval/exec, zero physical keyboard/mouse interaction.
"""

from __future__ import annotations

import ast
import operator as op
import re
from typing import Any


class SafeMathEvaluator:
    """Deterministic mathematical evaluator supporting arithmetic, decimals, percentages, and powers."""

    _OPERATORS = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.FloorDiv: op.floordiv,
        ast.Mod: op.mod,
        ast.Pow: op.pow,
        ast.USub: op.neg,
        ast.UAdd: op.pos,
    }

    @classmethod
    def evaluate(cls, expression: str) -> dict[str, Any]:
        """Safely evaluates a mathematical expression string."""
        if not expression or not expression.strip():
            return {
                "success": False,
                "error": "Expression cannot be empty",
                "expression": expression,
            }

        raw_expr = expression.strip()

        # Normalize mathematical words to standard operators
        norm = raw_expr.lower()
        norm = norm.replace("times", "*").replace("multiplied by", "*").replace("multiplied", "*")
        norm = norm.replace("plus", "+").replace("minus", "-")
        norm = norm.replace("divided by", "/").replace("divided", "/")
        norm = norm.replace("x", "*")  # common multiplier symbol
        norm = norm.replace("^", "**")

        # Handle percentages: e.g. "20% of 1000" -> "(20 / 100) * 1000", "1500 * 18%" -> "1500 * (18 / 100)"
        norm = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*(?:of)?\s*(\d+(?:\.\d+)?)", r"(\1 / 100.0) * \2", norm)
        norm = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1 / 100.0)", norm)

        # Sanitize permitted characters strictly
        sanitized = re.sub(r"[^0-9\+\-\*\/\(\)\.\s\%]", "", norm)
        if not sanitized.strip() or not re.search(r"\d", sanitized):
            return {
                "success": False,
                "error": f"Invalid mathematical expression '{raw_expr}'",
                "expression": raw_expr,
            }

        try:
            parsed = ast.parse(sanitized, mode="eval")

            def _eval_node(node):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    op_func = cls._OPERATORS.get(type(node.op))
                    if not op_func:
                        raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
                    left = _eval_node(node.left)
                    right = _eval_node(node.right)
                    if type(node.op) in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                        raise ZeroDivisionError("Division by zero")
                    return op_func(left, right)
                elif isinstance(node, ast.UnaryOp):
                    op_func = cls._OPERATORS.get(type(node.op))
                    if not op_func:
                        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
                    return op_func(_eval_node(node.operand))
                else:
                    raise TypeError(f"Unsupported expression element: {type(node).__name__}")

            val = _eval_node(parsed.body)
            val_str = str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)

            return {
                "success": True,
                "expression": raw_expr,
                "normalized_expression": sanitized,
                "result": val,
                "result_string": val_str,
                "message": f"{raw_expr} = {val_str}",
            }
        except ZeroDivisionError:
            return {
                "success": False,
                "error": "Division by zero",
                "expression": raw_expr,
            }
        except Exception as ex:
            return {
                "success": False,
                "error": f"Failed to evaluate expression: {ex}",
                "expression": raw_expr,
            }
