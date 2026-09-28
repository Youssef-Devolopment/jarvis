import ast, operator, re
from skills.registry import register

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    def walk(n):
        if isinstance(n, ast.Expression): return walk(n.body)
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                return n.value
            raise ValueError
        if isinstance(n, ast.BinOp):
            op = _BINOPS.get(type(n.op))
            if op is None: raise ValueError
            l, r = walk(n.left), walk(n.right)
            if op is operator.pow and abs(r) > 1000: raise ValueError
            return op(l, r)
        if isinstance(n, ast.UnaryOp):
            op = _UNARY.get(type(n.op))
            if op is None: raise ValueError
            return op(walk(n.operand))
        raise ValueError
    return walk(tree)


_W2S = {"plus": "+", "minus": "-", "times": "*", "multiplied by": "*",
        "divided by": "/", "over": "/", "to the power of": "**",
        "power": "**", "squared": "** 2", "cubed": "** 3", "modulo": "%"}


@register("math", [
    r"^(?:(?:what(?:'s| is)|calculate|compute|solve|how much is)\s+)?"
    r"(?P<expr>[A-Za-z0-9\s\.\+\-\*/%\(\)\^]+)$",
], "Arithmetic")
def skill_math(text, match):
    e = match.group("expr")
    n = e.lower()
    for w, s in _W2S.items():
        n = re.sub(rf"\b{re.escape(w)}\b", f" {s} ", n)
    n = n.replace("^", "**").replace("x", "*")
    n = re.sub(r"\s+", " ", n).strip(" ?.=")
    if not re.fullmatch(r"[-\d\s\.\+\*/%\(\)]+", n): return None
    if not re.search(r"\d", n) or not re.search(r"[-\+\*/%]", n): return None
    try:
        v = _safe_eval(n)
    except Exception:
        return None
    if isinstance(v, float):
        v = int(v) if v.is_integer() else round(v, 6)
    return f"{n} equals {v}."
