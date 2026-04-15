import logging
import sys
import threading
from collections import deque
from datetime import datetime

import pytz
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

GMT = pytz.timezone("UTC")


class UILogHandler(logging.Handler):
    def __init__(self, ui: "BotUI"):
        super().__init__()
        self.ui = ui

    def emit(self, record):
        try:
            self.ui.add_log(self.format(record), record.levelname)
        except Exception:
            pass


class BotUI:
    def __init__(self):
        self._lock = threading.Lock()
        self._opportunities: deque = deque(maxlen=10)
        self._logs: deque = deque(maxlen=15)
        self._start_time = datetime.now()
        self._last_scan: datetime | None = None
        self._next_scan_time: datetime | None = None
        self._market_open = False
        self._alerts_today = 0
        self._scanning = False
        self._tick = 0
        self._is_tty = sys.stdout.isatty()
        self._console = Console()
        self._live: Live | None = None
        self._ticker_thread: threading.Thread | None = None
        self._running = False

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    # --- public API (thread-safe) ---

    def add_log(self, message: str, level: str = "INFO"):
        if level == "TICK":
            return
        color = {"ERROR": "red", "WARNING": "yellow", "INFO": "white", "DEBUG": "dim"}.get(level, "white")
        now = datetime.now(GMT).strftime("%H:%M:%S")
        entry = Text(f"[{now}] {message}", style=color)
        with self._lock:
            self._logs.append(entry)
        self._refresh()

    def add_opportunity(self, opportunity: dict):
        with self._lock:
            self._opportunities.appendleft({
                **opportunity,
                "_time": datetime.now(GMT).strftime("%H:%M"),
            })
            self._alerts_today += 1
        self._refresh()

    def set_market_open(self, is_open: bool):
        with self._lock:
            self._market_open = is_open
        self._refresh()

    def set_next_scan(self, dt: datetime | None):
        with self._lock:
            self._next_scan_time = dt
        self._refresh()

    def set_last_scan(self):
        with self._lock:
            self._last_scan = datetime.now(GMT)
        self._refresh()

    def set_scanning(self, scanning: bool):
        with self._lock:
            self._scanning = scanning
        self._refresh()

    def _ticker_loop(self):
        import time
        while self._running:
            try:
                self._refresh()
            except Exception:
                pass
            time.sleep(0.15)

    def start(self):
        if self._is_tty:
            self._console.show_cursor(False)
            self._live = Live(
                self._build_layout(),
                refresh_per_second=10,
                screen=True,
                console=self._console,
            )
            self._live.start()
            self._running = True
            self._ticker_thread = threading.Thread(target=self._ticker_loop, daemon=True)
            self._ticker_thread.start()
        else:
            self._console.print("[bold blue]Stock Opportunity Bot[/bold blue] starting...")

    def stop(self):
        self._running = False
        if self._live:
            self._live.stop()
        self._console.show_cursor(True)

    # --- internal rendering ---

    def _refresh(self):
        if self._live:
            self._tick += 1
            self._live.update(self._build_layout())

    def _build_header(self) -> Panel:
        spinner_char = self._SPINNER[self._tick % len(self._SPINNER)]

        status = Text()
        if self._scanning:
            status.append(f"{spinner_char} Scanning...", style="bold yellow")
        elif self._market_open:
            status.append(f"{spinner_char} Live", style="bold green")
        else:
            status.append(f"{spinner_char} Market Closed", style="bold red")

        title = Text()
        title.append("  Stock Opportunity Bot  ", style="bold white")
        title.append("                                        ")
        title.append_text(status)

        return Panel(title, style="blue", padding=(0, 1))

    def _build_status_panel(self) -> Panel:
        uptime = datetime.now() - self._start_time
        h, rem = divmod(int(uptime.total_seconds()), 3600)
        m = rem // 60

        if self._next_scan_time:
            secs_left = max(0, int((self._next_scan_time - datetime.now()).total_seconds()))
            nm, ns = divmod(secs_left, 60)
            next_str = f"{nm}m {ns:02d}s"
        else:
            next_str = "—"

        last_str = self._last_scan.strftime("%H:%M:%S") if self._last_scan else "—"
        market_text = Text("OPEN", style="bold green") if self._market_open else Text("CLOSED", style="bold red")

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", justify="right")
        grid.add_column()
        grid.add_row("Market", market_text)
        grid.add_row("Last scan", last_str)
        grid.add_row("Next scan", next_str)
        grid.add_row("Uptime", f"{h}h {m:02d}m")
        grid.add_row("Alerts today", str(self._alerts_today))

        return Panel(grid, title="[bold]Status[/bold]", border_style="blue", padding=(1, 2))

    def _build_opportunities_panel(self) -> Panel:
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Ticker", style="bold", width=8)
        table.add_column("Company", ratio=2)
        table.add_column("Signal", ratio=2)
        table.add_column("Strength", width=8)
        table.add_column("Confidence", width=10)
        table.add_column("Time", width=6)

        opps = list(self._opportunities)
        if not opps:
            table.add_row("—", "No alerts yet", "", "", "", "")
        else:
            for opp in opps:
                strength = opp.get("signal_strength", "")
                strength_color = {"High": "green", "Medium": "yellow", "Low": "blue"}.get(strength, "white")

                score = opp.get("confidence_score")
                try:
                    score = int(score)
                    score_color = "green" if score >= 75 else "yellow" if score >= 50 else "red"
                    score_text = Text(f"{score}/100", style=f"bold {score_color}")
                except (TypeError, ValueError):
                    score_text = Text("N/A", style="dim")

                table.add_row(
                    f"${opp.get('ticker', '?')}",
                    opp.get("company_name", "")[:30],
                    opp.get("signal_type", "")[:25],
                    Text(strength, style=f"bold {strength_color}"),
                    score_text,
                    opp.get("_time", ""),
                )

        return Panel(table, title="[bold]Recent Opportunities[/bold]", border_style="green", padding=(0, 1))

    def _build_log_panel(self) -> Panel:
        with self._lock:
            logs = list(self._logs)

        content = Text()
        for i, entry in enumerate(logs):
            if i:
                content.append("\n")
            content.append_text(entry)

        return Panel(content, title="[bold]Log[/bold]", border_style="dim", padding=(0, 1))

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="logs", size=18),
        )
        layout["body"].split_row(
            Layout(self._build_status_panel(), name="status", ratio=1),
            Layout(self._build_opportunities_panel(), name="opportunities", ratio=3),
        )
        layout["header"].update(self._build_header())
        layout["logs"].update(self._build_log_panel())
        return layout
