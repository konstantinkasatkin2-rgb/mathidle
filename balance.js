/* СГЕНЕРИРОВАНО АВТОМАТИЧЕСКИ из mathidle/config.py — не редактируй руками.
 * Пересобрать: python tools/export_balance.py
 */
var MATHIDLE_BALANCE = {
 "version": "1.2.5",
 "title": "Math Idle",
 "subtitle": "Решай примеры. Копи деньги. Скушай математику.",
 "base_upgrades": [
  {
   "id": "knots",
   "name": "Узелки",
   "rate_per_level": 0.01,
   "max_rate": 0.1,
   "cost_kind": "arith",
   "cost_start": 0.1,
   "cost_step": 0.2,
   "price_formula": "0.1 + 0.2(n−1)"
  },
  {
   "id": "sticks",
   "name": "Счётные палочки",
   "rate_per_level": 0.03,
   "max_rate": 0.3,
   "cost_kind": "arith",
   "cost_start": 0.3,
   "cost_step": 0.6,
   "price_formula": "0.3 + 0.6(n−1)"
  },
  {
   "id": "abacus",
   "name": "Счёты",
   "rate_per_level": 0.05,
   "max_rate": 0.5,
   "cost_kind": "arith",
   "cost_start": 0.5,
   "cost_step": 0.5,
   "price_formula": "0.5 + 0.5(n−1)"
  }
 ],
 "operations": [
  {
   "id": "add",
   "name": "Сложение",
   "symbol": "+",
   "cap": 0.01,
   "price": null,
   "unlock_id": null,
   "max_terms": 4
  },
  {
   "id": "sub",
   "name": "Вычитание",
   "symbol": "−",
   "cap": 0.02,
   "price": 25,
   "unlock_id": "unlock_sub",
   "max_terms": 3
  },
  {
   "id": "mul",
   "name": "Умножение",
   "symbol": "×",
   "cap": 0.05,
   "price": 120,
   "unlock_id": "unlock_mul",
   "max_terms": 2
  },
  {
   "id": "div",
   "name": "Деление",
   "symbol": "÷",
   "cap": 0.08,
   "price": 500,
   "unlock_id": "unlock_div",
   "max_terms": 2
  },
  {
   "id": "expr",
   "name": "Порядок действий",
   "symbol": "=",
   "cap": 0.12,
   "price": 2000,
   "unlock_id": "unlock_expr",
   "max_terms": 5
  },
  {
   "id": "mix",
   "name": "Смешанные примеры",
   "symbol": "±",
   "cap": 0.2,
   "price": null,
   "unlock_id": null,
   "max_terms": 3,
   "mixed": true
  }
 ],
 "grade_items": [
  {
   "id": "double_book",
   "name": "Двойная тетрадь",
   "desc": "+50% денег за каждый пример",
   "effect": "money_mult",
   "per_level": 0.5,
   "max_level": 20,
   "price": 30,
   "growth": 1.6
  },
  {
   "id": "speed_form",
   "name": "Скоростной бланк",
   "desc": "+40% к окну скорости (быстрее максимум)",
   "effect": "speed_window",
   "per_level": 0.4,
   "max_level": 5,
   "price": 40,
   "growth": 1.8
  },
  {
   "id": "auto_answers",
   "name": "Автоответчик",
   "desc": "+50% денег с пассивных примеров",
   "effect": "passive_share",
   "per_level": 0.5,
   "max_level": 8,
   "price": 60,
   "growth": 1.7
  },
  {
   "id": "cheat_sheet",
   "name": "Шпаргалка",
   "desc": "Подсказка для каждого N-го примера (10, затем 5, затем 4)",
   "effect": "hint_every",
   "per_level": 10,
   "max_level": 3,
   "price": 80,
   "growth": 2.0
  },
  {
   "id": "grid_book",
   "name": "Тетрадь в клетку",
   "desc": "+100% денег за каждый пример",
   "effect": "money_mult",
   "per_level": 1.0,
   "max_level": 10,
   "price": 200,
   "growth": 2.2
  },
  {
   "id": "table_chart",
   "name": "Таблица умножения",
   "desc": "+30% денег за примеры сложения",
   "effect": "add_bonus",
   "per_level": 0.3,
   "max_level": 5,
   "price": 350,
   "growth": 2.0
  },
  {
   "id": "stopwatch",
   "name": "Секундомер",
   "desc": "+2 секунды к лимиту времени на контрольной",
   "effect": "test_time",
   "per_level": 2.0,
   "max_level": 10,
   "price": 150,
   "growth": 1.9
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
   "growth": 1.0
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
   "growth": 1.0
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
   "growth": 1.0
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
   "growth": 1.0
  }
 ],
 "prestige_items": [
  {
   "id": "pf_gain",
   "name": "Жажда знаний",
   "desc": "+20% к очкам престижа",
   "effect": "prestige_gain",
   "per_level": 0.2,
   "max_level": 6,
   "price": 0.1,
   "step": 0.1
  },
  {
   "id": "pf_window",
   "name": "Вечный разгон",
   "desc": "+25% к окну скорости",
   "effect": "speed_window",
   "per_level": 0.25,
   "max_level": 5,
   "price": 0.15,
   "step": 0.15
  },
  {
   "id": "pf_passive",
   "name": "Фоновый доход",
   "desc": "+50% к пассивному доходу",
   "effect": "passive_share",
   "per_level": 0.5,
   "max_level": 5,
   "price": 0.15,
   "step": 0.15
  },
  {
   "id": "pf_purse",
   "name": "Непустой карман",
   "desc": "Сохраняет 10% денег при престиже",
   "effect": "keep_money",
   "per_level": 0.1,
   "max_level": 5,
   "price": 0.2,
   "step": 0.2
  },
  {
   "id": "pf_diff",
   "name": "Сложные билеты",
   "desc": "+5% к сложности контрольных",
   "effect": "test_difficulty",
   "per_level": 0.05,
   "max_level": 4,
   "price": 0.3,
   "step": 0.3
  },
  {
   "id": "pf_time",
   "name": "Дополнительное время",
   "desc": "+10% к лимиту времени на контрольных",
   "effect": "test_time",
   "per_level": 0.1,
   "max_level": 4,
   "price": 0.25,
   "step": 0.25
  },
  {
   "id": "pf_money",
   "name": "Престижная жадность",
   "desc": "+50% к деньгам за пример",
   "effect": "money_mult",
   "per_level": 0.5,
   "max_level": 3,
   "price": 0.4,
   "step": 0.4
  },
  {
   "id": "femboy_futa_house",
   "name": "Femboy Futa house",
   "desc": "Без эффектов. Просто красиво.",
   "effect": "none",
   "per_level": 0,
   "max_level": 1,
   "price": 8.482353,
   "step": 0.0,
   "discount": 0.15,
   "easter_egg": true
  }
 ],
 "prestige": {
  "points_per_money": 1e-05,
  "required_difficulty": 1.0,
  "keep_operations": true,
  "reset_tests": true,
  "reset_difficulty": true,
  "unlock_mixed_on_first": true
 },
 "ascension": {
  "rate_multiplier": 2.0,
  "cost_multiplier": 4.0,
  "unlock_after_prestige": 1
 },
 "test_types": [
  {
   "id": "test",
   "name": "Контрольная",
   "desc": "Две случайные открытые операции",
   "price": 10,
   "ops_mode": "two",
   "diff_bonus": 0.0,
   "problems_mult": 1.0,
   "time_mult": 1.0,
   "reward_mult": 1.0,
   "unlock_after": 0
  },
  {
   "id": "final",
   "name": "Итоговая контрольная",
   "desc": "Все открытые операции, чуть сложнее, награда выше",
   "price": 150,
   "ops_mode": "all",
   "diff_bonus": 0.1,
   "problems_mult": 1.25,
   "time_mult": 1.3,
   "reward_mult": 4.0,
   "unlock_after": 0
  },
  {
   "id": "exam",
   "name": "Экзамен",
   "desc": "Все темы разом, самый высокий уровень и награда",
   "price": 1500,
   "ops_mode": "all_plus_mix",
   "diff_bonus": 0.22,
   "problems_mult": 1.5,
   "time_mult": 1.6,
   "reward_mult": 12.0,
   "unlock_after": 2
  }
 ],
 "display_settings": [
  {
   "id": "speed_gauge",
   "name": "Окно скорости",
   "desc": "Движущаяся шкала времени ответа",
   "default": true
  },
  {
   "id": "difficulty_bar",
   "name": "Полоса сложности",
   "desc": "Насколько трудный текущий пример",
   "default": true
  },
  {
   "id": "event_log",
   "name": "Журнал событий",
   "desc": "Сообщения о покупках и контрольных",
   "default": true
  },
  {
   "id": "passive_counter",
   "name": "Счётчик пассива",
   "desc": "Сколько заработано пассивно за сессию",
   "default": true
  },
  {
   "id": "animations",
   "name": "Анимации",
   "desc": "Всплывающие тексты и мигание",
   "default": true
  },
  {
   "id": "big_text",
   "name": "Крупный текст",
   "desc": "Интерфейс на 15% крупнее",
   "default": false
  },
  {
   "id": "precise_money",
   "name": "Точные деньги",
   "desc": "Показывать 4 знака вместо 3",
   "default": false
  }
 ],
 "rewards": {
  "fast_window": 1.6,
  "slow_window": 8.0,
  "speed_floor": 0.2,
  "diff_floor": 0.35,
  "combo_step": 0.05,
  "combo_max": 0.5,
  "combo_decay": 4.0,
  "passive_share": 0.8,
  "idle_difficulty": 0.15
 },
 "test": {
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
  "fail_refund": 1.0
 },
 "offline": {
  "enabled": true,
  "cap_hours": 8.0,
  "efficiency": 1.0
 },
 "account": {
  "enabled": true,
  "default_url": "",
  "fallback_ports": [
   8766,
   8000
  ],
  "autosync_seconds": 20.0,
  "session_token_days": 30,
  "https_required_hint": "Сайт открыт по HTTPS — сервер аккаунтов тоже должен быть по HTTPS. Запустите его с ключом: bash tools/serve_accounts.sh --https"
 },
 "game": {
  "title": "Math Idle",
  "subtitle": "Решай примеры. Копи деньги. Скушай математику.",
  "version": "1.2.5",
  "window": [
   1280,
   760
  ],
  "autosave_seconds": 5.0,
  "font": "assets/fonts/Roboto-Regular.ttf"
 }
};
