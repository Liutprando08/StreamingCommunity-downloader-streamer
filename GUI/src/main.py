"""Entry point for the Flet mobile interface.

Run from the repository root:

    python GUI/src/main.py

Build an Android APK from the GUI directory (see GUI/README.md):

    cd GUI && flet build apk
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
_ROOT = _SRC.parents[1]
for _path in (str(_ROOT), str(_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import flet as ft


def main(page: ft.Page) -> None:
    try:
        from oste.ui import main as run_app
    except Exception as exc:  # noqa: BLE001 - show a readable error on screen
        page.title = "OSTE Mobile"
        page.bgcolor = "#0b1020"
        page.add(
            ft.SafeArea(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.ERROR_OUTLINE, color="#f38ba8", size=42),
                            ft.Text(
                                "Impossibile avviare OSTE Mobile",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color="#cdd6f4",
                            ),
                            ft.Text(str(exc), size=12, color="#7f8bb0"),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    padding=24,
                    alignment=ft.alignment.center,
                    expand=True,
                ),
                expand=True,
            )
        )
        return

    run_app(page)


if __name__ == "__main__":
    ft.app(target=main)
