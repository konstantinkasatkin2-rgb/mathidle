"""Интерфейс на pygame.

Всё рисуется на фиксированный холст 1280x760 и масштабируется под окно,
поэтому игра одинаково выглядит на любом разрешении.
"""

import math
import os
import random
import sys
import time

import pygame

from . import assets, config, economy, state as state_mod

W, H = config.GAME["window"]      # 1280x760: базовый холст, масштабируется под окно
FPS = 60

# --------------------------------------------------------------------------
# Палитра
# --------------------------------------------------------------------------
BG = (16, 20, 28)
BG2 = (22, 27, 38)
PANEL = (26, 33, 47)
PANEL_HI = (34, 43, 60)
LINE = (45, 56, 78)
TEXT = (232, 237, 245)
MUTED = (139, 152, 173)
ACCENT = (79, 209, 197)
ACCENT_DARK = (26, 74, 71)
GOLD = (246, 196, 83)
GREEN = (72, 187, 120)
RED = (245, 101, 101)
BLUE = (108, 165, 245)
VIOLET = (167, 139, 250)

KIND_COLORS = {
    "buy": ACCENT,
    "unlock": GOLD,
    "pass": GREEN,
    "fail": RED,
    "test": BLUE,
    "info": MUTED,
}

TABS = [
    ("upgrades", "Улучшения"),
    ("test", "Проверки"),
    ("prestige", "Престиж"),
    ("shop", "Магазин"),
    ("settings", "Настройки"),
]

KEYPAD = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"], ["-", "0", "del"]]


class Button:
    """Прямоугольная кнопка с заголовком и подписью."""

    def __init__(self, rect, title, subtitle="", accent=ACCENT, enabled=True, badge=""):
        self.rect = pygame.Rect(rect)
        self.title = title
        self.subtitle = subtitle
        self.accent = accent
        self.enabled = enabled
        self.badge = badge
        self.hover = False

    def draw(self, canvas, fonts):
        r = self.rect
        pygame.draw.rect(canvas, PANEL_HI if self.hover else PANEL, r, border_radius=10)
        border = self.accent if self.enabled else LINE
        if not self.enabled:
            border = LINE
        pygame.draw.rect(canvas, border, r, width=2, border_radius=10)
        if self.enabled:
            bar = pygame.Rect(r.x, r.y, 4, r.h)
            pygame.draw.rect(canvas, self.accent, bar, border_radius=2)

        color = TEXT if self.enabled else MUTED
        title_font = fonts.get(19, bold=True)
        tx = r.x + 14
        if self.subtitle:
            ty = r.y + (r.h - 46) // 2
        else:
            ty = r.y + r.h // 2 - 12
        canvas.blit(title_font.render(self.title, True, color), (tx, ty))
        if self.subtitle:
            sub_font = fonts.get(14)
            sub_color = self.accent if self.enabled else (90, 100, 118)
            canvas.blit(sub_font.render(self.subtitle, True, sub_color), (tx, ty + 26))
        if self.badge:
            badge_font = fonts.get(14, bold=True)
            surf = badge_font.render(self.badge, True, BG)
            w = surf.get_width() + 16
            badge_rect = pygame.Rect(r.right - w - 10, r.y + 8, w, 24)
            pygame.draw.rect(canvas, self.accent, badge_rect, border_radius=12)
            canvas.blit(surf, (badge_rect.x + 8, badge_rect.y + 4))


class FloatingText:
    def __init__(self, x, y, text, color, ttl=1.1, born=0.0):
        self.x, self.y, self.text, self.color = x, y, text, color
        self.born, self.ttl = born, ttl

    def alive(self, now):
        return now - self.born < self.ttl


