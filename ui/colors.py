"""
colors — ANSI escape codes + theme system
cyberpunk/hacker aesthetic color palette
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Theme:
    """color theme for terminal output"""
    primary: str        # main brand color
    secondary: str      # accent
    success: str        # green tones
    warning: str        # yellow/orange
    error: str          # red
    info: str           # cyan/blue
    muted: str          # grey
    highlight: str      # bright accent
    bg_primary: str     # background
    bg_secondary: str   # alternate background


class Colors:
    """ANSI escape code constants + theme definitions"""

    # ─── base ANSI codes ───────────────────────────────────────────

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"
    HIDDEN = "\033[8m"
    STRIKE = "\033[9m"

    # ─── foreground colors ─────────────────────────────────────────

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # bright variants
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # ─── background colors ─────────────────────────────────────────

    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"
    BG_BRIGHT_BLACK = "\033[100m"
    BG_BRIGHT_RED = "\033[101m"
    BG_BRIGHT_GREEN = "\033[102m"
    BG_BRIGHT_YELLOW = "\033[103m"
    BG_BRIGHT_BLUE = "\033[104m"
    BG_BRIGHT_MAGENTA = "\033[105m"
    BG_BRIGHT_CYAN = "\033[106m"
    BG_BRIGHT_WHITE = "\033[107m"

    # ─── predefined themes ─────────────────────────────────────────

    THEME_HACKER = Theme(
        primary=BRIGHT_GREEN,
        secondary=CYAN,
        success=GREEN,
        warning=BRIGHT_YELLOW,
        error=BRIGHT_RED,
        info=CYAN,
        muted=BRIGHT_BLACK,
        highlight=BRIGHT_GREEN + BOLD,
        bg_primary=BG_BLACK,
        bg_secondary=BG_BRIGHT_BLACK,
    )

    THEME_NEON = Theme(
        primary=BRIGHT_MAGENTA,
        secondary=BRIGHT_CYAN,
        success=BRIGHT_GREEN,
        warning=BRIGHT_YELLOW,
        error=BRIGHT_RED,
        info=BRIGHT_BLUE,
        muted=BRIGHT_BLACK,
        highlight=BRIGHT_MAGENTA + BOLD,
        bg_primary=BG_BLACK,
        bg_secondary=BG_BRIGHT_BLACK,
    )

    THEME_OCEAN = Theme(
        primary=BRIGHT_BLUE,
        secondary=CYAN,
        success=GREEN,
        warning=YELLOW,
        error=RED,
        info=BLUE,
        muted=BRIGHT_BLACK,
        highlight=BRIGHT_CYAN + BOLD,
        bg_primary=BG_BLACK,
        bg_secondary=BG_BLUE,
    )

    THEME_SUNSET = Theme(
        primary=BRIGHT_YELLOW,
        secondary=BRIGHT_RED,
        success=GREEN,
        warning=YELLOW,
        error=RED,
        info=CYAN,
        muted=BRIGHT_BLACK,
        highlight=BRIGHT_YELLOW + BOLD,
        bg_primary=BG_BLACK,
        bg_secondary=BG_RED,
    )

    # ─── current theme ─────────────────────────────────────────────

    _current_theme: Theme = THEME_HACKER

    @classmethod
    def set_theme(cls, theme: Theme):
        cls._current_theme = theme

    @classmethod
    def get_theme(cls) -> Theme:
        return cls._current_theme

    # ─── styled text shortcuts ─────────────────────────────────────

    @classmethod
    def primary(cls, text: str) -> str:
        return f"{cls._current_theme.primary}{text}{cls.RESET}"

    @classmethod
    def secondary(cls, text: str) -> str:
        return f"{cls._current_theme.secondary}{text}{cls.RESET}"

    @classmethod
    def success(cls, text: str) -> str:
        return f"{cls._current_theme.success}{text}{cls.RESET}"

    @classmethod
    def warning(cls, text: str) -> str:
        return f"{cls._current_theme.warning}{text}{cls.RESET}"

    @classmethod
    def error(cls, text: str) -> str:
        return f"{cls._current_theme.error}{text}{cls.RESET}"

    @classmethod
    def info(cls, text: str) -> str:
        return f"{cls._current_theme.info}{text}{cls.RESET}"

    @classmethod
    def muted(cls, text: str) -> str:
        return f"{cls._current_theme.muted}{text}{cls.RESET}"

    @classmethod
    def highlight(cls, text: str) -> str:
        return f"{cls._current_theme.highlight}{text}{cls.RESET}"

    @classmethod
    def bold(cls, text: str) -> str:
        return f"{cls.BOLD}{text}{cls.RESET}"

    @classmethod
    def dim(cls, text: str) -> str:
        return f"{cls.DIM}{text}{cls.RESET}"

    @classmethod
    def tag(cls, text: str, color: str = None) -> str:
        """colored tag in brackets: [ TAG ]"""
        c = color or cls._current_theme.primary
        return f"{cls.muted('[')} {c}{text}{cls.RESET} {cls.muted(']')}"

    @classmethod
    def status_icon(cls, status: str) -> str:
        """colored status indicator"""
        icons = {
            "success": cls.success("✓"),
            "error": cls.error("✗"),
            "warning": cls.warning("⚠"),
            "info": cls.info("ℹ"),
            "found": cls.success("✓"),
            "not_found": cls.muted("○"),
            "running": cls.secondary("◌"),
            "pending": cls.muted("○"),
        }
        return icons.get(status, cls.muted("○"))

    @classmethod
    def strip_ansi(cls, text: str) -> str:
        """remove ANSI codes for plain text output"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)


# module-level alias
styled = Colors