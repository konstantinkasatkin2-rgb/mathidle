"""Состояние игры: деньги, улучшения, престиж, контрольные, сохранения.

Модуль не зависит от pygame — чистая логика, которую можно тестировать
и переиспользовать. Рисование живёт в mathidle/ui.py.
"""

import json
import os
import random
import time

from . import account as account_mod
from . import config, economy, problems

SAVE_VERSION = 2


def save_path():
    """Путь к файлу сохранения (%APPDATA%/mathidle/save.json)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "mathidle")
    return os.path.join(folder, "save.json")


def default_settings():
    """Настройки отображения со значениями по умолчанию."""
    return {s["id"]: s["default"] for s in config.DISPLAY_SETTINGS}


class GameState:
    """Вся прогрессия игрока."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.money = 0.0
        self.run_earned = 0.0        # заработано с прошлого престижа
        self.base_levels = {u["id"]: 0 for u in config.BASE_UPGRADES}
        self.ascensions = {u["id"]: 0 for u in config.BASE_UPGRADES}
        self.grade_levels = {i["id"]: 0 for i in config.GRADE_ITEMS}
        self.prestige_levels = {i["id"]: 0 for i in config.PRESTIGE_ITEMS}
        self.prestige_points = 0.0
        self.prestige_count = 0
        self.unlocked_ops = {"add"}
        self.test_level = 1          # номер следующей контрольной
        self.tests_passed = 0
        self.combo = 0
        self.last_correct_at = 0.0
        self.play_time = 0.0
        self.max_difficulty_solved = 0.0
        self.settings = default_settings()
        self.stats = {
            "solved": 0,
            "wrong": 0,
            "earned": 0.0,
            "passive_earned": 0.0,
            "prestige_points_total": 0.0,
            "tests_passed": 0,
            "idle_examples": 0,
            "best_streak": 0,
            "ascensions": 0,
            "femboy": False,
        }
        # текущий пример
        self.current = None
        self.shown_at = 0.0
        # активная контрольная
        self.test = None
        # события для UI: {"text":..., "kind":..., "until":...}
        self.events = []
        # аккаунт
        self.account = account_mod.AccountClient()
        self.account_token = None
        self.account_username = None
        self._last_sync = 0.0
        self._last_save = 0.0
        self._clock = 0.0
        # скрытое событие «Femboy Futa house»
        self.easter_egg = False
        # сколько пассивные примеры заработали в этой сессии
        self.session_passive = 0.0

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
        if self.account.signed_in:
            self._last_sync += dt
            if self._last_sync >= config.ACCOUNT["autosync_seconds"]:
                self._last_sync = 0.0
                self.sync_to_server(silent=True)

    # ------------------------------------------------------------------
    # Деньги и множители
    # ------------------------------------------------------------------
    def credit(self, amount, passive=False):
        if amount <= 0:
            return 0.0
        self.money += amount
        self.run_earned += amount
        if not passive:
            self.stats["earned"] += amount
        return amount

    def passive_rate(self):
        """Примеров в секунду от узелков/палочек/счётов с учётом вознесений."""
        total = 0.0
        for up in config.BASE_UPGRADES:
            level = self.base_levels.get(up["id"], 0)
            rate = economy.ascension_rate_multiplier(self.ascensions.get(up["id"], 0))
            total += level * up["rate_per_level"] * rate
        return total

    def top_operation(self):
        """Самое «дорогое» открытое действие — по нему считается idle-доход."""
        opened = [op for op in config.OPERATIONS if op["id"] in self.unlocked_ops]
        return opened[-1]["id"] if opened else "add"

    def passive_reward_per_example(self):
        return economy.passive_reward(
            self.top_operation(), self.grade_levels, self.prestige_levels
        )

    def money_mult(self):
        return economy.money_multiplier(self.grade_levels, self.prestige_levels)

    def setting(self, name):
        return self.settings.get(name, True)

    # ------------------------------------------------------------------
    # Базовые улучшения и вознесение
    # ------------------------------------------------------------------
    def upgrade_level(self, up_id):
        return self.base_levels.get(up_id, 0)

    def upgrade_cost(self, up_id):
        up = config.base_upgrade(up_id)
        mult = economy.ascension_cost_multiplier(self.ascensions.get(up_id, 0))
        return economy.upgrade_cost(up, self.upgrade_level(up_id)) * mult

    def upgrade_max_level(self, up_id):
        return config.max_level(config.base_upgrade(up_id))

    def upgrade_full(self, up_id):
        return self.upgrade_level(up_id) >= self.upgrade_max_level(up_id)

    def upgrade_rate(self, up_id):
        up = config.base_upgrade(up_id)
        asc = self.ascensions.get(up_id, 0)
        rate = economy.ascension_rate_multiplier(asc)
        return self.upgrade_level(up_id) * up["rate_per_level"] * rate

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
        asc = self.ascensions.get(up_id, 0)
        suffix = f" (вознесено ×{2 ** asc})" if asc else ""
        self.log(f"{up['name']}: уровень {level} (+{up['rate_per_level']} примера/с){suffix}", "buy")
        return True, f"{up['name']} → ур. {level}"

    def can_ascend(self, up_id):
        """Вознесение доступно на максимуме и после первого престижа."""
        return (
            self.prestige_count >= config.ASCENSION["unlock_after_prestige"]
            and self.upgrade_full(up_id)
        )

    def ascend(self, up_id):
        """Вознесение: уровень на ноль, скорость ×2, цена ×4."""
        if self.prestige_count < config.ASCENSION["unlock_after_prestige"]:
            return False, "Вознесение открывается после первого престижа"
        if not self.upgrade_full(up_id):
            need = self.upgrade_max_level(up_id) - self.upgrade_level(up_id)
            return False, f"Сначала до максимума (ещё {need} ур.)"
        up = config.base_upgrade(up_id)
        self.ascensions[up_id] = self.ascensions.get(up_id, 0) + 1
        self.base_levels[up_id] = 0
        self.stats["ascensions"] += 1
        n = self.ascensions[up_id]
        self.log(
            f"{up['name']} вознесено {n} раз: скорость ×{2 ** n}, цена ×{4 ** n}", "unlock"
        )
        return True, f"{up['name']} вознесено"

    def buy_all_upgrades(self):
        """Купить всё, что позволяет баланс."""
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
    # Престиж
    # ------------------------------------------------------------------
    @property
    def prestige_shop_unlocked(self):
        return self.prestige_count >= 1

    def prestige_unlocked(self):
        """Престиж доступен, когда решён пример сложности 100%."""
        return self.max_difficulty_solved >= config.PRESTIGE["required_difficulty"]

    def prestige_blocked_reason(self):
        if self.prestige_unlocked():
            return ""
        need = config.PRESTIGE["required_difficulty"]
        return (
            f"Нужен пример сложности {int(need * 100)}%. "
            f"Лучший решён: {int(self.max_difficulty_solved * 100)}%"
        )

    def pending_prestige_points(self):
        """Сколько очков престижа набежало за этот забег."""
        return economy.prestige_points(self.run_earned, self.prestige_levels)

    def do_prestige(self):
        """Сбрасывает прогресс и начисляет очки престижа."""
        if not self.prestige_unlocked():
            return False, self.prestige_blocked_reason()
        if self.prestige_count == 0 and self.pending_prestige_points() <= 0:
            return False, "Нужно заработать хотя бы 1 денег"

        gained = self.pending_prestige_points()
        keep = self.money * economy.keep_money_share(self.prestige_levels)

        self.prestige_points += gained
        self.stats["prestige_points_total"] += gained
        self.prestige_count += 1

        # сброс обычных и контрольных улучшений
        for up in config.BASE_UPGRADES:
            self.base_levels[up["id"]] = 0
        for item in config.GRADE_ITEMS:
            if item["effect"] != "unlock":     # открытые операции остаются
                self.grade_levels[item["id"]] = 0

        self.money = keep
        self.run_earned = 0.0
        self.combo = 0
        self.test = None
        self.current = None

        if (self.prestige_count == 1
                and config.PRESTIGE["unlock_mixed_on_first"]
                and "mix" not in self.unlocked_ops):
            self.unlocked_ops.add("mix")
            self.log("Открыты смешанные примеры (несколько действий в одном)", "unlock")

        self.log(
            f"Престиж! +{economy.fmt_money(gained)} очков престижа "
            f"(престиж #{self.prestige_count})", "pass"
        )
        self.next_problem()
        return True, f"Престиж #{self.prestige_count}: +{economy.fmt_money(gained)} очк."

    # ------------------------------------------------------------------
    # Магазин престижных улучшений
    # ------------------------------------------------------------------
    def prestige_level(self, item_id):
        return self.prestige_levels.get(item_id, 0)

    def prestige_cost(self, item_id):
        return economy.prestige_cost(prestige_item(item_id), self.prestige_level(item_id))

    def prestige_full(self, item_id):
        return self.prestige_level(item_id) >= prestige_item(item_id)["max_level"]

    def buy_prestige(self, item_id):
        if not self.prestige_shop_unlocked:
            return False, "Магазин откроется после первого престижа"
        item = prestige_item(item_id)
        if self.prestige_full(item_id):
            return False, "Уже куплено"
        cost = economy.prestige_cost(item, self.prestige_level(item_id))
        if self.prestige_points < cost:
            return False, f"Не хватает {economy.fmt_money(cost - self.prestige_points)} очк."
        self.prestige_points -= cost
        self.prestige_levels[item_id] = self.prestige_level(item_id) + 1

        if item.get("easter_egg"):
            self.easter_egg = True
            self.stats["femboy"] = True
            self.log("Femboy Futa house куплен", "unlock")
            return True, "Femboy Futa house"
        self.log(f"{item['name']}: уровень {self.prestige_levels[item_id]}", "buy")
        return True, f"{item['name']} → ур. {self.prestige_levels[item_id]}"

    # ------------------------------------------------------------------
    # Примеры
    # ------------------------------------------------------------------
    def operation_ids(self, include_mix=True):
        ops = [op["id"] for op in config.OPERATIONS if op["id"] in self.unlocked_ops]
        if not include_mix:
            ops = [o for o in ops if o != "mix"]
        return ops or ["add"]

    def manual_difficulty(self):
        """Сложность обычных примеров растёт вместе с прогрессом."""
        level = max(0, self.test_level - 1)
        value = 0.2 + 0.07 * level
        if self.prestige_shop_unlocked:
            value += 0.05                       # после престижа примеры интереснее
        return min(1.0, value)

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
        self.max_difficulty_solved = max(
            self.max_difficulty_solved, self.current["difficulty"]
        )
        amount = economy.reward(
            self.current["op"], self.current["difficulty"], elapsed, self.combo - 1,
            self.grade_levels, self.prestige_levels,
        )
        self.credit(amount)

        result = {
            "ok": True,
            "amount": amount,
            "elapsed": elapsed,
            "combo": self.combo,
            "speed": economy.speed_factor(elapsed, self.grade_levels, self.prestige_levels),
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

    def speed_window(self):
        """(быстрое окно, медленное окно) в секундах — для шкалы в интерфейсе."""
        fast = config.REWARDS["fast_window"] * economy.speed_multiplier(
            self.grade_levels, self.prestige_levels)
        slow = config.REWARDS["slow_window"] * economy.speed_multiplier(
            self.grade_levels, self.prestige_levels)
        return fast, slow

    def speed_now(self):
        """Текущий множитель скорости для показанного примера."""
        return economy.speed_factor(
            self.now - self.shown_at, self.grade_levels, self.prestige_levels
        )

    # ------------------------------------------------------------------
    # Контрольные
    # ------------------------------------------------------------------
    @property
    def test_started_at(self):
        return self.test["started_at"] if self.test else None

    def test_types_available(self):
        """Виды контрольных, открытые игроку."""
        out = []
        for tt in config.TEST_TYPES:
            if self.tests_passed >= tt["unlock_after"]:
                out.append(tt)
        return out

    def can_start_test(self, test_type_id="test"):
        return (
            self.test is None
            and any(t["id"] == test_type_id for t in self.test_types_available())
            and self.money >= economy.test_price(test_type_id)
        )

    def start_test(self, test_type_id="test"):
        if self.test is not None:
            return False, "Контрольная уже идёт"
        if not any(t["id"] == test_type_id for t in self.test_types_available()):
            return False, "Этот вид проверки ещё не открыт"
        cost = economy.test_price(test_type_id)
        if self.money < cost:
            return False, f"Не хватает {economy.fmt_money(cost - self.money)}"
        self.money -= cost

        level = self.test_level
        count = economy.test_problem_count(level, test_type_id)
        diff = economy.test_difficulty(level, test_type_id, self.prestige_levels)
        ops = self.operation_ids()
        generated, used = problems.test_problems_for(test_type_id, ops, diff, count, self.rng)

        self.test = {
            "level": level,
            "type": test_type_id,
            "problems": generated,
            "ops": used,
            "index": 0,
            "limit": economy.test_time_limit(
                level, self.grade_levels, test_type_id, self.prestige_levels),
            "started_at": self.now,
            "elapsed": 0.0,
            "finished": False,
            "passed": False,
            "difficulty": diff,
        }
        self.current = self.test["problems"][0]
        self.shown_at = self.now
        tt = economy.test_type(test_type_id)
        self.log(
            f"{tt['name']}: {count} примеров на {economy.fmt_time(self.test['limit'])}", "test"
        )
        return True, f"{tt['name']} началась"

    def test_problem(self):
        self.current = self.test["problems"][self.test["index"]]
        self.shown_at = self.now
        return self.current

    def pass_test(self):
        tt = economy.test_type(self.test["type"])
        bonus = economy.test_reward(self.test["level"], self.test["type"])
        self.credit(bonus)
        self.tests_passed += 1
        self.stats["tests_passed"] += 1
        level = self.test["level"]
        spare = self.test["limit"] - self.test["elapsed"]
        first = self.stats["tests_passed"] == 1
        self.test["finished"] = True
        self.test["passed"] = True
        self.test = None
        self.test_level = level + 1
        if tt["id"] == "test":
            self.log(
                f"Контрольная №{level} сдана! +{economy.fmt_money(bonus)}"
                + (" Открыт магазин контрольных улучшений!" if first else ""),
                "pass" if not first else "unlock",
            )
        else:
            self.log(f"{tt['name']} сдана! +{economy.fmt_money(bonus)}", "pass")
        return {
            "passed": True,
            "level": level,
            "kind": tt["id"],
            "name": tt["name"],
            "bonus": bonus,
            "spare": spare,
            "shop_unlocked": first,
        }

    def fail_test(self, reason="wrong"):
        """Провал: билет возвращается полностью, награды нет."""
        kind = self.test["type"] if self.test else "test"
        refund = economy.test_price(kind) * config.TEST["fail_refund"]
        level = self.test["level"] if self.test else self.test_level
        self.credit(refund)
        if self.test:
            self.test["finished"] = True
            self.test["passed"] = False
        self.test = None
        self.combo = 0
        text = "Время вышло!" if reason == "time" else "Ошибка в контрольной"
        name = economy.test_type(kind)["name"]
        self.log(f"{text} {name} провалена, билет возвращён", "fail")
        return {"passed": False, "level": level, "name": name,
                "refund": refund, "reason": reason}

    def abort_test(self):
        if self.test and not self.test["finished"]:
            return self.fail_test(reason="abort")
        return None

    # ------------------------------------------------------------------
    # Аккаунт
    # ------------------------------------------------------------------
    def sign_in(self, username, password):
        """Вход в аккаунт и загрузка сохранения с сервера."""
        try:
            self.account.login(username, password)
        except account_mod.AccountError as exc:
            return False, str(exc)
        self.account_token = self.account.token
        self.account_username = self.account.username
        self._last_sync = 0.0
        try:
            remote = self.account.download_save()
        except account_mod.AccountError as exc:
            return True, f"Вход выполнен, но сохранение не загрузилось: {exc}"
        if remote:
            self.apply_remote(remote)
            return True, f"Вход выполнен, прогресс загружен с сервера"
        self.sync_to_server(silent=True)
        return True, "Вход выполнен, создан новый профиль"

    def register(self, username, password):
        try:
            self.account.register(username, password)
        except account_mod.AccountError as exc:
            return False, str(exc)
        self.account_token = self.account.token
        self.account_username = self.account.username
        self._last_sync = 0.0
        self.sync_to_server(silent=True)
        return True, f"Аккаунт «{username}» создан"

    def apply_remote(self, remote):
        """Подставляет сохранение с сервера, сохраняя настройки этого устройства."""
        keep_settings = dict(self.settings)
        fresh = GameState.from_dict(remote)
        fresh.settings = keep_settings
        fresh.account = self.account
        fresh.account_token = self.account_token
        fresh.account_username = self.account_username
        fresh.easter_egg = self.easter_egg or fresh.stats.get("femboy", False)
        self.__dict__.update(fresh.__dict__)
        self.next_problem()

    def sync_to_server(self, silent=False):
        """Отправляет прогресс на сервер аккаунта."""
        if not self.account.signed_in:
            return False
        try:
            self.account.upload_save(self.to_dict())
            return True
        except account_mod.AccountError as exc:
            if not silent:
                self.log(f"Синхронизация не удалась: {exc}", "fail")
            return False

    def sign_out(self):
        self.sync_to_server(silent=True)
        self.account.logout()
        self.account_token = None
        self.account_username = None
        self._last_sync = 0.0
        return True, "Выход выполнен, прогресс остался на устройстве"

    # ------------------------------------------------------------------
    # События для интерфейса
    # ------------------------------------------------------------------
    def log(self, text, kind="info", ttl=4.5):
        self.events.append({"text": text, "kind": kind, "until": self.now + ttl,
                            "born": self.now})

    # ------------------------------------------------------------------
    # Сохранение
    # ------------------------------------------------------------------
    def to_dict(self):
        return {
            "version": SAVE_VERSION,
            "money": self.money,
            "run_earned": self.run_earned,
            "base_levels": self.base_levels,
            "ascensions": self.ascensions,
            "grade_levels": self.grade_levels,
            "prestige_levels": self.prestige_levels,
            "prestige_points": self.prestige_points,
            "prestige_count": self.prestige_count,
            "unlocked_ops": sorted(self.unlocked_ops),
            "test_level": self.test_level,
            "tests_passed": self.tests_passed,
            "max_difficulty_solved": self.max_difficulty_solved,
            "settings": self.settings,
            "stats": self.stats,
            "play_time": self.play_time,
            "account_username": self.account_username,
            "account_token": self.account_token,
            "saved_at": time.time(),
        }

    @classmethod
    def from_dict(cls, data):
        state = cls()
        state.money = float(data.get("money", 0.0))
        state.run_earned = float(data.get("run_earned", 0.0))
        for up in config.BASE_UPGRADES:
            uid = up["id"]
            state.base_levels[uid] = int((data.get("base_levels") or {}).get(uid, 0))
            state.ascensions[uid] = int((data.get("ascensions") or {}).get(uid, 0))
        for item in config.GRADE_ITEMS:
            state.grade_levels[item["id"]] = int(
                (data.get("grade_levels") or {}).get(item["id"], 0))
        for item in config.PRESTIGE_ITEMS:
            state.prestige_levels[item["id"]] = int(
                (data.get("prestige_levels") or {}).get(item["id"], 0))
        state.prestige_points = float(data.get("prestige_points", 0.0))
        state.prestige_count = int(data.get("prestige_count", 0))
        state.max_difficulty_solved = float(data.get("max_difficulty_solved", 0.0))

        valid = {op["id"] for op in config.OPERATIONS}
        state.unlocked_ops = set(data.get("unlocked_ops") or ["add"]) & valid
        if "add" not in state.unlocked_ops:
            state.unlocked_ops.add("add")

        state.test_level = max(1, int(data.get("test_level", 1)))
        state.tests_passed = int(data.get("tests_passed", 0))
        for key, value in (data.get("stats") or {}).items():
            if key in state.stats:
                state.stats[key] = value
        state.settings = default_settings()
        state.settings.update(data.get("settings") or {})
        state.play_time = float(data.get("play_time", 0.0))
        state.account_username = data.get("account_username")
        state.account_token = data.get("account_token")
        if state.account_token:
            state.account.username = state.account_username
            state.account.token = state.account_token
        state.easter_egg = bool(state.stats.get("femboy", False))
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


def prestige_item(item_id):
    """Престижное улучшение по id."""
    for item in config.PRESTIGE_ITEMS:
        if item["id"] == item_id:
            return item
    raise KeyError(item_id)
