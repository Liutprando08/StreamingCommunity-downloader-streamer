from rich.console import Console
from rich.theme import Theme

SCHEMA_THEME = Theme(
    {
        "error": "bold red",
        "warning": "bold yellow",
        "success": "bold green",
        "info": "cyan",
        "accent": "magenta",
        "highlight": "purple",
        "dim": "dim",
        "bold_warning": "bold yellow",
        "bold_info": "bold cyan",
        "bold_success": "bold green",
        "bold_error": "bold red",
        "bar_complete": "bright_magenta",
        "bar_incomplete": "dim white",
        "bar_speed": "red",
        "bar_size": "green",
        "bar_duration": "yellow",
        "bar_segments_current": "green",
        "bar_segments_total": "cyan",
        "table_header": "cyan",
        "table_border": "blue",
        "table_row_alt": "dim",
    }
)

console = Console(theme=SCHEMA_THEME)
