"""Restricted, read-only XDF equation evaluation. NO Python eval/exec.

XDF math syntax is not a universal standard. We support a documented, safe
subset and reject all unknown functions/symbols; invalid numeric domains are
reported instead of silently displaying plausible but wrong values.
"""
from __future__ import annotations
import ast
from functools import lru_cache
import math

_FUNCS = {'abs': abs, 'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10,
          'exp': math.exp, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
          'floor': math.floor, 'ceil': math.ceil, 'min': min, 'max': max}

@lru_cache(maxsize=2048)
def parse_equation(equation: str):
    if len(equation) > 512:
        raise ValueError('XDF-Gleichung zu lang')
    try:
        node = ast.parse(equation.replace('^', '**'), mode='eval')
    except SyntaxError as exc:
        raise ValueError('XDF-Gleichung nicht lesbar') from exc
    nodes = list(ast.walk(node))
    if len(nodes) > 96:
        raise ValueError('XDF-Gleichung zu komplex')
    for part in nodes:
        if isinstance(part, (ast.Expression, ast.Load, ast.operator, ast.unaryop)):
            continue
        if isinstance(part, ast.BinOp):
            if not isinstance(part.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
                raise ValueError('Nicht unterstützter Rechenoperator')
        elif isinstance(part, ast.UnaryOp):
            if not isinstance(part.op, (ast.USub, ast.UAdd)):
                raise ValueError('Nicht unterstützter Vorzeichenoperator')
        elif isinstance(part, ast.Constant):
            if type(part.value) not in (int, float) or not math.isfinite(part.value):
                raise ValueError('Ungültige Konstante')
        elif isinstance(part, ast.Name):
            if part.id.lower() != 'x' and part.id not in _FUNCS:
                raise ValueError('Unbekanntes Symbol in XDF-Gleichung')
        elif isinstance(part, ast.Call):
            if (not isinstance(part.func, ast.Name) or part.func.id not in _FUNCS
                    or part.keywords or len(part.args) not in (1, 2)):
                raise ValueError('Nicht unterstützte XDF-Funktion')
            if len(part.args)==2 and part.func.id not in ('min','max','log'):
                raise ValueError('Nicht unterstützte Funktionsargumente')
        else:
            raise ValueError('Unsichere/nicht unterstützte XDF-Gleichung')
    return node.body


def evaluate_equation(equation: str, value: float) -> float:
    expression = parse_equation(equation)
    def calc(node):
        if isinstance(node, ast.Constant): return float(node.value)
        if isinstance(node, ast.Name):
            if node.id.lower() == 'x': return float(value)
            raise ValueError('Unbekanntes Symbol')
        if isinstance(node, ast.UnaryOp):
            v=calc(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a,b=calc(node.left),calc(node.right)
            if isinstance(node.op, ast.Add):return a+b
            if isinstance(node.op, ast.Sub):return a-b
            if isinstance(node.op, ast.Mult):return a*b
            if isinstance(node.op, ast.Div):return a/b
            if isinstance(node.op, ast.Pow):
                if abs(b)>8 or abs(a)>1e12:raise ValueError('Potenz zu groß')
                return a**b
        if isinstance(node, ast.Call):
            return _FUNCS[node.func.id](*(calc(a) for a in node.args))
        raise ValueError('Ungültiger AST-Knoten')
    try:
        out=float(calc(expression))
    except (OverflowError, ZeroDivisionError, ValueError, TypeError) as exc:
        raise ValueError('XDF-Formel für diesen Rohwert nicht auswertbar') from exc
    if not math.isfinite(out):raise ValueError('XDF-Formel erzeugt nichtendlichen Wert')
    return out
