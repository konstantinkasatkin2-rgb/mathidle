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

TABS = [("upgrades", "Улучшения"), ("test", "Контрольная"), ("shop", "Магазин")]

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
        if self.flash > 0:
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            overlay.fill((*self.flash_color, int(70 * self.flash / 0.35)))
            canvas.blit(overlay, (0, 0))

        win_w, win_h = window.get_size()
        scale = min(win_w / W, win_h / H)
        frame = pygame.transform.smoothscale(canvas, (int(W * scale), int(H * scale)))
        window.fill(BG)
        window.blit(frame, ((win_w - frame.get_width()) // 2 + int(offset[0]),
                            (win_h - frame.get_height()) // 2 + int(offset[1])))

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
        canvas.blit(label.render("ПАССИВНО", True, MUTED), (x, 10))
        per_sec = rate * self.state.passive_reward_per_example()
        canvas.blit(
            money_font.render(f"+{economy.fmt_money(per_sec)} в секунду", True, ACCENT), (x, 24)
        )
        canvas.blit(
            small.render(
                f"{economy.fmt_rate(rate)} примера/с · {economy.fmt_money(self.state.passive_reward_per_example())} за пример",
                True, MUTED,
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
        # заголовок панели
        head = self.fonts.get(15, bold=True)
        if testing:
            title = f"Контрольная №{st.test['level']}  ·  пример {st.test['index'] + 1} из {len(st.test['problems'])}"
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
            canvas.blit(hint.render(msg, True, GOLD), (panel.right - 24 - hint.size(msg)[0], panel.y + 16))

        # сам пример
        if st.current:
            age = max(0.0, st.now - st.shown_at)
            pop = min(1.0, age / 0.18)
            size = int(56 * (0.92 + 0.08 * pop))
            font = self.fonts.get(size, bold=True)
            text = st.current["text"] + " ="
            surf = font.render(text, True, TEXT)
            rect = surf.get_rect(center=(panel.centerx, panel.y + 130))
            canvas.blit(surf, rect)

            # сложность примера
            diff = st.current["difficulty"]
            bar_w = 320
            bar = pygame.Rect(panel.centerx - bar_w // 2, panel.y + 172, bar_w, 8)
            pygame.draw.rect(canvas, LINE, bar, border_radius=4)
            filled = max(1, int(bar_w * diff)) if diff > 0 else 0
            if filled:
                pygame.draw.rect(
                    canvas, self._diff_color(diff),
                    pygame.Rect(bar.x, bar.y, filled, bar.h), border_radius=4,
                )
            small = self.fonts.get(13)
            label = f"сложность {int(diff * 100)}%"
            canvas.blit(small.render(label, True, MUTED),
                        (panel.centerx - small.size(label)[0] // 2, bar.bottom + 6))

        # поле ответа
        box = pygame.Rect(panel.x + 24, panel.y + 205, panel.w - 48, 62)
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
        self.draw_keypad(canvas, pygame.Rect(panel.x + 24, panel.y + 285, panel.w - 48, 240))

        hint = self.fonts.get(13)
        canvas.blit(
            hint.render("Enter — ответ   ·   Backspace — стереть   ·   Tab — вкладка   ·   Esc — выход",
                        True, (86, 96, 114)),
            (panel.x + 24, panel.bottom - 26),
        )

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
        tw = (panel.w - 32) / 3
        for i, (tid, title) in enumerate(TABS):
            rect = pygame.Rect(panel.x + 16 + i * (tw + 0), panel.y + 14, int(tw - 6), 40)
            rect.y = panel.y + 14
            rect.x = panel.x + 16 + i * int(tw)
            active = self.tab == tid
            locked = tid == "shop" and not st.shop_unlocked
            pygame.draw.rect(canvas, PANEL_HI if active else BG, rect, border_radius=8)
            if active:
                pygame.draw.rect(canvas, ACCENT, rect, width=2, border_radius=8)
            font = self.fonts.get(17, bold=True)
            if locked:
                surf = font.render(title + " (закрыто)", True, (96, 106, 124))
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
        else:
            self.draw_tab_shop(canvas, body)

    def set_tab(self, tab):
        if tab == "shop" and not self.state.shop_unlocked:
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
        self._scroll_area(canvas, rect, 10 + len(config.BASE_UPGRADES) * 96 + 70)
        y = rect.y - self.scroll[self.tab]

        info = self.fonts.get(13)
        rate = st.passive_rate()
        line = (f"Сейчас: {economy.fmt_rate(rate)} примера/с   ·   "
                f"{economy.fmt_money(rate * st.passive_reward_per_example())}/с   ·   "
                f"всего {economy.fmt_rate(sum(u['max_rate'] for u in config.BASE_UPGRADES))} максимум")
        canvas.blit(info.render(line, True, MUTED), (rect.x, y))
        y += 26

        for up in config.BASE_UPGRADES:
            level = st.upgrade_level(up["id"])
            maxl = st.upgrade_max_level(up["id"])
            full = st.upgrade_full(up["id"])
            cost = st.upgrade_cost(up["id"])
            card = pygame.Rect(rect.x, y, rect.w, 84)
            enabled = (not full) and st.money >= cost
            title = up["name"]
            if full:
                subtitle = f"максимум {up['max_rate']} примера/с"
            else:
                subtitle = (f"+{up['rate_per_level']} примера/с   ·   ур. {level}/{maxl}   ·   "
                            f"цена: {economy.fmt_money(cost)}")
            btn = Button(card, title, subtitle, ACCENT if enabled else GOLD,
                         enabled, "" if full else economy.fmt_money(cost))
            btn.action = (lambda u=up["id"]: self.do_buy_upgrade(u))
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)

            # полоса прогресса скорости
            bar = pygame.Rect(card.x + 14, card.bottom - 12, card.w - 28, 5)
            pygame.draw.rect(canvas, LINE, bar, border_radius=2)
            filled = int(bar.w * (st.upgrade_rate(up["id"]) / up["max_rate"]))
            pygame.draw.rect(canvas, ACCENT, (bar.x, bar.y, filled, bar.h), border_radius=2)
            y += 96

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

    def do_buy_all(self):
        bought, spent = self.state.buy_all_upgrades()
        if not bought:
            self.state.log("Не хватает денег на улучшения", "fail", ttl=2.0)
        else:
            self.flash, self.flash_color = 0.25, GREEN

    def draw_tab_test(self, canvas, rect):
        st = self.state
        self._scroll_area(canvas, rect, 430)
        y = rect.y - self.scroll[self.tab]
        big = self.fonts.get(24, bold=True)
        body = self.fonts.get(15)
        small = self.fonts.get(13)

        card = pygame.Rect(rect.x, y, rect.w, 190)
        pygame.draw.rect(canvas, BG, card, border_radius=12)
        pygame.draw.rect(canvas, BLUE, card, width=2, border_radius=12)
        y = card.y + 16

        if st.test:
            test = st.test
            canvas.blit(big.render(f"Контрольная №{test['level']} идёт", True, BLUE), (card.x + 16, y))
            y += 40
            for line in [
                f"Пример {test['index'] + 1} из {len(test['problems'])}",
                f"Осталось: {economy.fmt_time(test['limit'] - test['elapsed'])}",
                f"Награда: {economy.fmt_money(economy.test_reward(test['level']))}",
            ]:
                canvas.blit(body.render(line, True, TEXT), (card.x + 16, y))
                y += 26
            y += 6
            btn = Button(pygame.Rect(card.x + 16, y, 220, 48), "Прервать", "вернуть билет", RED, True)
            btn.action = self.do_abort_test
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)
            y = card.bottom + 16
        else:
            canvas.blit(big.render("Контрольная", True, BLUE), (card.x + 16, y))
            y += 38
            level = st.test_level
            lines = [
                f"Билет: {economy.fmt_money(config.TEST['entry_price'])}",
                f"Примеров: {economy.test_problem_count(level)}",
                f"Сложность: {int(economy.test_difficulty(level) * 100)}%",
                f"Время: {economy.fmt_time(economy.test_time_limit(level, st.grade_levels))}",
                f"Награда: {economy.fmt_money(economy.test_reward(level))}",
                f"Пройдено: {st.tests_passed}",
            ]
            for line in lines:
                canvas.blit(body.render(line, True, TEXT), (card.x + 16, y))
                y += 25
            y += 8
            can = st.can_start_test()
            label = "Начать контрольную" if can else f"Нужно {economy.fmt_money(config.TEST['entry_price'])}"
            btn = Button(pygame.Rect(card.x + 16, y, 240, 46), label, "", GREEN, can)
            btn.action = self.do_start_test
            btn.draw(canvas, self.fonts)
            self._pending.append(btn)
            y = card.bottom + 20

        note = [
            "Правила контрольной:",
            "• ни одной ошибки, иначе провал (билет возвращается)",
            "• не уложишься во время — тоже провал",
            "• сдаёшь — получаешь награду и следующий уровень",
            "",
            "После первой сданной контрольной открывается",
            "магазин контрольных улучшений: множители денег,",
            "более широкое окно скорости и новые действия.",
        ]
        for i, line in enumerate(note):
            color = MUTED if i else TEXT
            font = body if i == 0 else small
            canvas.blit(font.render(line, True, color), (rect.x + 4, y + i * 21))
        canvas.set_clip(None)

    def do_start_test(self):
        ok, message = self.state.start_test()
        if ok:
            self.input = ""
            self.tab = "upgrades"
        else:
            self.state.log(message, "fail", ttl=2.5)

    def do_abort_test(self):
        result = self.state.abort_test()
        if result:
            self.modal = self._result_modal(result)

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

        st, _welcome = state_mod.GameState.load()
        st.next_problem()
        note(st.current is not None and st.current["answer"] >= 0,
             f"пример сгенерирован: {st.current['text']} = {st.current['answer']}")

        for _ in range(50):
            st.tick(0.1)
        st.money = 25.0
        ok, message = st.buy_upgrade("knots")
        note(ok, f"покупка узелков: {message}")
        note(abs(st.passive_rate() - 0.01) < 1e-9,
             f"пассивная скорость {economy.fmt_rate(st.passive_rate())} примера/с")

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
