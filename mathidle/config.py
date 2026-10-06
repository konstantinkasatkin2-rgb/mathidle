"""ЕДИНЫЙ ИСТОЧНИК БАЛАНСА.

Все числа игры живут здесь. Файл `tools/export_balance.py` выгружает этот
словарь в `web/balance.json`, а JS-порт читает его оттуда — поэтому Python
и HTML5 версии считают деньги совершенно одинаково.

Правка баланса делается ТОЛЬКО здесь.
"""

# --------------------------------------------------------------------------
# Базовые улучшения (основной магазин)
#
# Цена n-й покупки (n = 1, 2, 3, ...) по ТЗ:
# Цена n-й покупки (n = 1, 2, 3, ...) — арифметическая прогрессия:
#     цена = a1 + (n − 1)·d
#   «Узелки»            a1 = 0.1, d = 0.2   ->  0.1, 0.3, 0.5, ... 1.9
#   «Счётные палочки»   a1 = 0.3, d = 0.6   ->  0.3, 0.9, 1.5, ... 5.7
#   «Счёты»             a1 = 0.5, d = 0.5   ->  0.5, 1.0, 1.5, ... 5.0
# В скобках — максимальная суммарная скорость в примерах/сек.
# --------------------------------------------------------------------------
BASE_UPGRADES = [
    {
        "id": "knots",
        "name": "Узелки",
        "rate_per_level": 0.01,
        "max_rate": 0.1,
        "cost_kind": "arith",
        "cost_start": 0.1,
        "cost_step": 0.2,
        "price_formula": "0.1 + 0.2(n−1)",
    },
    {
        "id": "sticks",
        "name": "Счётные палочки",
        "rate_per_level": 0.03,
        "max_rate": 0.3,
        "cost_kind": "arith",
        "cost_start": 0.3,
        "cost_step": 0.6,
        "price_formula": "0.3 + 0.6(n−1)",
    },
    {
        "id": "abacus",
        "name": "Счёты",
        "rate_per_level": 0.05,
        "max_rate": 0.5,
        "cost_kind": "arith",
        "cost_start": 0.5,
        "cost_step": 0.5,
        "price_formula": "0.5 + 0.5(n−1)",
    },
]

# --------------------------------------------------------------------------
# Математические действия.
# `cap` — максимум денег за один пример этого действия (с учётом скорости
# и множителей). Сложение по ТЗ даёт максимум 0.01.
# `price` — цена открытия в магазине контрольных улучшений (None — открыто сразу).
# --------------------------------------------------------------------------
OPERATIONS = [
    {
        "id": "add",
        "name": "Сложение",
        "symbol": "+",
        "cap": 0.01,
        "price": None,
        "unlock_id": None,
        "max_terms": 4,
    },
    {
        "id": "sub",
        "name": "Вычитание",
        "symbol": "−",
        "cap": 0.02,
        "price": 25,
        "unlock_id": "unlock_sub",
        "max_terms": 3,
    },
    {
        "id": "mul",
        "name": "Умножение",
        "symbol": "×",
        "cap": 0.05,
        "price": 120,
        "unlock_id": "unlock_mul",
        "max_terms": 2,
    },
    {
        "id": "div",
        "name": "Деление",
        "symbol": "÷",
        "cap": 0.08,
        "price": 500,
        "unlock_id": "unlock_div",
        "max_terms": 2,
    },
    {
        "id": "expr",
        "name": "Порядок действий",
        "symbol": "=",
        "cap": 0.12,
        "price": 2000,
        "unlock_id": "unlock_expr",
        "max_terms": 5,
    },
]

