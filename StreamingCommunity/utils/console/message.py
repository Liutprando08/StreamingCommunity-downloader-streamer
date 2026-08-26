# 3.12.23
import platform
import subprocess

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
        try:
            subprocess.run(
                "cls" if platform.system() == "Windows" else "clear",
                shell=False,
                check=False,
            )
        except Exception:
            pass

    if SHOW:
        console.print(f"[purple]{msg}")
