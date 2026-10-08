"""Смоук-тест логики: генераторы, цены, награды, сохранение.

    python tools/selftest.py
"""

import os
import re
import random
import time
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:  # консоль Windows по умолчанию cp1251 — принудительно UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from mathidle import account as account_mod  # noqa: E402
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
    print("Цены: арифметическая прогрессия a1 + (n−1)·d")
    knots = config.base_upgrade("knots")
    sticks = config.base_upgrade("sticks")
    abacus = config.base_upgrade("abacus")

    def costs(up):
        return [round(economy.upgrade_cost(up, lvl), 6) for lvl in range(10)]

    def expected(a1, d):
        return [round(a1 + d * (n - 1), 6) for n in range(1, 11)]

    k, s, a = costs(knots), costs(sticks), costs(abacus)
    check("узелки: a1 = 0.1", k[0] == 0.1, k[0])
    check("узелки: d = 0.2", k == expected(0.1, 0.2), k)
    check("палочки: a1 = 0.3", s[0] == 0.3, s[0])
    check("палочки: d = 0.6", s == expected(0.3, 0.6), s)
    check("счёты: a1 = 0.5", a[0] == 0.5, a[0])
    check("счёты: d = 0.5", a == expected(0.5, 0.5), a)
    # прогрессия возрастающая: каждая следующая цена ровно на d больше
    for up, name in ((knots, "узелки"), (sticks, "палочки"), (abacus, "счёты")):
        diffs = [round(costs(up)[i + 1] - costs(up)[i], 6) for i in range(9)]
        check(f"{name}: шаг прогрессии постоянен = {up['cost_step']}",
              all(abs(d - up["cost_step"]) < 1e-9 for d in diffs), diffs)
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

    # пассивный доход во время игры
    st.money = 0.0
    st.session_passive = 0.0
    st.tick(1.0)
    check("пассивный доход капает", st.money > 0, st.money)
    check("доход учтён в сессии", st.session_passive > 0, st.session_passive)
    check("доход учтён в статистике", st.stats["passive_earned"] > 0,
          st.stats["passive_earned"])
    check("пассив не попадает в «earned» за решение примеров",
          st.stats["earned"] >= 0, st.stats["earned"])

    # пассив капает и пока игрок actively решает примеры
    st2 = state.GameState(rng=random.Random(3))
    st2.next_problem()
    st2.base_levels["knots"] = 1
    st2.money = 0.0
    for _ in range(30):
        st2.tick(0.1)                                   # 3 секунды игры
        st2.submit(str(st2.current["answer"]))         # и активная игра
    check("пассив капает во время активной игры", st2.session_passive > 0,
          st2.session_passive)
    check("сессионный счётчик меньше общего заработка",
          st2.session_passive < st2.stats["earned"], (st2.session_passive, st2.stats["earned"]))

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


