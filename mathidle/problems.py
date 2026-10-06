"""Генерация случайных примеров.

Каждый генератор принимает `difficulty` в диапазоне 0..1 и возвращает
`(текст, ответ, difficulty)`. Чем выше сложность, тем меньше денег
за пример (см. economy.reward).
"""

import random

from . import config


def _gen_add(rng, diff, cfg):
    """2..max_terms слагаемых."""
    terms = 2
    if diff > 0.30:
        terms += 1
    if diff > 0.65 and cfg.get("max_terms", 4) >= 3:
        terms += 1
    if diff > 0.90 and cfg.get("max_terms", 4) >= 4:
        terms += 1
    terms = min(terms, cfg.get("max_terms", 4))

    hi = max(4, int(round(5 + 45 * diff)))
    nums = [rng.randint(1, hi) for _ in range(terms)]
    return " + ".join(str(n) for n in nums), sum(nums)


def _gen_sub(rng, diff, cfg):
    """Вычитание, ответ всегда неотрицательный."""
    hi = max(8, int(round(9 + 90 * diff)))
    a = rng.randint(max(4, hi // 2), hi)
    b = rng.randint(1, max(1, a - 1))
    return f"{a} - {b}", a - b


def _gen_mul(rng, diff, cfg):
    """Таблица умножения на старте, дальше — посложнее."""
    hi = max(5, int(round(6 + 19 * diff)))
    a = rng.randint(2, hi)
    b = rng.randint(2, hi)
    return f"{a} × {b}", a * b


def _gen_div(rng, diff, cfg):
    """Деление всегда без остатка."""
    hi_b = max(3, int(round(3 + 9 * diff)))
    hi_q = max(4, int(round(5 + 20 * diff)))
    b = rng.randint(2, hi_b)
    q = rng.randint(2, hi_q)
    return f"{b * q} ÷ {b}", q


def _atomic(rng, diff, hi):
    """Один целочисленный «кусок» выражения: число, умножение или деление."""
    roll = rng.random()
    if roll < 0.30:
        a, b = rng.randint(2, hi), rng.randint(2, hi)
        return f"{a} × {b}", a * b
    if roll < 0.48:
        b, q = rng.randint(2, max(3, hi // 2)), rng.randint(2, max(3, hi // 2))
        return f"{b * q} ÷ {b}", q
    n = rng.randint(1, hi + 4)
    return str(n), n


def _gen_expr(rng, diff, cfg):
    """Приоритет операций: умножение/деление считаются первыми.

    Куски строятся так, чтобы ответ всегда был целым, а промежуточные
    остатки не уходили в минус.
    """
    hi = max(5, int(round(5 + 15 * diff)))
    pieces = 4 if diff < 0.45 else 5
    if diff > 0.85:
        pieces = 6

    total = 0
    chunks = []
    for i in range(pieces):
        text, value = _atomic(rng, diff, hi)
        if i == 0:
            sign, value = "+", abs(value)
            if not text[0].isdigit():  # «a × b» / «a ÷ b» в начале ставим со знака
                pass
        else:
            prefer_minus = rng.random() < 0.4
            if prefer_minus and total - value < 0:
                prefer_minus = False
            sign = "-" if prefer_minus else "+"
        chunks.append((sign, text, value))
        total += value if sign == "+" else -value

    # «-» перед первым куском в тексте не нужен
    body = chunks[0][1] + "".join(f" {s} {t}" for s, t, _ in chunks[1:])
    return body, total


_GENERATORS = {
    "add": _gen_add,
    "sub": _gen_sub,
    "mul": _gen_mul,
    "div": _gen_div,
    "expr": _gen_expr,
}


def generate(op_id, difficulty=0.3, rng=None):
    """Случайный пример действия `op_id` сложности `difficulty` (0..1)."""
    rng = rng or random
    op = config.operation(op_id)
    diff = min(1.0, max(0.0, float(difficulty)))
    text, answer = _GENERATORS[op_id](rng, diff, op)
    return {"text": text, "answer": int(answer), "op": op_id, "difficulty": diff}


def random_problem(op_ids, difficulty=0.3, rng=None):
    """Пример из одного из доступных действий."""
    rng = rng or random
    if not op_ids:
        op_ids = ["add"]
    return generate(rng.choice(list(op_ids)), difficulty, rng)
