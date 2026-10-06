"""Смоук-тест логики: генераторы, цены, награды, сохранение.

    python tools/selftest.py
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:  # консоль Windows по умолчанию cp1251 — принудительно UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from mathidle import config, economy, problems, state  # noqa: E402

FAILS = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def test_problems():
    print("Генераторы примеров")
    rng = random.Random(7)
    ops = [op["id"] for op in config.OPERATIONS]
    for op_id in ops:
        for diff in (0.0, 0.35, 0.7, 1.0):
            for _ in range(200):
                p = problems.generate(op_id, diff, rng)
                if not isinstance(p["answer"], int):
                    check(f"{op_id}@ {diff} целый ответ", False, str(p))
                    return
                if p["answer"] < 0:
                    check(f"{op_id}@{diff} неотрицательный ответ", False, str(p))
                    return
                if "?" in p["text"] or "None" in p["text"]:
                    check(f"{op_id}@{diff} текст", False, p["text"])
                    return
        check(f"{op_id}: 800 примеров без мусора", True)
    # сложность растёт
    easy = problems.generate("add", 0.05, rng)
    hard = problems.generate("add", 1.0, rng)
    check("сложное сложение длиннее", len(hard["text"]) >= len(easy["text"]))
    print(f"  пример: add 0.05 -> '{easy['text']}' = {easy['answer']}")
    print(f"  пример: expr 0.9 -> "
          f"'{problems.generate('expr', 0.9, rng)['text']}'")


def test_prices():
    print("Цены по формулам из ТЗ")
    knots = config.base_upgrade("knots")
    sticks = config.base_upgrade("sticks")
    abacus = config.base_upgrade("abacus")

    def costs(up):
        return [round(economy.upgrade_cost(up, lvl), 6) for lvl in range(10)]

    k, s, a = costs(knots), costs(sticks), costs(abacus)
    check("узелки: старт 0.1", k[0] == 0.1, k[0])
    check("узелки: n(n-1)+0.2", [round(x, 6) for x in k] ==
          [round(0.1 + 0.2 * n * (n - 1), 6) for n in range(1, 11)])
    check("палочки: старт 0.3", s[0] == 0.3, s[0])
    check("палочки: n(n-1)+0.6", [round(x, 6) for x in s] ==
          [round(0.3 + 0.6 * n * (n - 1), 6) for n in range(1, 11)])
    check("счёты: старт 0.5", a[0] == 0.5, a[0])
    check("счёты: 0.5n", [round(x, 6) for x in a] == [round(0.5 * n, 6) for n in range(1, 11)])
    check("макс уровней = 10", config.max_level(knots) == config.max_level(sticks)
          == config.max_level(abacus) == 10)
    check("макс скорость 0.1/0.3/0.5",
          (knots["max_rate"], sticks["max_rate"], abacus["max_rate"]) == (0.1, 0.3, 0.5))
    print(f"  узелки:    {k}")
    print(f"  палочки:   {s}")
    print(f"  счёты:     {a}")
    print(f"  всего:     {round(sum(k) + sum(s) + sum(a), 2)}")


def test_rewards():
    print("Награды")
    empty = {}
    best = economy.reward("add", 0.0, 0.0, 0, empty)
    check("сложение максимум 0.01", abs(best - 0.01) < 1e-9, best)
    slow = economy.reward("add", 0.0, 60.0, 0, empty)
    check("медленный ответ дешевле", slow < best, slow)
    hard = economy.reward("add", 1.0, 0.0, 0, empty)
    check("сложный пример дешевле", hard < best, hard)
    combo = economy.reward("add", 0.0, 0.0, 10, empty)
    check("серия даёт +50%", abs(combo - best * 1.5) < 1e-9, combo)
    check("вычитание дороже сложения", economy.reward("sub", 0.0, 0.0, 0, empty) > best)
    boosted = economy.reward("add", 0.0, 0.0, 0, {"double_book": 2})
    check("тетрадь умножает деньги", abs(boosted - best * 2.0) < 1e-9, boosted)
    print(f"  быстро и легко: {best}, медленно: {round(slow, 5)}, сложно: {round(hard, 5)}")
    print(f"  формат денег: {economy.fmt_money(0.01234)} {economy.fmt_money(1234.5)} "
          f"{economy.fmt_money(4.2e-7)}")


def test_flow():
    print("Игровой цикл")
    st = state.GameState(rng=random.Random(1))
    st.next_problem()
    check("стартовый пример — сложение", st.current["op"] == "add")

    # решаем 500 примеров «мгновенно»
    for _ in range(500):
        st.submit(str(st.current["answer"]))
    check("500 примеров решено", st.stats["solved"] == 500, st.stats["solved"])
    check("деньги начислены", st.money > 0, st.money)
    money_after = st.money

    # покупаем узелки
    ok, _ = st.buy_upgrade("knots")
    check("узелки куплены", ok and st.upgrade_level("knots") == 1)
    check("скорость 0.01/с", abs(st.passive_rate() - 0.01) < 1e-9, st.passive_rate())

    # копим до билетa на контрольную
    st.money = 10.0
    ok, msg = st.start_test()
    check("контрольная началась", ok, msg)
    check("билет списан", st.money == 0.0, st.money)
    n = len(st.test["problems"])
    for _ in range(n):
        st.submit(str(st.current["answer"]))
    check("контрольная засчитана", st.tests_passed == 1, st.tests_passed)
    check("магазин открылся", st.shop_unlocked)
    check("награда выдана", st.money >= economy.test_reward(1) - 1e-9, st.money)
    check("следующая контрольная сложнее",
          economy.test_problem_count(2) > economy.test_problem_count(1))

    # магазин
    st.money = 10_000.0
    ok, _ = st.buy_grade("unlock_mul")
    check("умножение открылось", ok and "mul" in st.unlocked_ops)
    ok, _ = st.buy_grade("double_book")
    check("тетрадь куплена", ok and st.money_mult() == 1.5, st.money_mult())

    # пассивный доход
    st.money = 0.0
    st.tick(1.0)
    check("пассивный доход капает", st.money > 0, st.money)

    # провал контрольной
    st.test_level = 3
    st.money = 10.0
    st.start_test()
    balance = st.money
    st.submit("999999")
    check("ошибка валит контрольную", st.test is None)
    check("билет возвращён", abs(st.money - (balance + 10)) < 1e-9, st.money)

    # сохранение
    path = os.path.join(ROOT, ".selftest-save.json")
    st.save(path)
    loaded, welcome = state.GameState.load(path)
    check("сохранение читается", abs(loaded.money - st.money) < 1e-6, loaded.money)
    check("уровни сохраняются", loaded.base_levels == st.base_levels)
    check("действия сохраняются", loaded.unlocked_ops == st.unlocked_ops)
    os.remove(path)


def test_upgrade_ladder():
    print("Потолки улучшений")
    st = state.GameState(rng=random.Random(2))
    st.money = 1e9
    bought, spent = st.buy_all_upgrades()
    check("купилось 30 уровней", bought == 30, bought)
    check("скорость 0.9 примера/с", abs(st.passive_rate() - 0.9) < 1e-9, st.passive_rate())
    check("все улучшения на максимуме",
          all(st.upgrade_full(u["id"]) for u in config.BASE_UPGRADES))
    ok, _ = st.buy_upgrade("knots")
    check("больше максимума нельзя", not ok)
    print(f"  потрачено {economy.fmt_money(spent)}, доход "
          f"{economy.fmt_money(st.passive_rate() * st.passive_reward_per_example())}/с")


def main():
    print("=" * 60)
    print("Math Idle — самопроверка")
    print("=" * 60)
    test_problems()
    test_prices()
    test_rewards()
    test_flow()
    test_upgrade_ladder()
    print("=" * 60)
    if FAILS:
        print(f"ПРОВАЛЕНО {len(FAILS)}: {FAILS}")
        return 1
    print("Все проверки пройдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
