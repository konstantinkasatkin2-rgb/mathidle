"""Проверяет, что JS-порт считает ровно так же, как Python.

Вырезает из web/game.js блок экономики (DOM там не нужен), подставляет тот же
баланс и сравнивает тысячи значений. Нужен node (ставится портативно, без прав
администратора: tools/fetch_toolchain.sh кладёт его в .toolchain/).

Запуск:
    python tools/parity.py
"""

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from mathidle import config, economy  # noqa: E402

GRADE_SETS = [
    {},
    {"double_book": 3},
    {"grid_book": 2, "double_book": 1},
    {"speed_form": 2, "auto_answers": 3, "table_chart": 4},
    {"speed_form": 5, "auto_answers": 8, "table_chart": 5, "double_book": 20},
]

UI_MARKER = "// --------------------------------------------------------------------- UI"
NG = len(GRADE_SETS)


def find_node():
    local = os.path.join(ROOT, ".toolchain", "node_x", "node", "node.exe")
    if os.path.exists(local):
        return local
    for name in ("node", "nodejs"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def scenarios():
    """Список (имя, python-значение, js-выражение, индекс набора улучшений)."""
    out = []

    for idx, up in enumerate(config.BASE_UPGRADES):
        for lvl in range(config.max_level(up)):
            out.append((f"price[{up['id']}][{lvl}]", economy.upgrade_cost(up, lvl),
                        f"r(upgradeCost(B.base_upgrades[{idx}], {lvl}))", None))

    for idx, item in enumerate(config.GRADE_ITEMS):
        for lvl in range(item["max_level"]):
            out.append((f"grade_price[{item['id']}][{lvl}]", economy.grade_cost(item, lvl),
                        f"r(gradeCost(B.grade_items[{idx}], {lvl}))", None))

    for op in config.OPERATIONS:
        for diff in (0.0, 0.25, 0.5, 0.75, 1.0):
            for t in (0.0, 0.5, 1.6, 3.0, 8.0, 30.0):
                for combo in (0, 2, 10):
                    for gi in range(NG):
                        out.append((
                            f"reward[{op['id']},{diff},{t},{combo},g{gi}]",
                            economy.reward(op["id"], diff, t, combo, GRADE_SETS[gi]),
                            f"r(reward('{op['id']}', {diff}, {t}, {combo}))",
                            gi,
                        ))

    for gi in range(NG):
        for op in config.OPERATIONS:
            out.append((f"passive[{op['id']},g{gi}]",
                        economy.passive_reward(op["id"], GRADE_SETS[gi]),
                        f"r(passiveReward('{op['id']}'))", gi))
        out.append((f"test_time_bonus[g{gi}]", economy.test_time_limit(4, GRADE_SETS[gi]),
                    "r(testTimeLimit(4))", gi))
        out.append((f"money_mult[g{gi}]", economy.money_multiplier(GRADE_SETS[gi]),
                    "r(moneyMult())", gi))
        out.append((f"speed_mult[g{gi}]", economy.speed_multiplier(GRADE_SETS[gi]),
                    "r(speedMult())", gi))
        out.append((f"add_mult[g{gi}]", economy.add_multiplier(GRADE_SETS[gi]),
                    "r(addMult())", gi))
        out.append((f"passive_mult[g{gi}]", economy.passive_multiplier(GRADE_SETS[gi]),
                    "r(passiveMult())", gi))
        out.append((f"hint_every[g{gi}]", economy.hint_every(GRADE_SETS[gi]),
                    "r(hintEvery())", gi))

    for level in range(1, 13):
        out.append((f"test_count[{level}]", economy.test_problem_count(level),
                    f"r(testProblemCount({level}))", None))
        out.append((f"test_diff[{level}]", economy.test_difficulty(level),
                    f"r(testDifficulty({level}))", None))
        out.append((f"test_reward[{level}]", economy.test_reward(level),
                    f"r(testReward({level}))", None))

    return out


NODE_PRELUDE = """
const fs = require('fs');
eval(fs.readFileSync(process.argv[2], 'utf8'));       // тот же баланс, что и в web/balance.js
const window = { MATHIDLE_BALANCE: MATHIDLE_BALANCE };
const document = { addEventListener() {}, getElementById() { return null; } };
const localStorage = undefined;

// блок экономики из game.js (DOM начинается с маркера UI)
const src = fs.readFileSync(process.argv[3], 'utf8');
eval(src.slice(src.indexOf('var B ='), src.indexOf(process.argv[4])));

// округляем до 12 знаков, чтобы не спорить с плавающей точкой
function r(v) { return Math.round(v * 1e12) / 1e12; }

const GRADE_SETS = __GRADE_SETS__;
const results = [];
"""


def main():
    node = find_node()
    if node is None:
        print("node не найден — паритет не проверен")
        return 0

    balance_js = os.path.join(ROOT, "web", "balance.js")
    game_js = os.path.join(ROOT, "web", "game.js")
    if not os.path.exists(balance_js):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "export_balance.py")],
                       check=True, capture_output=True)

    cases = scenarios()
    lines = [NODE_PRELUDE.replace("__GRADE_SETS__", json.dumps(GRADE_SETS))]
    current = object()
    for name, _py, expr, gi in cases:
        if gi is not None and gi != current:
            lines.append(f"state.grade = Object.assign({{}}, GRADE_SETS[{gi}]);")
            current = gi
        lines.append(f"results.push([{json.dumps(name)}, {expr}]);")
    lines.append("console.log(JSON.stringify(results));")

    script = os.path.join(ROOT, ".parity.js")
    with open(script, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    proc = subprocess.run(
        [node, script,
         balance_js.replace("\\", "/"), game_js.replace("\\", "/"), UI_MARKER],
        capture_output=True, text=True, encoding="utf-8",
    )
    os.remove(script)

    if proc.returncode != 0:
        print("ошибка node:\n" + proc.stderr[:3000])
        return 1
    try:
        js_results = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print("не удалось разобрать вывод node:\n" + proc.stdout[:2000])
        return 1

    if len(js_results) != len(cases):
        print(f"число проверок разошлось: python={len(cases)} js={len(js_results)}")
        return 1

    bad = []
    for case, js_row in zip(cases, js_results):
        name, py_value = case[0], case[1]
        js_value = js_row[1]
        if abs(float(py_value) - float(js_value)) > 1e-9:
            bad.append((name, py_value, js_value))

    print(f"Проверено значений: {len(cases)}")
    print(f"Расхождений: {len(bad)}")
    for name, py_value, js_value in bad[:20]:
        print(f"  {name}: python={py_value!r} js={js_value!r}")
    if bad:
        return 1
    print("Python и JS считают идентично")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