# --------------------------------------------------------------------------
# Магазин контрольных улучшений (открывается после первой контрольной).
# `effect` + `per_level` — повторяемые улучшения, `max_level` ограничивает.
# Одноразовые — те, у кого max_level == 1.
# --------------------------------------------------------------------------
GRADE_ITEMS = [
    {
        "id": "double_book",
        "name": "Двойная тетрадь",
        "desc": "+50% денег за каждый пример",
        "effect": "money_mult",
        "per_level": 0.5,
        "max_level": 20,
        "price": 30,
        "growth": 1.6,
    },
    {
        "id": "speed_form",
        "name": "Скоростной бланк",
        "desc": "+40% к окну скорости (быстрее максимум)",
        "effect": "speed_window",
        "per_level": 0.4,
        "max_level": 5,
        "price": 40,
        "growth": 1.8,
    },
    {
        "id": "auto_answers",
        "name": "Автоответчик",
        "desc": "+50% денег с пассивных примеров",
        "effect": "passive_share",
        "per_level": 0.5,
        "max_level": 8,
        "price": 60,
        "growth": 1.7,
    },
    {
        "id": "cheat_sheet",
        "name": "Шпаргалка",
        "desc": "Подсказка для каждого N-го примера (10, затем 5, затем 4)",
        "effect": "hint_every",
        "per_level": 10,
        "max_level": 3,
        "price": 80,
        "growth": 2.0,
    },
    {
        "id": "grid_book",
        "name": "Тетрадь в клетку",
        "desc": "+100% денег за каждый пример",
        "effect": "money_mult",
        "per_level": 1.0,
        "max_level": 10,
        "price": 200,
        "growth": 2.2,
    },
    {
        "id": "table_chart",
        "name": "Таблица умножения",
        "desc": "+30% денег за примеры сложения",
        "effect": "add_bonus",
        "per_level": 0.3,
        "max_level": 5,
        "price": 350,
        "growth": 2.0,
    },
    {
        "id": "stopwatch",
        "name": "Секундомер",
        "desc": "+2 секунды к лимиту времени на контрольной",
        "effect": "test_time",
        "per_level": 2.0,
        "max_level": 10,
        "price": 150,
        "growth": 1.9,
    },
    {
        "id": "unlock_sub",
        "name": "Вычитание",
        "desc": "Открывает новое математическое действие",
        "effect": "unlock",
        "operation": "sub",
        "per_level": 0,
        "max_level": 1,
        "price": 25,
        "growth": 1.0,
    },
    {
        "id": "unlock_mul",
        "name": "Умножение",
        "desc": "Открывает новое математическое действие",
        "effect": "unlock",
        "operation": "mul",
        "per_level": 0,
        "max_level": 1,
        "price": 120,
        "growth": 1.0,
    },
    {
        "id": "unlock_div",
        "name": "Деление",
        "desc": "Открывает новое математическое действие",
        "effect": "unlock",
        "operation": "div",
        "per_level": 0,
        "max_level": 1,
        "price": 500,
        "growth": 1.0,
    },
    {
        "id": "unlock_expr",
        "name": "Порядок действий",
        "desc": "Открывает примеры со скобками и приоритетом",
        "effect": "unlock",
        "operation": "expr",
        "per_level": 0,
        "max_level": 1,
        "price": 2000,
        "growth": 1.0,
    },
]

# --------------------------------------------------------------------------
# Награда за примеры
# --------------------------------------------------------------------------
REWARDS = {
    # окно скорости: до fast_window — полная награда, дальше плавно падает
    "fast_window": 1.6,
    "slow_window": 8.0,
    "speed_floor": 0.2,   # минимум скоростного множителя
    "diff_floor": 0.35,   # множитель за самую сложную задачу
    "combo_step": 0.05,   # +5% за серию
    "combo_max": 0.5,     # максимум +50% за серию
    "combo_decay": 4.0,   # через сколько секунд серия сбрасывается
    "passive_share": 0.8, # доля награды, которую платит пассивный пример
    "idle_difficulty": 0.15,
}

# --------------------------------------------------------------------------
# Контрольная
# --------------------------------------------------------------------------
TEST = {
    "entry_price": 10,
    "base_problems": 5,
    "problems_per_level": 2,
    "max_problems": 15,
    "base_time": 25.0,
    "time_per_problem": 4.0,
    "diff_base": 0.15,
    "diff_per_level": 0.12,
    "diff_max": 1.0,
    "pass_bonus": 5.0,
    "pass_bonus_per_level": 2.5,
    "fail_refund": 1.0,   # при провале возвращаем цену билета
}

# --------------------------------------------------------------------------
# Оффлайн-доход (idle)
# --------------------------------------------------------------------------
OFFLINE = {
    "enabled": True,
    "cap_hours": 8.0,
    "efficiency": 1.0,   # доля пассивного дохода, начисляемого за время отсутствия
}

# --------------------------------------------------------------------------
# Прочее
# --------------------------------------------------------------------------
GAME = {
    "title": "Math Idle",
    "subtitle": "Решай примеры. Копи деньги. Скушай математику.",
    "version": "1.1.0",
    "window": [1280, 760],
    "autosave_seconds": 5.0,
    "font": "assets/fonts/Roboto-Regular.ttf",
}


def operation(op_id):
    """Математическое действие по id."""
    for op in OPERATIONS:
        if op["id"] == op_id:
            return op
    raise KeyError(op_id)


def base_upgrade(up_id):
    for up in BASE_UPGRADES:
        if up["id"] == up_id:
            return up
    raise KeyError(up_id)


def grade_item(item_id):
    for it in GRADE_ITEMS:
        if it["id"] == item_id:
            return it
    raise KeyError(item_id)


def max_level(up):
    """Сколько уровней можно купить, до достижения максимальной скорости."""
    return int(round(up["max_rate"] / up["rate_per_level"]))


def balance_dict():
    """Всё, что нужно фронтенду (JS-порту)."""
    return {
        "version": GAME["version"],
        "title": GAME["title"],
        "subtitle": GAME["subtitle"],
        "base_upgrades": BASE_UPGRADES,
        "operations": OPERATIONS,
        "grade_items": GRADE_ITEMS,
        "rewards": REWARDS,
        "test": TEST,
        "offline": OFFLINE,
        "game": GAME,
    }
