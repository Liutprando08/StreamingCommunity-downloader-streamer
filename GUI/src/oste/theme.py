"""Colours and small reusable widgets for the mobile UI."""

from __future__ import annotations

import flet as ft

BG = "#0b1020"
SURFACE = "#141b31"
SURFACE_ALT = "#1b2440"
SURFACE_HI = "#243056"
PRIMARY = "#cba6f7"
ACCENT = "#89dceb"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
RED = "#f38ba8"
TEXT = "#cdd6f4"
MUTED = "#7f8bb0"

RADIUS = 16


def card(content: ft.Control, **kwargs) -> ft.Container:
    kwargs.setdefault("bgcolor", SURFACE)
    kwargs.setdefault("border_radius", RADIUS)
    kwargs.setdefault("padding", ft.padding.all(14))
    return ft.Container(content=content, **kwargs)


def section_title(text: str, **kwargs) -> ft.Text:
    return ft.Text(
        text,
        size=16,
        weight=ft.FontWeight.BOLD,
        color=ACCENT,
        **kwargs,
    )


def muted(text: str, size: float = 12, **kwargs) -> ft.Text:
    return ft.Text(text, size=size, color=MUTED, **kwargs)


def badge(text: str, color: str = ACCENT) -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=11, color=color, weight=ft.FontWeight.W_600),
        bgcolor=ft.Colors.with_opacity(0.14, color),
        border_radius=99,
        padding=ft.padding.symmetric(horizontal=10, vertical=4),
    )