def evaluate_expression(text):
    """Независимый вычислитель примера со старшинством операций.

    Сначала выполняет × и ÷, потом складывает и вычитает слева направо.
    Используется только в тестах — чтобы проверить ответ генератора.
    """
    normalized = text.replace("×", "*").replace("÷", "/")
    numbers, ops = [], []
    for token in re.findall(r"\d+|[+\-*/]", normalized):
        if token in "+-*/":
            ops.append(token)
        else:
            numbers.append(int(token))

    # сначала умножение и деление
    i = 0
    while i < len(ops):
        if ops[i] in "*/":
            left, right = numbers[i], numbers[i + 1]
            numbers[i:i + 2] = [left * right if ops[i] == "*" else left // right]
            ops.pop(i)
        else:
            i += 1
    # затем сложение и вычитание
    result = numbers[0]
    for i, op in enumerate(ops):
        result = result + numbers[i + 1] if op == "+" else result - numbers[i + 1]
    return result


def test_mixed_problems():
    print("Смешанные примеры")
    rng = random.Random(11)
    for diff in (0.0, 0.4, 0.7, 1.0):
        texts = []
        for _ in range(300):
            p = problems.generate("mix", diff, rng)
            if not isinstance(p["answer"], int) or p["answer"] < 0:
                check(f"mix@{diff} корректен", False, str(p))
                return
            ops = {sym for sym in ("+", "-", "×", "÷") if sym in p["text"]}
            texts.append(p["text"])
            if len(ops) < 2:
                check(f"mix@{diff} минимум два действия", False, p["text"])
                return
            if evaluate_expression(p["text"]) != p["answer"]:
                check(f"mix@{diff} посчитан верно", False,
                      f"{p['text']} = {p['answer']} (вышло {evaluate_expression(p['text'])})")
                return
        check(f"mix@{diff}: 300 примеров с 2+ действиями и верным ответом", True)
    print(f"  пример: {texts[-1]}")

    # сверяем ответ примера независимым счётом со старшинством операций
    p = problems.generate("mix", 0.5, rng)
    value = evaluate_expression(p["text"])
    check("смешанный пример посчитан верно", value == p["answer"],
          f"{p['text']} = {p['answer']} (независимо {value})")


def test_test_types():
    print("Виды проверок")
    ops = ["add", "sub", "mul"]
    rng = random.Random(5)
    made, used = problems.test_problems_for("test", ops, 0.3, 5, rng)
    check("контрольная берёт ровно 2 операции", len(set(used)) == 2, used)
    check("примеры только из выбранных операций",
          {p["op"] for p in made} <= set(used), {p["op"] for p in made})
    _made, used = problems.test_problems_for("final", ops, 0.3, 5, rng)
    check("итоговая берёт все операции", set(used) == set(ops), used)
    _made, used = problems.test_problems_for("exam", ops, 0.3, 5, rng)
    check("экзамен берёт все операции", set(used) == set(ops), used)

    check("итоговая дороже обычной",
          economy.test_price("final") > economy.test_price("test"))
    check("экзамен дороже итоговой",
          economy.test_price("exam") > economy.test_price("final"))
    check("итоговая сложнее обычной",
          economy.test_difficulty(3, "final") > economy.test_difficulty(3, "test"))
    check("экзамен сложнее итоговой",
          economy.test_difficulty(3, "exam") > economy.test_difficulty(3, "final"))
    check("итоговая платит больше",
          economy.test_reward(3, "final") > economy.test_reward(3, "test"))
    check("экзамен платит больше итоговой",
          economy.test_reward(3, "exam") > economy.test_reward(3, "final"))
    print(f"  цены:    {economy.test_price('test')} / {economy.test_price('final')}"
          f" / {economy.test_price('exam')}")
    print(f"  награда: {economy.test_reward(3)} / {economy.test_reward(3, 'final')}"
          f" / {economy.test_reward(3, 'exam')}")


def test_ascension():
    print("Вознесение улучшений")
    st = state.GameState(rng=random.Random(2))
    ok, msg = st.ascend("knots")
    check("до престижа вознесение закрыто", not ok, msg)

    st.prestige_count = 1
    ok, msg = st.ascend("knots")
    check("вознесение без максимума невозможно", not ok, msg)

    # сравниваем одинаковый уровень до и после вознесения:
    # скорость за уровень удваивается, цена — учетверяется
    st.base_levels["knots"] = 1
    rate_before = st.upgrade_rate("knots")
    cost_before = st.upgrade_cost("knots")

    st.base_levels["knots"] = st.upgrade_max_level("knots")
    ok, msg = st.ascend("knots")
    check("вознесение прошло", ok, msg)
    check("уровень сброшен на ноль", st.upgrade_level("knots") == 0)

    st.base_levels["knots"] = 1
    check("скорость за уровень удвоилась",
          abs(st.upgrade_rate("knots") - rate_before * 2) < 1e-9,
          (st.upgrade_rate("knots"), rate_before))
    check("цена выросла вчетверо",
          abs(st.upgrade_cost("knots") - cost_before * 4) < 1e-9,
          (st.upgrade_cost("knots"), cost_before))
    check("пассивная скорость учитывает вознесение",
          abs(st.passive_rate() - 0.02) < 1e-9, st.passive_rate())

    st.base_levels["knots"] = st.upgrade_max_level("knots")
    st.ascend("knots")
    st.base_levels["knots"] = 1
    check("второе вознесение: скорость ×4",
          abs(st.upgrade_rate("knots") - 0.04) < 1e-9, st.upgrade_rate("knots"))


def test_prestige():
    print("Престиж")
    st = state.GameState(rng=random.Random(4))
    ok, msg = st.do_prestige()
    check("без примера 100% престиж закрыт", not ok, msg)

    st.max_difficulty_solved = 1.0
    st.money = 500.0
    st.run_earned = 500.0
    st.base_levels["knots"] = 5
    st.grade_levels["double_book"] = 2
    st.test_level = 4
    st.tests_passed = 3
    st.unlocked_ops.update({"sub", "mul"})
    check("престиж открыт при 100% сложности", st.prestige_unlocked())

    expected = economy.prestige_points(500.0, st.prestige_levels)
    ok, msg = st.do_prestige()
    check("престиж выполнен", ok, msg)
    check("очки по курсу 1 деньга : 0.00001 очка",
          abs(st.prestige_points - expected) < 1e-12, st.prestige_points)
    check("деньги обнулены", st.money == 0.0, st.money)
    check("обычные улучшения сброшены", st.upgrade_level("knots") == 0)
    check("контрольные улучшения сброшены", st.grade_level("double_book") == 0)
    check("открытые операции сохранены", {"sub", "mul"} <= st.unlocked_ops, st.unlocked_ops)
    check("открыты смешанные примеры", "mix" in st.unlocked_ops, st.unlocked_ops)
    check("магазин престижа открыт", st.prestige_shop_unlocked)
    check("забег обнулён", st.run_earned == 0.0)

    # после престижа всё начинается заново
    check("сложность сброшена", st.max_difficulty_solved == 0.0, st.max_difficulty_solved)
    check("престиж снова закрыт", not st.prestige_unlocked())
    check("номер контрольной сброшен", st.test_level == 1, st.test_level)
    check("счётчик сданных контрольных сброшен", st.tests_passed == 0, st.tests_passed)
    exam = [t for t in config.TEST_TYPES if t["id"] == "exam"][0]
    check("экзамен снова закрыт",
          not any(st.tests_passed >= t["unlock_after"] and t["id"] == "exam"
                  for t in config.TEST_TYPES), exam["unlock_after"])

    st.money = 250.0
    st.run_earned = 250.0
    st.max_difficulty_solved = 1.0
    st.do_prestige()
    check("второй престиж дал больше очков", st.prestige_points > expected,
          st.prestige_points)


def test_prestige_shop():
    print("Магазин престижных улучшений")
    st = state.GameState(rng=random.Random(6))
    st.prestige_count = 1
    ok, msg = st.buy_prestige("pf_money")
    check("без очков не купить", not ok, msg)

    item = [i for i in config.PRESTIGE_ITEMS if i["id"] == "femboy_futa_house"][0]
    check("у него нет эффектов", item["effect"] == "none", item["effect"])
    check("скидка 15%", item["discount"] == 0.15, item["discount"])
    effective = economy.prestige_cost(item, 0)
    check("цена со скидкой ровно 7.21", effective == 7.21, effective)

    others = max(economy.prestige_cost(it, it["max_level"] - 1)
                 for it in config.PRESTIGE_ITEMS if not it.get("easter_egg"))
    check("Femboy Futa house — самая дорогая престижная прокачка",
          effective > others, (effective, others))

    st.prestige_points = 100.0
    before_mult = st.money_mult()
    ok, msg = st.buy_prestige("pf_money")
    check("престижное улучшение куплено", ok, msg)
    check("множитель денег вырос", st.money_mult() > before_mult,
          (before_mult, st.money_mult()))

    ok, msg = st.buy_prestige("femboy_futa_house")
    check("Femboy Futa house куплен", ok, msg)
    check("экран должен потемнеть", st.easter_egg)
    check("повторно не купить", not st.buy_prestige("femboy_futa_house")[0])


def test_account():
    print("Аккаунты")
    check("есть адреса для подключения", len(account_mod.candidate_urls()) >= 1)
    st = state.GameState()
    check("без аккаунта игра работает", not st.account.signed_in)
    check("токен попадает в сохранение", "account_token" in st.to_dict())
    check("настройки переживают сохранение",
          state.GameState.from_dict(st.to_dict()).settings == st.settings)
    partial = state.GameState.from_dict({"settings": {"big_text": True}})
    check("частичные настройки дополняются дефолтами",
          partial.settings["big_text"] and partial.settings["speed_gauge"])


def test_settings():
    print("Настройки отображения")
    st = state.GameState()
    for item in config.DISPLAY_SETTINGS:
        check(f"настройка есть: {item['name']}", item["id"] in st.settings)
    check("окно скорости включено по умолчанию", st.setting("speed_gauge"))
    st.settings["speed_gauge"] = False
    check("окно скорости выключается", not st.setting("speed_gauge"))


def test_mail():
    print("Почта")
    cfg = config.MAIL
    check("награда 100 денег", cfg["reward_money"] == 100.0, cfg["reward_money"])
    check("срок ровно трое суток",
          cfg["expires_in_seconds"] == 3 * 86400, cfg["expires_in_seconds"])
    check("тема письма",
          cfg["welcome_subject"] == "Компенсация за утраченный прогресс",
          cfg["welcome_subject"])
    check("одна почта — один аккаунт", cfg["one_account_per_email"] is True)
    check("в письме есть текст", len(cfg["welcome_body"]) > 40)

    st = state.GameState(rng=random.Random(9))
    check("ящик изначально пуст", st.mail == [] and st.mail_unread == 0)
    before = st.money
    ok, message = st.claim_mail(1)
    check("без аккаунта награду не забрать", ok is False, message)
    check("и деньги не начислились", st.money == before)

    # Письмо, пришедшее на сервер, должно доживать ровно трое суток
    letter = {"id": 1, "reward": 100.0, "expires_at": time.time() + 86400,
              "claimed": False}
    st.mail = [letter]
    check("письмо попало в ящик", len(st.mail) == 1)


def main():
    print("=" * 60)
    print("Math Idle — самопроверка")
    print("=" * 60)
    test_problems()
    test_mixed_problems()
    test_prices()
    test_rewards()
    test_test_types()
    test_ascension()
    test_prestige()
    test_prestige_shop()
    test_account()
    test_settings()
    test_mail()
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
