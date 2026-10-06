"""Загрузка ресурсов (работает и из .exe, собранного PyInstaller)."""

import os
import sys

import pygame

from . import config

_root = None


def root():
    """Корень проекта (или временная папка PyInstaller)."""
    global _root
    if _root is None:
        if getattr(sys, "frozen", False):
            _root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _root


def resource(*parts):
    return os.path.join(root(), *parts)


class BoldFont:
    """Обёртка, которая «жирнит» текст.

    Roboto в репозитории — вариативный шрифт, и `set_bold` даёт слишком
    слабый эффект, поэтому поверх рисуем ещё два смещённых слоя.
    Интерфейс вызывает только `.render()` / `.size()`, как у pygame.font.Font.
    """

    def __init__(self, font):
        self._font = font

    def render(self, text, antialias=True, color=(255, 255, 255), background=None):
        base = self._font.render(text, antialias, color, background)
        out = base.copy()
        out.blit(base, (1, 0))
        out.blit(base, (0, 1))
        out.blit(base, (1, 1))
        return out

    def size(self, text):
        w, h = self._font.size(text)
        return (w + 1, h)

    def metrics(self, ch):
        return self._font.metrics(ch)

    def get_height(self):
        return self._font.get_height()


class FontBook:
    """Кэш шрифтов с поддержкой «жирного» начертания."""

    def __init__(self, size=20):
        self.path = resource(config.GAME["font"])
        self._cache = {}
        self.default_size = size

    def get(self, size, bold=False):
        size = int(size)
        key = (size, bold)
        if key in self._cache:
            return self._cache[key]
        font = pygame.font.Font(self.path, size)
        if bold:
            try:
                font.set_bold(True)
            except (AttributeError, pygame.error):  # pragma: no cover - зависит от SDL_ttf
                pass
            font = BoldFont(font)
        self._cache[key] = font
        return font

    def missing_glyphs(self, text):
        """Символы, которых нет в шрифте (для самопроверки)."""
        missing = []
        for ch in set(text):
            if ch in " \n\t":
                continue
            metrics = self.get(self.default_size).metrics(ch)
            if not metrics or metrics[0] is None:
                missing.append(ch)
        return missing
