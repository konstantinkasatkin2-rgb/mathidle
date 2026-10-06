"""Состояние игры: деньги, улучшения, контрольные, сохранения.

Модуль не зависит от pygame — чистая логика, которую можно тестировать
и переиспользовать. Рисование живёт в mathidle/ui.py.
"""

import json
import os
import random
import time

from . import config, economy, problems

SAVE_VERSION = 1


def save_path():
    """Путь к файлу сохранения (%APPDATA%/mathidle/save.json)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "mathidle")
    return os.path.join(folder, "save.json")


class GameState:
    """Вся прогрессия игрока."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.money = 0.0
        self.base_levels = {u["id"]: 0 for u in config.BASE_UPGRADES}
        self.grade_levels = {i["id"]: 0 for i in config.GRADE_ITEMS}
        self.unlocked_ops = {"add"}
        self.test_level = 1          # номер следующей контрольной
        self.tests_passed = 0
        self.combo = 0
        self.last_correct_at = 0.0
        self.play_time = 0.0
        self.stats = {
            "solved": 0,
            "wrong": 0,
            "earned": 0.0,
            "passive_earned": 0.0,
            "tests_passed": 0,
            "idle_examples": 0,
            "best_streak": 0,
        }
        # сколько пассивные примеры заработали в этой сессии (в игре и оффлайн)
        self.session_passive = 0.0
        # текущий пример
        self.current = None
        self.shown_at = 0.0
        # активная контрольная
        self.test = None
        # события для UI: {"text":..., "kind":..., "until":...}
        self.events = []
        self._last_save = 0.0
        self._clock = 0.0

    # ------------------------------------------------------------------
    # Время
    # ------------------------------------------------------------------
    @property
    def now(self):
        return self._clock

    def tick(self, dt):
        """Тик игрового времени: пассивный доход, сброс серии, события."""
        self._clock += dt
        self.play_time += dt
        rate = self.passive_rate()
        if rate > 0:
            gain = rate * dt * self.passive_reward_per_example()
            self.credit(gain, passive=True)
            self.stats["idle_examples"] += rate * dt
            # доход идёт и во время игры — показываем, что он капает
            self.session_passive += gain
            self.stats["passive_earned"] += gain
        if self.combo and self.now - self.last_correct_at > config.REWARDS["combo_decay"]:
            self.combo = 0
        self.events = [e for e in self.events if e["until"] > self.now]
        if self.test and self.test_started_at is not None:
            self.test["elapsed"] = self.now - self.test_started_at
            if self.test["elapsed"] >= self.test["limit"]:
                self.fail_test(reason="time")

    # ------------------------------------------------------------------
    # Деньги и множители
    # ------------------------------------------------------------------
    def credit(self, amount, passive=False):
        if amount <= 0:
            return 0.0
        self.money += amount
        if not passive:
            self.stats["earned"] += amount
        return amount

    def passive_rate(self):
        """Примеров в секунду от узелков/палочек/счётов."""
        total = 0.0
        for up in config.BASE_UPGRADES:
            total += self.base_levels.get(up["id"], 0) * up["rate_per_level"]
        return total

    def top_operation(self):
        """Самое «дорогое» открытое действие — по нему считается idle-доход."""
        opened = [op for op in config.OPERATIONS if op["id"] in self.unlocked_ops]
        return opened[-1]["id"] if opened else "add"

    def passive_reward_per_example(self):
        return economy.passive_reward(self.top_operation(), self.grade_levels)

    def money_mult(self):
        return economy.money_multiplier(self.grade_levels)

    # ------------------------------------------------------------------
    # Базовые улучшения
    # ------------------------------------------------------------------
    def upgrade_level(self, up_id):
        return self.base_levels.get(up_id, 0)

    def upgrade_cost(self, up_id):
        up = config.base_upgrade(up_id)
        return economy.upgrade_cost(up, self.upgrade_level(up_id))

    def upgrade_max_level(self, up_id):
        return config.max_level(config.base_upgrade(up_id))

    def upgrade_full(self, up_id):
        return self.upgrade_level(up_id) >= self.upgrade_max_level(up_id)

    def upgrade_rate(self, up_id):
        up = config.base_upgrade(up_id)
        return self.upgrade_level(up_id) * up["rate_per_level"]

    def buy_upgrade(self, up_id):
        if self.upgrade_full(up_id):
            return False, "Уже максимум"
        cost = self.upgrade_cost(up_id)
        if self.money < cost:
            return False, f"Не хватает {economy.fmt_money(cost - self.money)}"
        self.money -= cost
        self.base_levels[up_id] += 1
        up = config.base_upgrade(up_id)
        level = self.base_levels[up_id]
        self.log(f"{up['name']}: уровень {level} (+{up['rate_per_level']} примера/с)", "buy")
        return True, f"{up['name']} → ур. {level}"

    def buy_all_upgrades(self):
        """Купить всё, что позволяет баланс (кнопка «Купить максимум»)."""
        bought = 0
        spent = 0.0
        while True:
            options = [
                (self.upgrade_cost(u["id"]), u["id"])
                for u in config.BASE_UPGRADES
                if not self.upgrade_full(u["id"])
            ]
            if not options:
                break
            cost, up_id = min(options)
            if self.money < cost:
                break
            self.money -= cost
            spent += cost
            self.base_levels[up_id] += 1
            bought += 1
        if bought:
            self.log(f"Куплено улучшений: {bought} на {economy.fmt_money(spent)}", "buy")
        return bought, spent

    # ------------------------------------------------------------------
    # Магазин контрольных улучшений
    # ------------------------------------------------------------------
    @property
    def shop_unlocked(self):
        return self.tests_passed >= 1

    def grade_level(self, item_id):
        return self.grade_levels.get(item_id, 0)

    def grade_cost(self, item_id):
        return economy.grade_cost(config.grade_item(item_id), self.grade_level(item_id))

    def grade_full(self, item_id):
        return self.grade_level(item_id) >= config.grade_item(item_id)["max_level"]

    def buy_grade(self, item_id):
        if not self.shop_unlocked:
            return False, "Магазин откроется после первой контрольной"
        if self.grade_full(item_id):
            return False, "Уже максимум"
        cost = self.grade_cost(item_id)
        if self.money < cost:
            return False, f"Не хватает {economy.fmt_money(cost - self.money)}"
        self.money -= cost
        self.grade_levels[item_id] += 1
        item = config.grade_item(item_id)
        level = self.grade_levels[item_id]
        if item["effect"] == "unlock":
            self.unlocked_ops.add(item["operation"])
            op = config.operation(item["operation"])
            self.log(f"Открыто действие «{op['name']}»!", "unlock")
            return True, f"Открыто: {op['name']}"
        self.log(f"{item['name']}: уровень {level}", "buy")
        return True, f"{item['name']} → ур. {level}"

    # ------------------------------------------------------------------
    # Примеры
    # ------------------------------------------------------------------
    def operation_ids(self):
        return [op["id"] for op in config.OPERATIONS if op["id"] in self.unlocked_ops]

    def manual_difficulty(self):
        """Сложность обычных примеров растёт вместе с прогрессом."""
        level = max(0, self.test_level - 1)
        return min(0.75, 0.2 + 0.07 * level)

    def next_problem(self):
        if self.test and not self.test["finished"]:
            return self.test_problem()
        self.current = problems.random_problem(
            self.operation_ids(), self.manual_difficulty(), self.rng
        )
        self.shown_at = self.now
        return self.current

    def submit(self, text):
        """Проверяет ответ. Возвращает словарь с результатом."""
        raw = (text or "").strip().replace(",", ".")
        if self.current is None:
            self.next_problem()
        try:
            value = float(raw)
            is_int = float(raw).is_integer()
        except ValueError:
            self.stats["wrong"] += 1
            self.combo = 0
            return {"ok": False, "reason": "empty" if not raw else "parse"}

        expected = self.current["answer"]
        elapsed = self.now - self.shown_at
        correct = (value == expected) if is_int else abs(value - expected) < 1e-9

        if not correct:
            self.stats["wrong"] += 1
            self.combo = 0
            result = {"ok": False, "reason": "wrong", "expected": expected}
            if self.test:
                result["test"] = self.fail_test(reason="wrong")
            return result

        # --- верно ---
        self.stats["solved"] += 1
        self.combo += 1
        self.stats["best_streak"] = max(self.stats["best_streak"], self.combo)
        self.last_correct_at = self.now
        amount = economy.reward(
            self.current["op"], self.current["difficulty"], elapsed, self.combo - 1,
            self.grade_levels,
        )
        self.credit(amount)

        result = {
            "ok": True,
            "amount": amount,
            "elapsed": elapsed,
            "combo": self.combo,
            "speed": economy.speed_factor(elapsed, self.grade_levels),
        }
        if self.test and not self.test["finished"]:
            self.test["index"] += 1
            if self.test["index"] >= len(self.test["problems"]):
                result["test"] = self.pass_test()
            else:
                self.test_problem()
        else:
            self.next_problem()
        return result

    def wants_hint(self):
        """Шпаргалка: подсказка на каждый N-й пример."""
        every = economy.hint_every(self.grade_levels)
        if not every or not self.current:
            return False
        return self.stats["solved"] > 0 and self.stats["solved"] % every == 0

    # ------------------------------------------------------------------
    # Контрольные
    # ------------------------------------------------------------------
    @property
    def test_started_at(self):
        return self.test["started_at"] if self.test else None

    def can_start_test(self):
        return self.test is None and self.money >= config.TEST["entry_price"]

    def start_test(self):
        if self.test is not None:
            return False, "Контрольная уже идёт"
        cost = config.TEST["entry_price"]
        if self.money < cost:
            return False, f"Не хватает {economy.fmt_money(cost - self.money)}"
        self.money -= cost
        level = self.test_level
        count = economy.test_problem_count(level)
        diff = economy.test_difficulty(level)
        ops = self.operation_ids()
        self.test = {
            "level": level,
            "problems": [],
            "index": 0,
            "limit": economy.test_time_limit(level, self.grade_levels),
            "started_at": self.now,
            "elapsed": 0.0,
            "finished": False,
            "passed": False,
            "difficulty": diff,
        }
        for _ in range(count):
            self.test["problems"].append(problems.random_problem(ops, diff, self.rng))
        self.current = self.test["problems"][0]
        self.shown_at = self.now
        self.log(f"Контрольная №{level}: {count} примеров на {economy.fmt_time(self.test['limit'])}", "test")
        return True, f"Контрольная №{level} началась"

    def test_problem(self):
        self.current = self.test["problems"][self.test["index"]]
        self.shown_at = self.now
        return self.current

    def pass_test(self):
        bonus = economy.test_reward(self.test["level"])
        self.credit(bonus)
        self.tests_passed += 1
        self.stats["tests_passed"] += 1
        level = self.test["level"]
        spent = self.test["limit"] - self.test["elapsed"]
        self.test["finished"] = True
        self.test["passed"] = True
        self.test = None
        self.test_level = level + 1
        first = self.stats["tests_passed"] == 1
        self.log(
            f"Контрольная №{level} сдана! +{economy.fmt_money(bonus)}"
            + (" Открыт магазин контрольных улучшений!" if first else ""),
            "pass" if not first else "unlock",
        )
        return {
            "passed": True,
            "level": level,
            "bonus": bonus,
            "spare": spent,
            "shop_unlocked": first,
        }

    def fail_test(self, reason="wrong"):
        """Провал: билет возвращается полностью, награды нет."""
        refund = config.TEST["entry_price"] * config.TEST["fail_refund"]
        level = self.test["level"] if self.test else self.test_level
        self.credit(refund)
        if self.test:
            self.test["finished"] = True
            self.test["passed"] = False
        self.test = None
        self.combo = 0
        text = "Время вышло!" if reason == "time" else "Ошибка в контрольной"
        self.log(f"{text} Контрольная №{level} провалена, билет возвращён", "fail")
        return {"passed": False, "level": level, "refund": refund, "reason": reason}

    def abort_test(self):
        if self.test and not self.test["finished"]:
            return self.fail_test(reason="abort")
        return None

    # ------------------------------------------------------------------
    # События для интерфейса
    # ------------------------------------------------------------------
    def log(self, text, kind="info", ttl=4.5):
        self.events.append({"text": text, "kind": kind, "until": self.now + ttl, "born": self.now})

    # ------------------------------------------------------------------
    # Сохранение
    # ------------------------------------------------------------------
    def to_dict(self):
        return {
            "version": SAVE_VERSION,
            "money": self.money,
            "base_levels": self.base_levels,
            "grade_levels": self.grade_levels,
            "unlocked_ops": sorted(self.unlocked_ops),
            "test_level": self.test_level,
            "tests_passed": self.tests_passed,
            "stats": self.stats,
            "play_time": self.play_time,
            "saved_at": time.time(),
        }

    @classmethod
    def from_dict(cls, data):
        state = cls()
        state.money = float(data.get("money", 0.0))
        for up in config.BASE_UPGRADES:
            state.base_levels[up["id"]] = int(data.get("base_levels", {}).get(up["id"], 0))
        for item in config.GRADE_ITEMS:
            state.grade_levels[item["id"]] = int(data.get("grade_levels", {}).get(item["id"], 0))
        state.unlocked_ops = set(data.get("unlocked_ops") or ["add"]) & {
            op["id"] for op in config.OPERATIONS
        }
        if "add" not in state.unlocked_ops:
            state.unlocked_ops.add("add")
        state.test_level = max(1, int(data.get("test_level", 1)))
        state.tests_passed = int(data.get("tests_passed", 0))
        for key, value in (data.get("stats") or {}).items():
            if key in state.stats:
                state.stats[key] = value
        state.play_time = float(data.get("play_time", 0.0))
        return state

    def save(self, path=None):
        path = path or save_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        self._last_save = self.now
        return path

    @classmethod
    def load(cls, path=None):
        """Читает сохранение; при отсутствии/битой файле — новая игра."""
        path = path or save_path()
        if not os.path.exists(path):
            return cls(), None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cls(), None
        state = cls.from_dict(data)

        # оффлайн-доход
        earned = 0.0
        away = max(0.0, time.time() - float(data.get("saved_at", time.time())))
        if config.OFFLINE["enabled"] and away > 60:
            capped = min(away, config.OFFLINE["cap_hours"] * 3600)
            rate = state.passive_rate()
            if rate > 0:
                earned = (
                    rate
                    * capped
                    * state.passive_reward_per_example()
                    * config.OFFLINE["efficiency"]
                )
                state.credit(earned, passive=True)
        state.next_problem()
        return state, {"away": away, "earned": earned}
