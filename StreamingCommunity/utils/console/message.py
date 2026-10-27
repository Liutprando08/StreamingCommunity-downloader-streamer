# 3.12.23
import platform
import subprocess
from contextlib import suppress

from StreamingCommunity.utils.console.shared import console


def start_message(clean: bool = True):
    """Display a stylized start message in the console."""
    from StreamingCommunity.utils import config_manager

    CLEAN = config_manager.config.get_bool("DEFAULT", "show_message")
    SHOW = config_manager.config.get_bool("DEFAULT", "show_message")

    msg = r"""
[green]→[purple] / __ \___ / /____  [yellow] __ __ [purple]   / __/ /________ ___ ___ _  (_)__  ___ _
[green]→[purple]/ /_/ (_-</ __/ -_) [yellow] \ \ / [purple]  _\ \/ __/ __/ -_) _ `/  ' \/ / _ \/ _ `/
[green]→[purple]\____/___/\__/\__/  [yellow] /_\_\ [purple] /___/\__/_/  \__/\_,_/_/_/_/_//_/\_,__ /
[green]→[purple]                                                              /___/
    """
    if CLEAN and clean:
        with suppress(OSError):
            subprocess.run(
                "cls" if platform.system() == "Windows" else "clear",
                shell=False,
                check=False,
            )

    if SHOW:
        # Imported lazily: importing ``StreamingCommunity.upload.version`` runs
        # the ``upload`` package initializer, which itself imports ``utils``.
        # A module-level import here would create a circular import while the
        # utils package is still being initialized.
        from StreamingCommunity.upload.version import __author__, __title__, __version__

        console.print(f"[purple]{msg}")
        console.print(f"[dim]{__title__} {__version__} · {__author__}[/]")
