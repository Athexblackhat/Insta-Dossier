"""
progress tracker — live progress bars, spinners, status updates
wraps rich library for beautiful terminal progress
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# rich is optional — graceful fallback if not installed
try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn, TextColumn,
        TimeElapsedColumn, TimeRemainingColumn, TaskID,
    )
    from rich.spinner import Spinner
    from rich.text import Text
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class PhaseProgress:
    """tracks progress of a single extraction phase"""
    name: str
    phase_num: int
    total_phases: int
    status: str = "pending"  # pending, running, complete, error
    data_found: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.status in ("complete", "error")

    @property
    def duration_str(self) -> str:
        if self.duration_ms > 1000:
            return f"{self.duration_ms / 1000:.1f}s"
        return f"{self.duration_ms:.0f}ms"


class ProgressTracker:
    """
    manages live progress display for the extraction pipeline

    usage:
        tracker = ProgressTracker()
        tracker.start()

        tracker.start_phase(1, 6, "Public Profile Scraping")
        tracker.add_result("✓", "full_name: John Doe")
        tracker.add_result("✓", "followers: 4,521")
        tracker.complete_phase()

        tracker.start_phase(2, 6, "Bio Parsing")
        tracker.add_result("✓", "email found: j****@gmail.com")
        tracker.complete_phase()

        tracker.finish()
    """

    def __init__(self, use_rich: bool = True, show_spinners: bool = True):
        self.use_rich = use_rich and RICH_AVAILABLE
        self.show_spinners = show_spinners
        self._console: Optional["Console"] = None
        self._progress: Optional["Progress"] = None
        self._live: Optional["Live"] = None
        self._current_task: Optional[TaskID] = None
        self._phases: list[PhaseProgress] = []
        self._current_phase: Optional[PhaseProgress] = None
        self._start_time: float = 0.0
        self._lines_buffer: list[str] = []

        if self.use_rich:
            self._console = Console()

    def start(self):
        """initialize the progress display"""
        self._start_time = time.monotonic()

        if self.use_rich and self._console:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=30),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=self._console,
                expand=False,
            )
            self._progress.start()
        else:
            print()

    def start_phase(self, phase_num: int, total_phases: int, name: str):
        """begin a new extraction phase"""
        phase = PhaseProgress(
            name=name,
            phase_num=phase_num,
            total_phases=total_phases,
            status="running",
            start_time=time.monotonic(),
        )
        self._current_phase = phase
        self._phases.append(phase)
        self._lines_buffer = []

        if self.use_rich and self._progress:
            desc = f"PHASE {phase_num}/{total_phases} — {name}"
            self._current_task = self._progress.add_task(
                f"[cyan]{desc}", total=100
            )
        else:
            # fallback: simple text output
            print(f"  ══ PHASE {phase_num}/{total_phases} — {name.upper()} ══")
            print(f"  {'●':<2} Running...")

    def update_progress(self, percent: float):
        """update the progress bar percentage"""
        if self.use_rich and self._progress and self._current_task is not None:
            self._progress.update(self._current_task, completed=percent)

    def add_result(self, icon: str, message: str):
        """add a result line to the current phase"""
        self._lines_buffer.append(f"    {icon} {message}")

        if not self.use_rich:
            print(f"    {icon} {message}")

    def add_error(self, message: str):
        """add an error line"""
        if self._current_phase:
            self._current_phase.errors.append(message)
        self._lines_buffer.append(f"    ✗ {message}")
        if not self.use_rich:
            print(f"    ✗ {message}")

    def complete_phase(self, status: str = "complete"):
        """mark the current phase as complete"""
        if self._current_phase:
            self._current_phase.status = status
            self._current_phase.end_time = time.monotonic()
            self._current_phase.duration_ms = (
                (self._current_phase.end_time - self._current_phase.start_time) * 1000
            )

        if self.use_rich and self._progress and self._current_task is not None:
            self._progress.update(
                self._current_task,
                completed=100,
                description=f"[green]✓ {self._current_phase.name} — {self._current_phase.duration_str}",
            )

        duration = self._current_phase.duration_str if self._current_phase else ""
        if not self.use_rich:
            status_text = "✓ COMPLETE" if status == "complete" else "✗ FAILED"
            print(f"  {status_text} ({duration})")
            print()

        self._current_phase = None
        self._current_task = None

    def fail_phase(self, error: str = ""):
        """mark the current phase as failed"""
        if error and self._current_phase:
            self._current_phase.errors.append(error)
        self.complete_phase(status="error")

    def show_live_status(self, message: str):
        """show a temporary status message"""
        if self.use_rich and self._progress:
            if self._current_task is not None:
                self._progress.update(self._current_task, description=f"[yellow]{message}")
        else:
            print(f"  ... {message}")

    def finish(self, total_time: float = None):
        """stop the progress display"""
        if total_time is None:
            total_time = time.monotonic() - self._start_time

        if self.use_rich and self._progress:
            self._progress.stop()

        # print phase summary if using rich
        if self.use_rich and self._console:
            self._print_phase_summary(total_time)
        else:
            print(f"  ⏱ Total time: {total_time:.1f}s")
            print()

    def _print_phase_summary(self, total_time: float):
        """print a summary table of all phases"""
        if not self._phases or not self._console:
            return

        table = Table(title="Extraction Summary", title_style="bold cyan")
        table.add_column("Phase", style="dim", width=8)
        table.add_column("Name", style="cyan")
        table.add_column("Status", width=10)
        table.add_column("Duration", width=10)
        table.add_column("Results", width=30)

        for phase in self._phases:
            status_style = "green" if phase.status == "complete" else "red"
            status_icon = "✓" if phase.status == "complete" else "✗"
            phase_label = f"{phase.phase_num}/{phase.total_phases}"

            results = ", ".join([
                line.strip().lstrip("✓⚠✗○").strip()
                for line in self._lines_buffer[:3]
            ]) if self._lines_buffer else "—"

            table.add_row(
                phase_label,
                phase.name,
                f"[{status_style}]{status_icon} {phase.status}[/]",
                phase.duration_str,
                results[:28] + "..." if len(results) > 28 else results,
            )

        table.add_row("", "", "", f"[bold]{total_time:.1f}s[/]", "[dim]total[/]")
        self._console.print(table)
        print()

    @property
    def total_duration(self) -> float:
        return time.monotonic() - self._start_time if self._start_time else 0.0