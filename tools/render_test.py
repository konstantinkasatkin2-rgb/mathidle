"""Рендер-тест: проверяет шрифт и рисует кадры игры в PNG (без окна).

    python tools/render_test.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from mathidle import assets, config, economy, state, ui  # noqa: E402

OUT = os.path.join(ROOT, ".render")


def check_glyphs(fonts):
    """Все символы интерфейса должны быть в шрифте."""
    sample = (
        "".join(op["name"] + op["symbol"] for op in config.OPERATIONS)
        + "".join(up["name"] for up in config.BASE_UPGRADES)
        + "".join(item["name"] + item["desc"] for item in config.GRADE_ITEMS)
        + "Деньги за пример серия скорость сложность Контрольная Магазин Улучшения "
        "Прервать Начать купить максимум узелки счётные палочки счёты ×÷− "
        "0123456789.,-+=()!?%/ abcdefghijklmnopqrstuvwxyz"
        "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    )
    missing = fonts.missing_glyphs(sample)
    ok = not missing
    print(f"  шрифт {config.GAME['font']}: "
          + ("все символы на месте" if ok else f"НЕТ {missing}"))
    return ok


def render(label, st, seconds=0.2, tabs=("upgrades",), input_text="", modal=None):
    """Прогоняет несколько кадров и сохраняет скриншот."""
    pygame.init()
    screen = pygame.display.set_mode((ui.W, ui.H))
    canvas = pygame.Surface((ui.W, ui.H))
    game = ui.GameUI(st)
    frames = max(1, int(seconds * 60))
    for tab in tabs:
        game.tab = tab
        game.input = input_text
        for _ in range(frames):
            st.tick(1 / 60)
            game.update(1 / 60)
            game.draw(canvas, screen)
        game.scroll[game.tab] = 0
        pygame.image.save(canvas, os.path.join(OUT, f"{label}_{tab}.png"))
    if modal:
        game.modal = modal
        game.draw(canvas, screen)
        pygame.image.save(canvas, os.path.join(OUT, f"{label}_modal.png"))
    pygame.quit()


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    fonts = assets.FontBook()
    fonts_ok = check_glyphs(fonts)
    pygame.quit()

    st = state.GameState(rng=__import__("random").Random(3))
    st.next_problem()
    for _ in range(30):
        st.submit(str(st.current["answer"]))
    st.money = 12.0
    st.buy_upgrade("knots")
    st.buy_upgrade("sticks")
    for _ in range(30):
        st.tick(0.1)
    render("play", st, input_text="42", tabs=("upgrades",))

    st2 = state.GameState(rng=__import__("random").Random(4))
    st2.next_problem()
    st2.money = 40.0
    st2.start_test()
    st2.submit(str(st2.current["answer"]))
    render("test", st2, tabs=("test",), input_text="7")

    st3 = state.GameState(rng=__import__("random").Random(5))
    st3.next_problem()
    st3.money = 5000.0
    st3.tests_passed = 2
    st3.grade_levels["double_book"] = 4
    st3.unlocked_ops.update({"sub", "mul"})
    for _ in range(20):
        st3.submit(str(st3.current["answer"]))
    render("shop", st3, tabs=("shop", "upgrades"))

    st4 = state.GameState(rng=__import__("random").Random(6))
    st4.next_problem()
    st4.money = 10.0
    st4.start_test()
    for _ in range(len(st4.test["problems"])):
        st4.submit(str(st4.current["answer"]))
    passed = {"passed": True, "level": 1, "bonus": economy.test_reward(1), "spare": 12.3,
              "shop_unlocked": True}
    render("result", st4, tabs=("upgrades",), modal={
        "title": "Сдано!", "lines": ["Контрольная №1 сдана", "Награда: +5",
                                    "Осталось времени: 12с", "Открыт магазин контрольных улучшений!"],
        "color": ui.GREEN, "born": st4.now, "until": st4.now + 100})

    print(f"  скриншоты: {OUT}")
    return 0 if fonts_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
