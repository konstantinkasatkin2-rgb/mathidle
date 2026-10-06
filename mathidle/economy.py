"""Экономика: цены улучшений, награды за примеры, форматирование чисел.

Все формулы дублируются в web/game.js. Чтобы числа не разъезжались,
одна и та же логика выгружается в web/balance.json (см. tools/export_balance.py).
"""

from . import config

R = config.REWARDS


# --------------------------------------------------------------------------
# Цены
# --------------------------------------------------------------------------
def upgrade_cost(up, level):
    """Цена следующей покупки базового улучшения.

    `level` — уже купленных уровней, значит покупается n = level + 1.
        квадратичная:  cost_start + cost_step * n * (n - 1)   (узелки, палочки)
        линейная:      cost_start * n                        (счёты)
    """
    n = level + 1
    if up["cost_kind"] == "linear":
        return up["cost_start"] * n
    return up["cost_start"] + up["cost_step"] * n * (n - 1)


def grade_cost(item, level):
    """Цена следующей покупки контрольного улучшения (с ростом цены)."""
    return item["price"] * (item.get("growth", 1.0) ** level)


# --------------------------------------------------------------------------
# Множители
# --------------------------------------------------------------------------
def effect_total(grade_levels, effect):
    """Сумма эффекта контрольных улучшений одного типа."""
    total = 0.0
    for item in config.GRADE_ITEMS:
        if item["effect"] == effect:
            total += item["per_level"] * grade_levels.get(item["id"], 0)
    return total


def money_multiplier(grade_levels):
    """Итоговый множитель денег: 1.0 + бонусы тетрадей."""
    return 1.0 + effect_total(grade_levels, "money_mult")


def speed_multiplier(grade_levels):
    """Во сколько раз шире окно «быстрого» ответа."""
    return 1.0 + effect_total(grade_levels, "speed_window")


def add_multiplier(grade_levels):
    return 1.0 + effect_total(grade_levels, "add_bonus")


def passive_multiplier(grade_levels):
    """Множитель пассивного дохода (Автоответчик)."""
    return 1.0 + effect_total(grade_levels, "passive_share")


def hint_every(grade_levels):
    """Через сколько примеров показывать подсказку (0 — не показывать)."""
    levels = sum(
        grade_levels.get(i["id"], 0)
        for i in config.GRADE_ITEMS
        if i["effect"] == "hint_every"
    )
    if levels <= 0:
        return 0
    return max(4, 10 // levels)


def test_time_bonus(grade_levels):
    return effect_total(grade_levels, "test_time")


# --------------------------------------------------------------------------
# Награды
# --------------------------------------------------------------------------
def difficulty_factor(difficulty):
    """1.0 за самый лёгкий пример, diff_floor за самый сложный."""
    return 1.0 - (1.0 - R["diff_floor"]) * min(1.0, max(0.0, difficulty))


def speed_factor(elapsed, grade_levels=None):
    """1.0 за мгновенный ответ, speed_floor за очень долгий."""
    grade_levels = grade_levels or {}
    fast = R["fast_window"] * speed_multiplier(grade_levels)
    slow = R["slow_window"] * speed_multiplier(grade_levels)
    if elapsed <= fast:
        return 1.0
    if elapsed >= slow:
        return R["speed_floor"]
    k = (elapsed - fast) / (slow - fast)
    return 1.0 - (1.0 - R["speed_floor"]) * k


def combo_bonus(combo):
    """Бонус за серию верных ответов (до +50%)."""
    return min(R["combo_max"], combo * R["combo_step"])


def reward(op_id, difficulty, elapsed, combo=0, grade_levels=None):
    """Деньги за один решённый пример.

    Сложение по ТЗ даёт максимум 0.01: cap 0.01 * 1.0 * 1.0 * множители.
    """
    grade_levels = grade_levels or {}
    op = config.operation(op_id)
    amount = (
        op["cap"]
        * difficulty_factor(difficulty)
        * speed_factor(elapsed, grade_levels)
        * money_multiplier(grade_levels)
        * (1.0 + combo_bonus(combo))
    )
    if op_id == "add":
        amount *= add_multiplier(grade_levels)
    return amount


def passive_reward(op_id, grade_levels=None):
    """Деньги за один автоматически решённый (idle) пример."""
    grade_levels = grade_levels or {}
    op = config.operation(op_id)
    return (
        op["cap"]
        * difficulty_factor(R["idle_difficulty"])
        * money_multiplier(grade_levels)
        * R["passive_share"]
        * passive_multiplier(grade_levels)
    )


def test_reward(level):
    """Награда за пройденную контрольную."""
    return config.TEST["pass_bonus"] + config.TEST["pass_bonus_per_level"] * (level - 1)


def test_problem_count(level):
    t = config.TEST
    return min(t["max_problems"], t["base_problems"] + t["problems_per_level"] * (level - 1))


def test_difficulty(level):
    t = config.TEST
    return min(t["diff_max"], t["diff_base"] + t["diff_per_level"] * (level - 1))


def test_time_limit(level, grade_levels=None):
    t = config.TEST
    count = test_problem_count(level)
    return t["base_time"] + t["time_per_problem"] * count + test_time_bonus(grade_levels or {})


# --------------------------------------------------------------------------
# Форматирование
# --------------------------------------------------------------------------
_SUFFIX = ["", "K", "M", "B", "T", "aa", "ab", "ac"]


def fmt_money(value):
    """Деньги: чем меньше число, тем больше знаков после запятой."""
    v = float(value)
    if v == 0:
        return "0"
    if abs(v) >= 1000:
        n, idx = v, 0
        while abs(n) >= 1000 and idx < len(_SUFFIX) - 1:
            n /= 1000.0
            idx += 1
        return f"{n:.2f}{_SUFFIX[idx]}"
    if abs(v) < 1e-5:
        return f"{v:.2e}".replace("e-0", "e−").replace("e-", "e−")
    if abs(v) < 1:
        return f"{v:.4f}"
    if abs(v - round(v)) < 1e-9 and abs(v) < 1000:
        return str(int(round(v)))
    return f"{v:.3f}"


def fmt_rate(value):
    """Скорость в примерах в секунду."""
    v = float(value)
    if v == 0:
        return "0"
    if abs(v) < 0.01:
        return f"{v:.3f}"
    if abs(v) < 10:
        return f"{v:.2f}"
    return f"{v:.1f}"


def fmt_time(seconds):
    """Человеческое время: 65 → «1м 05с»."""
    s = int(max(0, round(seconds)))
    if s < 60:
        return f"{s}с"
    return f"{s // 60}м {s % 60:02d}с"
