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
    Арифметическая прогрессия: цена = a1 + (n − 1)·d
        узелки:   0.1 + 0.2(n−1)   ->  0.1, 0.3, 0.5, ...
        палочки:  0.3 + 0.6(n−1)   ->  0.3, 0.9, 1.5, ...
        счёты:    0.5 + 0.5(n−1)   ->  0.5, 1.0, 1.5, ...
    """
    n = level + 1
    return up["cost_start"] + up["cost_step"] * (n - 1)


def grade_cost(item, level):
    """Цена следующей покупки контрольного улучшения (с ростом цены)."""
    return item["price"] * (item.get("growth", 1.0) ** level)


def ascension_rate_multiplier(ascensions):
    """Во сколько раз улучшение стало лучше после всех вознесений."""
    return config.ASCENSION["rate_multiplier"] ** max(0, ascensions)


def ascension_cost_multiplier(ascensions):
    """Во сколько раз улучшение стало дороже после всех вознесений."""
    return config.ASCENSION["cost_multiplier"] ** max(0, ascensions)


def prestige_cost(item, level):
    """Цена следующей покупки престижного улучшения: price + step·(n−1).

    Для «Femboy Futa house» действует скидка из конфига.
    """
    discount = item.get("discount", 0.0)
    price = item["price"] * (1.0 - discount)
    return round(price + item.get("step", 0.0) * level, 6)


def prestige_base_price(item):
    """Цена первой покупки с учётом скидки."""
    return prestige_cost(item, 0)


def prestige_effect_total(prestige_levels, effect):
    """Сумма эффекта престижных улучшений одного типа."""
    total = 0.0
    for item in config.PRESTIGE_ITEMS:
        if item["effect"] == effect:
            total += item["per_level"] * prestige_levels.get(item["id"], 0)
    return total


def prestige_points(earned, prestige_levels=None):
    """Очки престижа за заработанные деньги: 1 деньга : 0.01 очка."""
    multiplier = 1.0
    if prestige_levels:
        multiplier = 1.0 + prestige_effect_total(prestige_levels, "prestige_gain")
    return earned * config.PRESTIGE["points_per_money"] * multiplier


def test_type(test_type_id):
    """Описание вида контрольной по id."""
    for tt in config.TEST_TYPES:
        if tt["id"] == test_type_id:
            return tt
    raise KeyError(test_type_id)


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


def money_multiplier(grade_levels, prestige_levels=None):
    """Итоговый множитель денег: 1.0 + бонусы тетрадей + престижа."""
    total = 1.0 + effect_total(grade_levels, "money_mult")
    if prestige_levels:
        total += prestige_effect_total(prestige_levels, "money_mult")
    return total


def speed_multiplier(grade_levels, prestige_levels=None):
    """Во сколько раз шире окно «быстрого» ответа."""
    total = 1.0 + effect_total(grade_levels, "speed_window")
    if prestige_levels:
        total += prestige_effect_total(prestige_levels, "speed_window")
    return total


def add_multiplier(grade_levels):
    return 1.0 + effect_total(grade_levels, "add_bonus")


def passive_multiplier(grade_levels, prestige_levels=None):
    """Множитель пассивного дохода (Автоответчик + престиж)."""
    total = 1.0 + effect_total(grade_levels, "passive_share")
    if prestige_levels:
        total += prestige_effect_total(prestige_levels, "passive_share")
    return total


def keep_money_share(prestige_levels):
    """Доля денег, которая переживает престиж."""
    return prestige_effect_total(prestige_levels or {}, "keep_money")


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


def speed_factor(elapsed, grade_levels=None, prestige_levels=None):
    """1.0 за мгновенный ответ, speed_floor за очень долгий."""
    grade_levels = grade_levels or {}
    prestige_levels = prestige_levels or {}
    fast = R["fast_window"] * speed_multiplier(grade_levels, prestige_levels)
    slow = R["slow_window"] * speed_multiplier(grade_levels, prestige_levels)
    if elapsed <= fast:
        return 1.0
    if elapsed >= slow:
        return R["speed_floor"]
    k = (elapsed - fast) / (slow - fast)
    return 1.0 - (1.0 - R["speed_floor"]) * k


def combo_bonus(combo):
    """Бонус за серию верных ответов (до +50%)."""
    return min(R["combo_max"], combo * R["combo_step"])


def reward(op_id, difficulty, elapsed, combo=0, grade_levels=None, prestige_levels=None):
    """Деньги за один решённый пример.

    Сложение по ТЗ даёт максимум 0.01: cap 0.01 * 1.0 * 1.0 * множители.
    """
    grade_levels = grade_levels or {}
    prestige_levels = prestige_levels or {}
    op = config.operation(op_id)
    amount = (
        op["cap"]
        * difficulty_factor(difficulty)
        * speed_factor(elapsed, grade_levels, prestige_levels)
        * money_multiplier(grade_levels, prestige_levels)
        * (1.0 + combo_bonus(combo))
    )
    if op_id == "add":
        amount *= add_multiplier(grade_levels)
    return amount


def passive_reward(op_id, grade_levels=None, prestige_levels=None):
    """Деньги за один автоматически решённый (idle) пример."""
    grade_levels = grade_levels or {}
    prestige_levels = prestige_levels or {}
    op = config.operation(op_id)
    return (
        op["cap"]
        * difficulty_factor(R["idle_difficulty"])
        * money_multiplier(grade_levels, prestige_levels)
        * R["passive_share"]
        * passive_multiplier(grade_levels, prestige_levels)
    )


def test_reward(level, test_type_id="test"):
    """Награда за пройденную контрольную с учётом вида проверки."""
    tt = test_type(test_type_id)
    base = config.TEST["pass_bonus"] + config.TEST["pass_bonus_per_level"] * (level - 1)
    return base * tt["reward_mult"]


def test_problem_count(level, test_type_id="test"):
    tt = test_type(test_type_id)
    base = min(
        config.TEST["max_problems"],
        config.TEST["base_problems"] + config.TEST["problems_per_level"] * (level - 1),
    )
    return max(1, int(round(base * tt["problems_mult"])))


def test_difficulty(level, test_type_id="test", prestige_levels=None):
    """Сложность примеров в контрольной: база + уровень + бонус вида + престиж."""
    tt = test_type(test_type_id)
    t = config.TEST
    base = t["diff_base"] + t["diff_per_level"] * (level - 1)
    value = base + tt["diff_bonus"]
    if prestige_levels:
        value += prestige_effect_total(prestige_levels, "test_difficulty")
    return min(t["diff_max"], value)


def test_price(test_type_id="test"):
    return test_type(test_type_id)["price"]


def test_time_limit(level, grade_levels=None, test_type_id="test", prestige_levels=None):
    """Лимит времени на контрольную с учётом вида проверки и улучшений."""
    tt = test_type(test_type_id)
    t = config.TEST
    count = test_problem_count(level, test_type_id)
    base = t["base_time"] + t["time_per_problem"] * count
    base = base * tt["time_mult"] + test_time_bonus(grade_levels or {})
    if prestige_levels:
        base *= 1.0 + prestige_effect_total(prestige_levels, "test_time")
    return base


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