class GameUI:
    def __init__(self, st=None):
        self.state = st or state_mod.GameState()
        self.running = True
        self.fonts = assets.FontBook()
        self.input = ""
        self.tab = "upgrades"
        self.scroll = {tid: 0 for tid, _ in TABS}
        self.floats = []
        self.modal = None
        self.shake = 0.0
        self.flash = 0.0
        self.flash_color = GREEN
        self.rng = random.Random()
        self.bg = self._make_background()
        self._pending = []          # события, ждущие отрисовки
        self._passive_milestone = 0  # сколько порогов пассивного дохода пройдено
        # аккаунт
        self._login_name = ""
        self._login_pass = ""
        self._account_error = ""
        self._egg_shown = False
        self._egg_dismissed = False
        self._egg_shown_at = 0.0
        # показывать ли поля ввода логина (в настройках отдалены предпочтениями)
        self.focus_login_field = "name"

    # ------------------------------------------------------------------
    # Фон
    # ------------------------------------------------------------------
    def _make_background(self):
        surf = pygame.Surface((W, H))
        for y in range(H):
            k = y / H
            surf.fill(
                (
                    int(BG[0] + (BG2[0] - BG[0]) * k),
                    int(BG[1] + (BG2[1] - BG[1]) * k),
                    int(BG[2] + (BG2[2] - BG[2]) * k),
                ),
                (0, y, W, 1),
            )
        return surf

    # ------------------------------------------------------------------
    # Главный цикл
    # ------------------------------------------------------------------
    def run(self, max_seconds=None):
        """Игровой цикл. `max_seconds` ограничивает время (используется в тестах)."""
        pygame.init()
        pygame.display.set_caption(f"{config.GAME['title']} {config.GAME['version']}")
        window = pygame.display.set_mode((W, H), pygame.RESIZABLE)
        canvas = pygame.Surface((W, H))
        clock = pygame.time.Clock()
        self.state.next_problem()
        started = time.monotonic()

        while self.running:
            if max_seconds and time.monotonic() - started >= max_seconds:
                self.running = False
            dt = min(0.1, clock.tick(FPS) / 1000.0)
            self.handle_events()
            self.state.tick(dt)
            self.update(dt)
            self.draw(canvas, window)
            pygame.display.flip()

        self.state.save()
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                w = max(640, event.w)
                h = max(400, event.h)
                pygame.display.set_mode((w, h), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                self.on_key(event)
            elif event.type == pygame.MOUSEWHEEL:
                self.scroll[self.tab] = max(0, self.scroll[self.tab] - event.y * 40)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.on_click(event.pos)

    # ------------------------------------------------------------------
    # Ввод с клавиатуры
    # ------------------------------------------------------------------
    def on_key(self, event):
        st = self.state
        # затемнение после «Femboy Futa house» перехватывает ввод
        if st.easter_egg and not self._egg_dismissed:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE,
                             pygame.K_SPACE):
                self._egg_dismissed = True
            return
        if self.modal and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE,
                                         pygame.K_SPACE):
            self.modal = None
            return
        if event.key == pygame.K_ESCAPE:
            if st.test:
                st.abort_test()
                self.modal = self._result_modal({"passed": False, "reason": "abort"})
            else:
                st.save()
                self.running = False
            return
        if event.key == pygame.K_TAB:
            order = [t[0] for t in TABS]
            self.tab = order[(order.index(self.tab) + 1) % len(order)]
            return
        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3) and event.mod & pygame.KMOD_CTRL:
            self.tab = TABS[event.key - pygame.K_1][0]
            return
        if event.key == pygame.K_BACKSPACE:
            self.input = self.input[:-1]
            return
        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            self.press_enter()
            return
        if event.key in (pygame.K_DELETE,):
            self.input = ""
            return
        ch = event.unicode
        if ch and (ch.isdigit() or ch in "-.,"):
            if len(self.input) < 8:
                self.input += ch

    def press_enter(self):
        if not self.input:
            return
        result = self.state.submit(self.input)
        self.input = ""
        self.on_result(result)

    def on_result(self, result):
        now = self.state.now
        if result.get("ok"):
            amount = result["amount"]
            self.floats.append(
                FloatingText(W * 0.22, 250, f"+{economy.fmt_money(amount)}", GOLD, born=now)
            )
            self.flash, self.flash_color = 0.25, GREEN
            speed = result["speed"]
            if speed >= 0.999:
                self.floats.append(
                    FloatingText(W * 0.22, 285, "мгновенно!", ACCENT, ttl=0.9, born=now)
                )
            if result["combo"] >= 3:
                self.floats.append(
                    FloatingText(W * 0.22, 320, f"серия ×{result['combo']}", BLUE, ttl=0.9, born=now)
                )
        else:
            self.flash, self.flash_color = 0.35, RED
            self.shake = 0.35
            if result.get("reason") == "wrong":
                self.floats.append(
                    FloatingText(
                        W * 0.22, 250, f"ответ: {result['expected']}", RED, ttl=1.4, born=now
                    )
                )
        test = result.get("test")
        if test:
            self.modal = self._result_modal(test)

    def _result_modal(self, test):
        now = self.state.now
        if test.get("passed"):
            lines = [
                f"Контрольная №{test['level']} сдана",
                f"Награда: +{economy.fmt_money(test['bonus'])}",
                f"Осталось времени: {economy.fmt_time(test['spare'])}",
            ]
            if test.get("shop_unlocked"):
                lines.append("Открыт магазин контрольных улуйшений!")
            return {"title": "Сдано!", "lines": lines, "color": GREEN,
                    "born": now, "until": now + 6.0}
        reason = test.get("reason", "wrong")
        text = {
            "time": "Время вышло",
            "abort": "Контрольная прервана",
            "wrong": "Ошибка в примере",
        }.get(reason, "Провал")
        return {
            "title": text,
            "lines": [f"Контрольная №{test.get('level')} не засчитана", "Билет возвращён"],
            "color": RED,
            "born": now,
            "until": now + 4.5,
        }

    # ------------------------------------------------------------------
    # Мышь
    # ------------------------------------------------------------------
    def scale_pos(self, pos, window_size):
        win_w, win_h = window_size
        scale = min(win_w / W, win_h / H)
        off_x = (win_w - W * scale) / 2
        off_y = (win_h - H * scale) / 2
        return (pos[0] - off_x) / scale, (pos[1] - off_y) / scale

    def on_click(self, pos):
        pos = self.scale_pos(pos, pygame.display.get_surface().get_size())
        if self.state.easter_egg and not self._egg_dismissed:
            self._egg_dismissed = True
            return
        for button in self._pending:
            if button.enabled and button.rect.collidepoint(pos):
                self.activate(button)
                return
        self.input = ""

    def activate(self, button):
        action = getattr(button, "action", None)
        if action:
            action()

    def update(self, dt):
        now = self.state.now
        self.floats = [f for f in self.floats if f.alive(now)]
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt)
        if self.modal and now > self.modal.get("until", 0):
            self.modal = None
        self._pending = []
        self.check_passive_milestone()

    def check_passive_milestone(self):
        """Как только пассивный доход стал заметным — сообщаем об этом."""
        st = self.state
        if st.session_passive <= 0:
            return
        thresholds = (0.01, 0.1, 1, 10, 100, 1000)
        passed = sum(1 for t in thresholds if st.session_passive >= t)
        if passed > self._passive_milestone:
            self._passive_milestone = passed
            target = thresholds[passed - 1]
            self.floats.append(
                FloatingText(W * 0.22, 355, f"пассив: +{economy.fmt_money(target)}",
                             ACCENT, ttl=1.4, born=st.now)
            )

    # ------------------------------------------------------------------
    # Отрисовка
    # ------------------------------------------------------------------
    def draw(self, canvas, window):
        canvas.blit(self.bg, (0, 0))
        offset = (0, 0)
        if self.shake > 0:
            amp = self.shake * 10
            offset = (self.rng.uniform(-amp, amp), self.rng.uniform(-amp, amp))

        self.draw_topbar(canvas)
        self.draw_problem_panel(canvas)
        self.draw_side_panel(canvas)
        self.draw_events(canvas)
        self.draw_floats(canvas)
        if self.modal:
            self.draw_modal(canvas)
        if self.flash > 0 and self.state.setting("animations"):
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            overlay.fill((*self.flash_color, int(70 * self.flash / 0.35)))
            canvas.blit(overlay, (0, 0))
        if self.state.easter_egg and not self._egg_dismissed:
            self.draw_easter_egg(canvas)

        win_w, win_h = window.get_size()
        scale = min(win_w / W, win_h / H)
        frame = pygame.transform.smoothscale(canvas, (int(W * scale), int(H * scale)))
        window.fill(BG)
        window.blit(frame, ((win_w - frame.get_width()) // 2 + int(offset[0]),
                            (win_h - frame.get_height()) // 2 + int(offset[1])))

    def draw_easter_egg(self, canvas):
        """После покупки «Femboy Futa house» экран темнеет.

        Закрывается по Enter, Esc или клику — иначе играть было бы нельзя.
        """
        st = self.state
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((4, 6, 12, 232))
        canvas.blit(veil, (0, 0))

        t = max(0.0, st.now - self._egg_shown_at) if self._egg_shown_at else 0.0
        pulse = 0.75 + 0.25 * math.sin(st.now * 1.6)

        card_w, card_h = 720, 260
        card = pygame.Rect((W - card_w) // 2, (H - card_h) // 2, card_w, card_h)
        pygame.draw.rect(canvas, (12, 14, 22), card, border_radius=20)
        pygame.draw.rect(canvas, (*GOLD, int(140 * pulse)), card, width=3, border_radius=20)

        title_font = self.fonts.get(34, bold=True)
        body_font = self.fonts.get(17)
        small_font = self.fonts.get(13)

        def center(text, font, color, yy):
            surf = font.render(text, True, color)
            canvas.blit(surf, (card.centerx - surf.get_width() // 2, yy))

        center("Femboy Futa house", title_font, GOLD, card.y + 34)
        center("Куплено. Эффектов нет. Как и обещано.", body_font, TEXT, card.y + 96)
        center("Ждите версии 1.3...", self.fonts.get(24, bold=True),
               (*GOLD, int(255 * pulse)), card.y + 140)
        center("Enter, Esc или клик — вернуться к игре", small_font, MUTED, card.bottom - 40)

    # ---------------- верхняя панель ----------------
    def draw_topbar(self, canvas):
        pygame.draw.rect(canvas, (18, 23, 33), (0, 0, W, 70))
        pygame.draw.line(canvas, LINE, (0, 70), (W, 70))

        title = self.fonts.get(26, bold=True)
        canvas.blit(title.render(config.GAME["title"], True, TEXT), (24, 12))
        small = self.fonts.get(13)
        canvas.blit(small.render(f"v{config.GAME['version']}", True, MUTED), (24, 42))

        money = self.state.money
        money_font = self.fonts.get(34, bold=True)
        label = self.fonts.get(13)
        x = 220
        canvas.blit(label.render("ДЕНЬГИ", True, MUTED), (x, 10))
        canvas.blit(money_font.render(economy.fmt_money(money), True, GOLD), (x, 24))

        rate = self.state.passive_rate()
        x = 560
        canvas.blit(label.render("ПАССИВНО КАПАЕТ", True, MUTED), (x, 10))
        per_sec = rate * self.state.passive_reward_per_example()
        canvas.blit(
            money_font.render(f"+{economy.fmt_money(per_sec)} в секунду", True, ACCENT), (x, 24)
        )
        session = self.state.session_passive
        canvas.blit(
            small.render(
                f"за сессию +{economy.fmt_money(session)} · "
                f"{economy.fmt_rate(rate)} примера/с",
                True, ACCENT if session > 0 else MUTED,
            ),
            (x, 52),
        )

        x = 900
        canvas.blit(label.render("МНОЖИТЕЛЬ", True, MUTED), (x, 10))
        canvas.blit(money_font.render(f"×{self.state.money_mult():.1f}", True, VIOLET), (x, 24))
        if self.state.combo > 1:
            canvas.blit(
                small.render(f"серия {self.state.combo}", True, BLUE), (x, 52)
            )

        ops = ", ".join(config.operation(o)["name"] for o in self.state.operation_ids())
        ops_line = f"Открыто: {ops}"
        canvas.blit(
            small.render(ops_line, True, MUTED),
            (W - 24 - small.size(ops_line)[0], 52),
        )

    # ---------------- панель примера ----------------
    def draw_problem_panel(self, canvas):
        st = self.state
        panel = pygame.Rect(20, 88, 620, H - 108)
        pygame.draw.rect(canvas, PANEL, panel, border_radius=14)

        testing = st.test is not None
        head = self.fonts.get(15, bold=True)
        if testing:
            tt = economy.test_type(st.test["type"])
            title = (f"{tt['name']} №{st.test['level']}  ·  пример "
                     f"{st.test['index'] + 1} из {len(st.test['problems'])}")
            color = BLUE
        else:
            title = "Реши пример"
            color = MUTED
        canvas.blit(head.render(title, True, color), (panel.x + 24, panel.y + 16))

        if testing:
            self.draw_timer(canvas, panel)
        elif st.wants_hint():
            hint = self.fonts.get(15, bold=True)
            msg = "Шпаргалка"
            canvas.blit(hint.render(msg, True, GOLD),
                        (panel.right - 24 - hint.size(msg)[0], panel.y + 16))

        # --- пример ---
        if st.current:
            age = max(0.0, st.now - st.shown_at)
            pop = min(1.0, age / 0.18)
            size = int(52 * (0.92 + 0.08 * pop))
            font = self.fonts.get(size, bold=True)
            text = st.current["text"] + " ="
            surf = font.render(text, True, TEXT)
            rect = surf.get_rect(center=(panel.centerx, panel.y + 105))
            canvas.blit(surf, rect)

            y = panel.y + 140
            # окно скорости: движущаяся шкала ответа
            if st.setting("speed_gauge"):
                y = self.draw_speed_gauge(canvas, panel, y)
            # сложность примера
            if st.setting("difficulty_bar"):
                y = self.draw_difficulty(canvas, panel, y)

        # поле ответа
        box = pygame.Rect(panel.x + 24, panel.y + 225, panel.w - 48, 62)
        pygame.draw.rect(canvas, BG, box, border_radius=10)
        pygame.draw.rect(canvas, ACCENT if self.input else LINE, box, width=2, border_radius=10)
        shown = self.input if self.input else "…"
        ans_font = self.fonts.get(38, bold=True)
        canvas.blit(ans_font.render(shown, True, TEXT if self.input else MUTED),
                    (box.x + 18, box.y + 12))
        caret = box.x + 18 + ans_font.size(shown)[0] + 6
        if int(st.now * 2) % 2 == 0:
            pygame.draw.rect(canvas, ACCENT, (caret, box.y + 16, 3, 30))

        # цифровая клавиатура
        self.draw_keypad(canvas, pygame.Rect(panel.x + 24, panel.y + 300, panel.w - 48, 225))

        hint = self.fonts.get(13)
        canvas.blit(
            hint.render("Enter — ответ   ·   Backspace — стереть   ·   Tab — вкладка   ·   Esc — выход",
                        True, (86, 96, 114)),
            (panel.x + 24, panel.bottom - 26),
        )

    def draw_speed_gauge(self, canvas, panel, y):
        """Окно скорости: зелёная зона «быстро», маркер едет вправо по мере времени.

        Само окно двигается вместе с улучшениями «Скоростной бланк» и
        «Вечный разгон» — видно, как оно растёт.
        """
        st = self.state
        fast, slow = st.speed_window()
        elapsed = max(0.0, st.now - st.shown_at)
        span = max(slow * 1.25, 1.0)

        track = pygame.Rect(panel.centerx - 170, y, 340, 12)
        pygame.draw.rect(canvas, LINE, track, border_radius=6)

        # зелёная зона быстрого окна
        fast_w = int(track.w * min(1.0, fast / span))
        if fast_w > 0:
            pygame.draw.rect(
                canvas, GREEN,
                pygame.Rect(track.x, track.y, fast_w, track.h), border_radius=6,
            )

        # маркер текущего времени
        pos = int(track.w * min(1.0, elapsed / span))
        speed = st.speed_now()
        marker_x = min(track.right - 3, track.x + pos)
        marker = pygame.Rect(marker_x, track.y - 5, 6, track.h + 10)
        pygame.draw.rect(canvas, TEXT, marker, border_radius=3)

        small = self.fonts.get(12)
        left = "быстро" + self._filler()
        canvas.blit(small.render(left, True, GREEN), (track.x, track.y - 17))
        right = f"медленно {elapsed:.1f}с"
        canvas.blit(small.render(right, True, MUTED),
                    (track.right - small.size(right)[0], track.y - 17))
        mult = f"скорость ×{speed:.2f}"
        width = small.size(mult)[0]
        canvas.blit(small.render(mult, True, ACCENT if speed > 0.99 else GOLD),
                    (panel.centerx - width // 2, track.bottom + 4))
        return track.bottom + 28

    def _filler(self):
        """Пробелы-заполнитель не нужны; оставлено как точка расширения."""
        return ""

    def draw_difficulty(self, canvas, panel, y):
        st = self.state
        diff = st.current["difficulty"]
        bar_w = 320
        bar = pygame.Rect(panel.centerx - bar_w // 2, y, bar_w, 8)
        pygame.draw.rect(canvas, LINE, bar, border_radius=4)
        filled = max(1, int(bar_w * diff)) if diff > 0 else 0
        if filled:
            pygame.draw.rect(canvas, self._diff_color(diff),
                             pygame.Rect(bar.x, bar.y, filled, bar.h), border_radius=4)
        small = self.fonts.get(13)
        label = f"сложность {int(diff * 100)}%"
        canvas.blit(small.render(label, True, MUTED),
                    (panel.centerx - small.size(label)[0] // 2, bar.bottom + 6))
        return bar.bottom + 26

    def draw_timer(self, canvas, panel):
        st = self.state
        test = st.test
        left = max(0.0, test["limit"] - test["elapsed"])
        bar = pygame.Rect(panel.x + 24, panel.y + 44, panel.w - 48, 10)
        pygame.draw.rect(canvas, LINE, bar, border_radius=5)
        k = min(1.0, left / max(1e-6, test["limit"]))
        color = RED if k < 0.25 else (GOLD if k < 0.5 else GREEN)
        filled = max(1, int(bar.w * k)) if k > 0 else 0
        if filled:
            pygame.draw.rect(
                canvas, color, pygame.Rect(bar.x, bar.y, filled, bar.h), border_radius=5
            )
        font = self.fonts.get(15, bold=True)
        canvas.blit(font.render(f"осталось {economy.fmt_time(left)}", True, color),
                    (bar.x, bar.bottom + 8))
        # прогресс по примерам
        dots_font = self.fonts.get(13)
        done = test["index"]
        label = f"{done}/{len(test['problems'])}"
        canvas.blit(dots_font.render(label, True, MUTED),
                    (bar.right - dots_font.size(label)[0], bar.bottom + 8))

    def draw_keypad(self, canvas, rect):
        cols, rows = 3, 4
        gap = 8
        bw = (rect.w - gap * (cols - 1)) // cols
        bh = (rect.h - gap * (rows - 1)) // rows
        for r in range(rows):
            for c in range(cols):
                key = KEYPAD[r][c]
                cell = pygame.Rect(
                    rect.x + c * (bw + gap), rect.y + r * (bh + gap), bw, bh
                )
                font = self.fonts.get(24, bold=True)
                label = {"del": "DEL"}.get(key, key)
                pygame.draw.rect(canvas, PANEL_HI, cell, border_radius=10)
                surf = font.render(label, True, TEXT if key != "-" else ACCENT)
                canvas.blit(surf, surf.get_rect(center=cell.center))
                btn = Button(cell, key)
                btn.enabled = True
                btn.action = (lambda k=key: self.press_key(k))
                self._pending.append(btn)

    def press_key(self, key):
        if key == "del":
            self.input = self.input[:-1]
        elif len(self.input) < 8:
            self.input += key

    def _diff_color(self, diff):
        if diff < 0.35:
            return GREEN
        if diff < 0.6:
            return GOLD
        return RED

    # ---------------- боковая панель ----------------
    def draw_side_panel(self, canvas):
        panel = pygame.Rect(660, 88, W - 680, H - 108)
        pygame.draw.rect(canvas, PANEL, panel, border_radius=14)
        st = self.state

        # вкладки
        count = len(TABS)
        gap = 6
        tw = int((panel.w - 32 - gap * (count - 1)) / count)
        for i, (tid, title) in enumerate(TABS):
            rect = pygame.Rect(panel.x + 16 + i * (tw + gap), panel.y + 14, tw, 40)
            active = self.tab == tid
            locked = self._tab_locked(tid)
            pygame.draw.rect(canvas, PANEL_HI if active else BG, rect, border_radius=8)
            if active:
                pygame.draw.rect(canvas, ACCENT, rect, width=2, border_radius=8)
            font = self.fonts.get(15, bold=True)
            if locked:
                surf = font.render(title, True, (96, 106, 124))
            else:
                surf = font.render(title, True, TEXT if active else MUTED)
            canvas.blit(surf, surf.get_rect(center=rect.center))
            btn = Button(rect, title)
            btn.enabled = True
            btn.action = (lambda t=tid: self.set_tab(t))
            self._pending.append(btn)

        body = pygame.Rect(panel.x + 16, panel.y + 64, panel.w - 32, panel.h - 80)
        if self.tab == "upgrades":
            self.draw_tab_upgrades(canvas, body)
        elif self.tab == "test":
            self.draw_tab_test(canvas, body)
        elif self.tab == "prestige":
            self.draw_tab_prestige(canvas, body)
        elif self.tab == "settings":
            self.draw_tab_settings(canvas, body)
        else:
            self.draw_tab_shop(canvas, body)

    def _tab_locked(self, tid):
        st = self.state
        if tid == "shop" and not st.shop_unlocked:
            return True
        if tid == "prestige" and st.prestige_count == 0 and not st.prestige_unlocked():
            return True
        return False

    def set_tab(self, tab):
        if self._tab_locked(tab):
            return
        self.tab = tab

    def _scroll_area(self, canvas, rect, content_h):
        """Рисует список с вертикальной прокруткой, возвращает сдвиг."""
        offset = self.scroll[self.tab]
        max_off = max(0, content_h - rect.h)
        offset = min(offset, max_off)
        self.scroll[self.tab] = offset
        prev = canvas.get_clip()
        canvas.set_clip(rect)
        canvas_y = offset
        return canvas_y

    def draw_tab_upgrades(self, canvas, rect):
        st = self.state
        cards = len(config.BASE_UPGRADES) * 122
        self._scroll_area(canvas, rect, 10 + cards + 80)
        y = rect.y - self.scroll[self.tab]

        info = self.fonts.get(13)
        rate = st.passive_rate()
        per_sec = rate * st.passive_reward_per_example()
        line = (f"Сейчас: {economy.fmt_rate(rate)} примера/с   ·   "
                f"{economy.fmt_money(per_sec)}/с   ·   "
                f"всего {economy.fmt_rate(sum(u['max_rate'] for u in config.BASE_UPGRADES))} максимум")
        canvas.blit(info.render(line, True, MUTED), (rect.x, y))
        y += 22
        if rate > 0:
            canvas.blit(
                info.render(
                    f"Заработано пассивно за сессию: +{economy.fmt_money(st.session_passive)}",
                    True, ACCENT,
                ),
                (rect.x, y),
            )
        else:
            canvas.blit(
                info.render("Купи узелки — и деньги пойдут сами", True, MUTED),
                (rect.x, y),
            )
        y += 28

        for up in config.BASE_UPGRADES:
            level = st.upgrade_level(up["id"])
            maxl = st.upgrade_max_level(up["id"])
            full = st.upgrade_full(up["id"])
            cost = st.upgrade_cost(up["id"])
            asc = st.ascensions.get(up["id"], 0)

            card = pygame.Rect(rect.x, y, rect.w, 78)
            enabled = (not full) and st.money >= cost
            title = up["name"]
            rate_txt = up["rate_per_level"] * (2 ** asc)
            if full:
                subtitle = f"максимум, вознесений: {asc}" if asc else "максимум улучшения"
            else:
                subtitle = (f"+{rate_txt:g} примера/с   ·   ур. {level}/{maxl}   ·   "
                            f"цена: {economy.fmt_money(cost)}")
            badge = "" if full else economy.fmt_money(cost)
            if asc:
                badge = (badge + "  ×" + str(2 ** asc)).strip()
            btn = Button(card, title, subtitle, ACCENT if enabled else GOLD, enabled, badge)
            btn.action = (lambda u=up["id"]: self.do_buy_upgrade(u))
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)

            # полоса прогресса: с учётом вознесений максимум выше базового
            bar = pygame.Rect(card.x + 14, card.bottom - 10, card.w - 28, 5)
            max_rate = up["max_rate"] * (2 ** asc)
            pygame.draw.rect(canvas, LINE, bar, border_radius=2)
            filled = int(bar.w * min(1.0, st.upgrade_rate(up["id"]) / max_rate))
            pygame.draw.rect(canvas, ACCENT, (bar.x, bar.y, filled, bar.h), border_radius=2)
            y += 84

            # кнопка вознесения
            if asc or st.prestige_count >= config.ASCENSION["unlock_after_prestige"]:
                asc_btn = pygame.Rect(card.x, y, card.w, 34)
                can = st.can_ascend(up["id"])
                if not st.upgrade_full(up["id"]):
                    label = f"Вознести (нужен максимум, осталось {maxl - level})"
                else:
                    label = (f"Вознести: уровень → 0, скорость ×{2 ** (asc + 1)}, "
                             f"цена ×{4 ** (asc + 1)}")
                btn = Button(asc_btn, label, "", VIOLET, can)
                btn.action = (lambda u=up["id"]: self.do_ascend(u))
                btn.draw(canvas, self.fonts)
                self._pending.append(btn)
                y += 40
            y += 6

        # кнопка «купить максимум»
        card = pygame.Rect(rect.x, y + 6, rect.w, 56)
        btn = Button(card, "Купить максимум", "всё, что позволяет баланс", BLUE, True)
        btn.action = self.do_buy_all
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        canvas.set_clip(None)

    def do_buy_upgrade(self, up_id):
        ok, message = self.state.buy_upgrade(up_id)
        if ok:
            self.flash, self.flash_color = 0.2, GREEN
        else:
            self.state.log(message, "fail", ttl=2.0)

    def do_ascend(self, up_id):
        ok, message = self.state.ascend(up_id)
        if ok:
            self.flash, self.flash_color = 0.3, VIOLET
            self.state.next_problem()
        else:
            self.state.log(message, "fail", ttl=2.5)

    def do_buy_all(self):
        bought, spent = self.state.buy_all_upgrades()
        if not bought:
            self.state.log("Не хватает денег на улучшения", "fail", ttl=2.0)
        else:
            self.flash, self.flash_color = 0.25, GREEN

    def draw_tab_test(self, canvas, rect):
        st = self.state
        available = st.test_types_available()
        self._scroll_area(canvas, rect, 150 + len(available) * 242 + 190)
        y = rect.y - self.scroll[self.tab]
        big = self.fonts.get(21, bold=True)
        body = self.fonts.get(15)
        small = self.fonts.get(13)

        if st.test:
            y = self.draw_test_running(canvas, rect, y, big, body)
        else:
            for tt in available:
                y = self.draw_test_offer(canvas, rect, y, tt, big, body, small)
            y += 6

        note = [
            "Правила проверок:",
            "• ни одной ошибки, иначе провал (билет возвращается)",
            "• не уложишься во время — тоже провал",
            "• сдаёшь — награда и следующий уровень",
            "",
            "В обычной контрольной встречаются две СЛУЧАЙНЫЕ открытые операции.",
            "Итоговая и экзамен — все операции разом.",
        ]
        for i, line in enumerate(note):
            canvas.blit(body.render(line, True, TEXT if i == 0 else MUTED),
                        (rect.x + 4, y + i * 21))
        canvas.set_clip(None)

    def draw_test_running(self, canvas, rect, y, big, body):
        """Карточка идущей проверки."""
        st = self.state
        test = st.test
        tt = economy.test_type(test["type"])
        card = pygame.Rect(rect.x, y, rect.w, 190)
        pygame.draw.rect(canvas, BG, card, border_radius=12)
        pygame.draw.rect(canvas, BLUE, card, width=2, border_radius=12)
        y = card.y + 16
        canvas.blit(big.render(f"{tt['name']} №{test['level']} идёт", True, BLUE), (card.x + 16, y))
        y += 38
        ops = ", ".join(config.operation(o)["name"] for o in test["ops"])
        for line in [
            f"Пример {test['index'] + 1} из {len(test['problems'])}",
            f"Темы: {ops}",
            f"Осталось: {economy.fmt_time(test['limit'] - test['elapsed'])}",
            f"Награда: {economy.fmt_money(economy.test_reward(test['level'], test['type']))}",
        ]:
            canvas.blit(body.render(line, True, TEXT), (card.x + 16, y))
            y += 25
        y += 8
        btn = Button(pygame.Rect(card.x + 16, y, 220, 46), "Прервать", "вернуть билет", RED, True)
        btn.action = self.do_abort_test
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        return card.bottom + 16

    def draw_test_offer(self, canvas, rect, y, tt, big, body, small):
        """Карточка одного вида проверки с ценой и кнопкой."""
        st = self.state
        kind = tt["id"]
        level = st.test_level
        price = economy.test_price(kind)
        can = st.can_start_test(kind)
        colors = {"test": BLUE, "final": GOLD, "exam": VIOLET}
        accent = colors.get(kind, BLUE)

        card = pygame.Rect(rect.x, y, rect.w, 228)
        pygame.draw.rect(canvas, BG, card, border_radius=12)
        pygame.draw.rect(canvas, accent if can else LINE, card, width=2, border_radius=12)

        y2 = card.y + 14
        canvas.blit(big.render(tt["name"], True, accent if can else MUTED), (card.x + 16, y2))
        y2 += 30
        canvas.blit(small.render(tt["desc"], True, MUTED), (card.x + 16, y2))
        y2 += 26

        count = economy.test_problem_count(level, kind)
        diff = int(economy.test_difficulty(level, kind, st.prestige_levels) * 100)
        for line in [
            f"Билет: {economy.fmt_money(price)}",
            f"Примеров: {count}   ·   Сложность: {diff}%",
            f"Время: {economy.fmt_time(economy.test_time_limit(level, st.grade_levels, kind, st.prestige_levels))}",
            f"Награда: {economy.fmt_money(economy.test_reward(level, kind))}",
        ]:
            canvas.blit(body.render(line, True, TEXT), (card.x + 16, y2))
            y2 += 24

        label = f"Начать · {economy.fmt_money(price)}" if can else f"Нужно {economy.fmt_money(price)}"
        btn = Button(pygame.Rect(card.x + 16, y2 + 4, 230, 42), label, "", accent, can)
        btn.action = (lambda k=kind: self.do_start_test(k))
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        return card.bottom + 14

    def do_start_test(self, kind="test"):
        ok, message = self.state.start_test(kind)
        if ok:
            self.input = ""
            self.tab = "upgrades"
        else:
            self.state.log(message, "fail", ttl=2.5)

    def do_abort_test(self):
        result = self.state.abort_test()
        if result:
            self.modal = self._result_modal(result)

    # ---------------- Престиж ----------------
    def draw_tab_prestige(self, canvas, rect):
        st = self.state
        self._scroll_area(canvas, rect, 300 + len(config.PRESTIGE_ITEMS) * 92 + 60)
        y = rect.y - self.scroll[self.tab]
        big = self.fonts.get(21, bold=True)
        body = self.fonts.get(15)
        small = self.fonts.get(13)

        card = pygame.Rect(rect.x, y, rect.w, 250)
        unlocked = st.prestige_unlocked()
        accent = GOLD if unlocked else MUTED
        pygame.draw.rect(canvas, BG, card, border_radius=12)
        pygame.draw.rect(canvas, accent if unlocked else LINE, card, width=2, border_radius=12)

        y = card.y + 14
        canvas.blit(big.render(f"Престиж #{st.prestige_count + 1}", True, accent),
                    (card.x + 16, y))
        y += 32
        canvas.blit(
            body.render(
                f"Очков престижа: {economy.fmt_money(st.prestige_points)}"
                f"   ·   набежит: +{economy.fmt_money(st.pending_prestige_points())}",
                True, GOLD if st.prestige_points > 0 else TEXT,
            ),
            (card.x + 16, y),
        )
        y += 26
        canvas.blit(
            small.render(
                f"Курс: 1 деньга = {config.PRESTIGE['points_per_money']} очка престижа",
                True, MUTED),
            (card.x + 16, y),
        )
        y += 30

        for label, ok in self._prestige_requirements(st):
            canvas.blit(small.render(("[x] " if ok else "[ ] ") + label,
                                     True, GREEN if ok else MUTED), (card.x + 16, y))
            y += 21

        y += 8
        for line in [
            "Престиж обнуляет: деньги, обычные улучшения,",
            "контрольные улучшения и вознесения.",
            "Открытые операции (вычитание, деление и т.д.) остаются.",
        ]:
            canvas.blit(small.render(line, True, MUTED), (card.x + 16, y))
            y += 19

        y = card.bottom + 12
        label = "СДЕЛАТЬ ПРЕСТИЖ" if unlocked else st.prestige_blocked_reason()
        btn = Button(pygame.Rect(rect.x, y, rect.w, 48), label, "", GOLD, unlocked)
        btn.action = self.do_prestige
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        y += 62

        if not st.prestige_shop_unlocked:
            canvas.blit(
                small.render("Магазин престижных улучшений откроется после первого престижа.",
                             True, MUTED),
                (rect.x + 4, y),
            )
            canvas.set_clip(None)
            return

        canvas.blit(body.render("Престижные улучшения", True, VIOLET), (rect.x + 4, y))
        y += 26
        for item in config.PRESTIGE_ITEMS:
            y = self.draw_prestige_item(canvas, rect, y, item, small)

        canvas.blit(
            small.render("«Femboy Futa house» — самая дорогая прокачка, без эффектов.",
                         True, GOLD),
            (rect.x + 4, y + 6),
        )
        canvas.set_clip(None)

    def _prestige_requirements(self, st):
        """Требования престижа с отметками выполнения."""
        need = config.PRESTIGE["required_difficulty"]
        return [
            (f"Решить пример сложности {int(need * 100)}% "
             f"(сейчас {int(st.max_difficulty_solved * 100)}%)",
             st.max_difficulty_solved >= need),
            (f"Заработать деньги в этом забеге ({economy.fmt_money(st.run_earned)})",
             st.run_earned > 0),
        ]

    def draw_prestige_item(self, canvas, rect, y, item, small):
        st = self.state
        level = st.prestige_level(item["id"])
        full = st.prestige_full(item["id"])
        cost = st.prestige_cost(item["id"])
        affordable = (not full) and st.prestige_points >= cost

        if item.get("easter_egg"):
            card = pygame.Rect(rect.x, y, rect.w, 104)
            btn = Button(card, item["name"], item["desc"], GOLD, affordable,
                         "ЕСТЬ" if full else economy.fmt_money(cost))
            btn.action = (lambda i=item["id"]: self.do_buy_prestige(i))
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)
            sale = "сейчас действует скидка 15%"
            canvas.blit(small.render(sale, True, GREEN if full else RED),
                        (card.x + 14, card.bottom - 26))
            base_txt = f"полная цена {economy.fmt_money(item['price'])}"
            canvas.blit(small.render(base_txt, True, MUTED),
                        (card.right - 14 - small.size(base_txt)[0], card.bottom - 26))
            return card.bottom + 8

        if full:
            subtitle = f"максимум (ур. {item['max_level']}) · {item['desc']}"
        else:
            subtitle = f"ур. {level}/{item['max_level']} · {item['desc']}"
        card = pygame.Rect(rect.x, y, rect.w, 78)
        btn = Button(card, item["name"], subtitle, VIOLET, affordable,
                     "МАКС" if full else economy.fmt_money(cost))
        btn.action = (lambda i=item["id"]: self.do_buy_prestige(i))
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        return card.bottom + 8

    def do_prestige(self):
        ok, message = self.state.do_prestige()
        if ok:
            self.flash, self.flash_color = 0.35, GOLD
            self.input = ""
            self.state.next_problem()
        else:
            self.state.log(message, "fail", ttl=3.0)

    def do_buy_prestige(self, item_id):
        ok, message = self.state.buy_prestige(item_id)
        if ok:
            self.flash, self.flash_color = 0.3, GOLD
            if self.state.easter_egg and not self._egg_shown:
                self._egg_shown = True
                self._egg_dismissed = False
                self._egg_shown_at = self.state.now
        else:
            self.state.log(message, "fail", ttl=2.5)

    # ---------------- Настройки ----------------
    def draw_tab_settings(self, canvas, rect):
        st = self.state
        self._scroll_area(canvas, rect, 60 + len(config.DISPLAY_SETTINGS) * 52 + 300)
        y = rect.y - self.scroll[self.tab]
        body = self.fonts.get(15)
        small = self.fonts.get(13)

        canvas.blit(body.render("Отображение", True, TEXT), (rect.x + 4, y))
        y += 28
        for item in config.DISPLAY_SETTINGS:
            card = pygame.Rect(rect.x, y, rect.w, 44)
            on = st.setting(item["id"])
            pygame.draw.rect(canvas, BG, card, border_radius=9)
            pygame.draw.rect(canvas, ACCENT if on else LINE, card, width=2, border_radius=9)
            mark = "ВКЛ" if on else "ВЫКЛ"
            mark_color = ACCENT if on else MUTED
            chip = pygame.Rect(card.right - 74, card.y + 9, 62, 26)
            pygame.draw.rect(canvas, mark_color, chip, border_radius=13)
            mark_font = self.fonts.get(13, bold=True)
            canvas.blit(mark_font.render(mark, True, BG),
                        (chip.x + (chip.w - mark_font.size(mark)[0]) // 2, chip.y + 5))
            canvas.blit(body.render(item["name"], True, TEXT), (card.x + 14, card.y + 6))
            canvas.blit(small.render(item["desc"], True, MUTED), (card.x + 14, card.y + 25))
            btn = Button(card, item["name"])
            btn.enabled = True
            btn.action = (lambda i=item["id"]: self.toggle_setting(i))
            self._pending.append(btn)
            y += 50

        y += 12
        canvas.blit(body.render("Аккаунт", True, TEXT), (rect.x + 4, y))
        y += 26
        if st.account.signed_in:
            canvas.blit(
                small.render(f"Вы вошли как {st.account_username} · прогресс синхронизируется",
                             True, GREEN), (rect.x + 4, y))
            y += 22
            canvas.blit(small.render(f"Сервер: {st.account.status()}", True, MUTED),
                        (rect.x + 4, y))
            y += 26
            btn = Button(pygame.Rect(rect.x, y, 240, 44), "Выйти",
                         "прогресс останется тут", RED, True)
            btn.action = self.do_sign_out
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)
            y += 56
            self.draw_mail(canvas, small, body, rect, y)
            canvas.set_clip(None)
            return

        canvas.blit(
            small.render("Войди, чтобы прогресс хранился на сервере, а не на устройстве",
                         True, MUTED), (rect.x + 4, y))
        y += 20
        canvas.blit(
            small.render("На одну почту — один аккаунт", True, MUTED),
            (rect.x + 4, y))
        y += 24
        if st.account.last_error:
            canvas.blit(small.render("сервер: " + st.account.last_error[:70], True, RED),
                        (rect.x + 4, y))
            y += 20
        if self._account_error:
            canvas.blit(small.render(self._account_error, True, RED), (rect.x + 4, y))
            y += 22

        # Если сервер не отвечает, предложим его запустить: без этого игрок
        # видит ошибку и не понимает, что делать дальше.
        if not st.account.signed_in and not st.account.ping():
            y += 4
            btn = Button(pygame.Rect(rect.x, y, rect.w, 42),
                         "Запустить сервер на этом компьютере",
                         "прогресс будет храниться тут", BLUE, True)
            btn.action = self.do_start_server
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)
            y += 50

        field_w = (rect.w - 10) // 2
        name_rect = pygame.Rect(rect.x, y, field_w, 40)
        pass_rect = pygame.Rect(rect.x + field_w + 10, y, field_w, 40)
        pygame.draw.rect(canvas, BG, name_rect, border_radius=8)
        pygame.draw.rect(canvas, LINE, name_rect, width=2, border_radius=8)
        pygame.draw.rect(canvas, BG, pass_rect, border_radius=8)
        pygame.draw.rect(canvas, LINE, pass_rect, width=2, border_radius=8)
        canvas.blit(body.render(self._login_name or "почта: vasya@mail.ru",
                                True, TEXT if self._login_name else MUTED),
                    (name_rect.x + 10, name_rect.y + 11))
        pass_text = "•" * len(self._login_pass) if self._login_pass else "пароль"
        canvas.blit(body.render(pass_text, True, TEXT if self._login_pass else MUTED),
                    (pass_rect.x + 10, pass_rect.y + 11))
        y += 48
        btn = Button(pygame.Rect(rect.x, y, field_w, 42), "Войти", "", ACCENT, True)
        btn.action = self.do_login
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        btn = Button(pygame.Rect(rect.x + field_w + 10, y, field_w, 42),
                     "Регистрация", "", BLUE, True)
        btn.action = self.do_register
        btn.draw(canvas, self.fonts)
        self._pending.append(btn)
        canvas.set_clip(None)

    @staticmethod
    def _left_text(seconds):
        """Сколько осталось жить письму: по-человечески, а не в секундах."""
        seconds = max(0, int(seconds))
        if seconds < 3600:
            return f"{max(1, seconds // 60)} мин"
        if seconds < 86400:
            return f"{seconds // 3600} ч"
        return f"{seconds // 86400} дн {(seconds % 86400) // 3600} ч"

    def draw_mail(self, canvas, small, body, rect, y):
        """Ящик аккаунта: письма и кнопка получения награды."""
        st = self.state
        canvas.blit(body.render("Почта", True, TEXT), (rect.x + 4, y))
        y += 26

        st.refresh_mail()
        letters = st.mail
        if not letters:
            canvas.blit(small.render("Писем нет", True, MUTED), (rect.x + 4, y))
            return

        for letter in letters:
            left = letter["expires_at"] - time.time()
            claimed = letter["claimed"]
            title = letter["subject"]
            canvas.blit(body.render(title, True, GOLD if not claimed else TEXT),
                        (rect.x + 4, y))
            y += 22
            reward = economy.fmt_money(letter["reward"])
            if claimed:
                canvas.blit(small.render(f"Награда {reward} получена", True, GREEN),
                            (rect.x + 4, y))
                y += 20
            elif left <= 0:
                canvas.blit(small.render("Письмо сгорело", True, RED),
                            (rect.x + 4, y))
                y += 20
            else:
                canvas.blit(
                    small.render(f"Награда {reward} · сгорит через {_left_text(left)}",
                                 True, MUTED), (rect.x + 4, y))
                y += 24
                btn = Button(pygame.Rect(rect.x, y, 240, 40), "Забрать награду",
                             "", GOLD, True)
                btn.action = lambda i=letter["id"]: self.do_claim_mail(i)
                btn.draw(canvas, self.fonts)
                self._pending.append(btn)
                y += 48
            y += 8
            if y > rect.bottom - 60:
                break

    def do_claim_mail(self, mail_id):
        ok, message = self.state.claim_mail(mail_id)
        self._account_error = "" if ok else message
        if ok:
            self.state.log(message, "unlock")

    def toggle_setting(self, setting_id):
        st = self.state
        st.settings[setting_id] = not st.setting(setting_id)
        st.log("Анимации " + ("включены" if st.setting("animations") else "выключены"))

    def do_login(self):
        ok, message = self.state.sign_in(self._login_name, self._login_pass)
        self._account_error = "" if ok else message
        if ok:
            st = self.state
            st.log(message, "unlock")

    def do_start_server(self):
        """Запускает сервер аккаунтов, если он есть рядом с игрой.

        Раньше игрок, скачавший игру, не мог зарегистрироваться вовсе: сервера
        в архиве не было, а ставить Python ему незачем.
        """
        import os
        import subprocess
        import sys

        here = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False)
                                               else __file__))
        candidates = [
            os.path.join(here, "MathIdleServer", "MathIdleServer.exe"),
            os.path.join(os.path.dirname(here), "MathIdleServer", "MathIdleServer.exe"),
            os.path.join(here, "..", "dist", "MathIdleServer", "MathIdleServer.exe"),
        ]
        for path in candidates:
            path = os.path.abspath(path)
            if os.path.exists(path):
                try:
                    subprocess.Popen([path], cwd=os.path.dirname(path))
                except OSError as err:
                    self._account_error = f"Не удалось запустить сервер: {err}"
                    return
                self._account_error = ""
                self.state.log(
                    "Сервер аккаунтов запущен, окно не закрывай", "unlock")
                return
        self._account_error = (
            "Рядом с игрой нет MathIdleServer.exe. Если игра запущена из "
            "исходников: bash tools/serve_accounts.sh")

    def do_register(self):
        ok, message = self.state.register(self._login_name, self._login_pass)
        self._account_error = "" if ok else message
        if ok:
            self.state.log(message, "unlock")

    def do_sign_out(self):
        self.state.sign_out()
        self._login_name = ""
        self._login_pass = ""

    def draw_tab_shop(self, canvas, rect):
        st = self.state
        if not st.shop_unlocked:
            return
        self._scroll_area(canvas, rect, 40 + len(config.GRADE_ITEMS) * 88)
        y = rect.y - self.scroll[self.tab]
        body = self.fonts.get(13)
        canvas.blit(
            body.render("Улучшения за деньги, полученные на контрольных.", True, MUTED),
            (rect.x + 4, y),
        )
        y += 26

        for item in config.GRADE_ITEMS:
            level = st.grade_level(item["id"])
            full = st.grade_full(item["id"])
            cost = st.grade_cost(item["id"])
            if item["effect"] == "unlock":
                op = config.operation(item["operation"])
                already = op["id"] in st.unlocked_ops
                title = item["name"]
                subtitle = "уже открыто" if already else item["desc"]
                accent = GOLD if not already else GREEN
                enabled = (not already) and st.money >= cost
            else:
                title = f"{item['name']}"
                effect_txt = item["desc"]
                if full:
                    subtitle = f"максимум (ур. {item['max_level']}) · {effect_txt}"
                else:
                    subtitle = f"ур. {level}/{item['max_level']} · {effect_txt}"
                accent = VIOLET
                enabled = (not full) and st.money >= cost
            card = pygame.Rect(rect.x, y, rect.w, 78)
            if item["effect"] == "unlock":
                op = config.operation(item["operation"])
                badge = "ЕСТЬ" if op["id"] in self.state.unlocked_ops else economy.fmt_money(cost)
            else:
                badge = "МАКС" if full else economy.fmt_money(cost)
            btn = Button(card, title, subtitle, accent, enabled, badge)
            btn.action = (lambda i=item["id"]: self.do_buy_grade(i))
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)
            y += 88
        canvas.set_clip(None)

    def do_buy_grade(self, item_id):
        ok, message = self.state.buy_grade(item_id)
        if ok:
            self.flash, self.flash_color = 0.25, GOLD
        else:
            self.state.log(message, "fail", ttl=2.5)

    # ---------------- события, летящий текст, модалка ----------------
    def draw_events(self, canvas):
        st = self.state
        if not st.events:
            return
        font = self.fonts.get(15)
        y = H - 150
        for event in st.events[-4:]:
            age = st.now - event["born"]
            alpha = 1.0 if age < 3.5 else max(0.0, 1.0 - (age - 3.5) / 1.0)
            if alpha <= 0:
                continue
            surf = font.render(event["text"], True, KIND_COLORS.get(event["kind"], TEXT))
            surf.set_alpha(int(255 * alpha))
            canvas.blit(surf, (26, y))
            y += 22

    def draw_floats(self, canvas):
        now = self.state.now
        font = self.fonts.get(26, bold=True)
        for item in self.floats:
            k = (now - item.born) / item.ttl
            y = item.y - int(40 * k)
            surf = font.render(item.text, True, item.color)
            surf.set_alpha(int(255 * max(0.0, 1.0 - k)))
            canvas.blit(surf, (item.x, y))

    def draw_modal(self, canvas):
        now = self.state.now
        if now > self.modal.get("until", 0):
            self.modal = None
            return
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        canvas.blit(overlay, (0, 0))

        lines = self.modal["lines"]
        w, h = 520, 120 + 34 * len(lines)
        card = pygame.Rect((W - w) // 2, (H - h) // 2, w, h)
        pygame.draw.rect(canvas, PANEL, card, border_radius=16)
        pygame.draw.rect(canvas, self.modal["color"], card, width=3, border_radius=16)

        born = self.modal.get("born", now)
        k = min(1.0, (now - born) / 0.2)
        title_font = self.fonts.get(30, bold=True)
        body_font = self.fonts.get(17)
        canvas.blit(title_font.render(self.modal["title"], True, self.modal["color"]),
                    (card.centerx - title_font.size(self.modal["title"])[0] // 2, card.y + 26))
        y = card.y + 74
        for line in lines:
            canvas.blit(body_font.render(line, True, TEXT),
                        (card.centerx - body_font.size(line)[0] // 2, y))
            y += 34
        canvas.blit(
            self.fonts.get(13).render("Enter — закрыть", True, MUTED),
            (card.centerx - 55, card.bottom - 28),
        )


def selfcheck():
    """Проверка упакованной сборки без окна: ресурсы, логика, сохранение.

    Запуск:  python main.py --selftest   (или MathIdle.exe --selftest)

    В .exe консоли нет, поэтому отчёт пишется в mathidle-selftest.txt
    рядом с программой (и дублируется в stdout, если он есть).
    """
    lines = []

    def pick_log_path():
        """Куда писать отчёт: рядом с .exe, иначе в APPDATA, иначе во временный каталог."""
        candidates = []
        try:
            candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
        except Exception:
            pass
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        candidates.append(os.path.join(base, "mathidle"))
        import tempfile
        candidates.append(tempfile.gettempdir())
        for folder in candidates:
            try:
                os.makedirs(folder, exist_ok=True)
                probe = os.path.join(folder, ".mathidle-write-probe")
                with open(probe, "w", encoding="utf-8") as fh:
                    fh.write("ok")
                os.remove(probe)
                return os.path.join(folder, "mathidle-selftest.txt")
            except OSError:
                continue
        return None

    log_path = pick_log_path()

    # первая же запись: если файл появился, значит загрузка прошла
    try:
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write("самопроверка запущена\n")
    except OSError:
        pass

    def dump():
        """Пишем отчёт сразу на каждом шаге — видно, где упало."""
        if not log_path:
            return
        try:
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError:
            pass

    def note(ok, text):
        lines.append(("  ok   " if ok else "  FAIL ") + text)
        dump()
        return ok

    def bail(exc):
        import traceback
        lines.append("")
        lines.append(f"  ОШИБКА: {type(exc).__name__}: {exc}")
        lines.append("  Трассировка:")
        lines.extend("    " + row for row in traceback.format_exc().splitlines())
        lines.append("")
        lines.append("ИТОГ: сборка НЕ прошла самопроверку")
        dump()
        if sys.stdout is not None:
            try:
                print("\n".join(lines))
            except (AttributeError, ValueError, OSError):
                pass
        return 1

    try:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        if sys.stdout is not None:
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass

        lines.append("=" * 58)
        lines.append(f"Math Idle {config.GAME['version']} — самопроверка сборки")
        lines.append("=" * 58)
        dump()

        pygame.init()
        pygame.display.set_mode((320, 240))
        note(True, "pygame инициализирован (видеодрайвер: "
                   + os.environ.get("SDL_VIDEODRIVER", "по умолчанию") + ")")

        fonts = assets.FontBook()
        note(os.path.exists(fonts.path), f"шрифт найден: {fonts.path}")
        sample = "Деньги · узелки · счётные палочки · счёты · Контрольная ×÷ −"
        missing = fonts.missing_glyphs(sample)
        note(not missing, "все символы интерфейса есть в шрифте"
             + ("" if not missing else " (нет " + "".join(missing) + ")"))

        # чистый лист: проверка не должна зависеть от прошлой игры
        st = state_mod.GameState()
        st.next_problem()
        note(st.current is not None and st.current["answer"] >= 0,
             f"пример сгенерирован: {st.current['text']} = {st.current['answer']}")

        st.money = 25.0
        ok, message = st.buy_upgrade("knots")
        note(ok, f"покупка узелков: {message}")
        note(abs(st.passive_rate() - 0.01) < 1e-9,
             f"пассивная скорость {economy.fmt_rate(st.passive_rate())} примера/с")

        # пассивный доход обязан капать во время игры, а не только оффлайн
        st.money = 0.0
        st.session_passive = 0.0
        for _ in range(60):
            st.tick(0.1)
        note(st.session_passive > 0,
             f"пассив капает во время игры: +{economy.fmt_money(st.session_passive)} за 6с")

        # настоящий игровой цикл: несколько секунд с окном, вводом и тиками
        game = GameUI(st)
        game.input = "7"
        game.press_enter()
        note(game.input == "", "ввод ответа обработан")
        canvas = pygame.Surface((W, H))
        game.draw(canvas, pygame.display.get_surface())
        note(True, "кадр интерфейса отрисован")
        game.run(max_seconds=1.5)
        note(True, "игровой цикл отработал (окно, тики, ввод, сохранение)")

        import tempfile
        save_path = os.path.join(tempfile.gettempdir(), "mathidle-selftest-save.json")
        try:
            st.save(save_path)
            back, _ = state_mod.GameState.load(save_path)
            note(abs(back.money - st.money) < 1e-9,
                 f"сохранение работает ({economy.fmt_money(back.money)})")
            note(back.base_levels == st.base_levels, "уровни улучшений сохраняются")
        finally:
            if os.path.exists(save_path):
                os.remove(save_path)

        failed = [line for line in lines if line.startswith("  FAIL")]
        lines.append("-" * 58)
        lines.append("ИТОГ: сборка исправна" if not failed else f"ИТОГ: проблем {len(failed)}")
        dump()
        pygame.quit()

        if sys.stdout is not None:
            try:
                print("\n".join(lines))
            except (AttributeError, ValueError, OSError):
                pass
        return 1 if failed else 0

    except BaseException as exc:          # noqa: BLE001 — отчёт нужен при любой ошибке
        try:
            pygame.quit()
        except Exception:
            pass
        return bail(exc)


def main():
    """Точка входа: грузим сохранение и запускаем игру."""
    st, welcome = state_mod.GameState.load()
    ui = GameUI(st)
    if welcome and welcome["earned"] > 0:
        ui.state.log(
            f"Пока тебя не было {economy.fmt_time(welcome['away'])}, "
            f"пассивные примеры заработали {economy.fmt_money(welcome['earned'])}",
            "info", ttl=8.0,
        )
    ui.run()


if __name__ == "__main__":
    main()
