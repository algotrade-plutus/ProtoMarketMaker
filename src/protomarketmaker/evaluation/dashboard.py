"""
Terminal Dashboard

Live trading dashboard using rich library.
"""
from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
import time
from datetime import datetime
from typing import Optional
import logging


class TradingDashboard:
    """
    Live terminal dashboard

    Displays:
    - Current positions
    - Recent orders
    - Performance metrics
    - System status
    - Redis statistics

    Example:
        dashboard = TradingDashboard(session)
        dashboard.start(refresh_rate=1.0)
    """

    def __init__(self, session):
        """
        Initialize dashboard

        Args:
            session: RedisTradingSession instance
        """
        self.session = session
        self.console = Console()
        self.running = False
        self.logger = logging.getLogger(__name__)

    def generate_layout(self) -> Layout:
        """Generate dashboard layout"""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=5)
        )

        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        layout["left"].split_column(
            Layout(name="positions", ratio=2),
            Layout(name="orders", ratio=1)
        )

        layout["right"].split_column(
            Layout(name="metrics", ratio=1),
            Layout(name="redis", ratio=1)
        )

        return layout

    def render_header(self) -> Panel:
        """Render header panel"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header_text = Text()
        header_text.append("📊 ", style="bold blue")
        header_text.append("Paper Trading Dashboard", style="bold white")
        header_text.append(f" | {current_time}", style="dim")

        return Panel(header_text, style="bold blue")

    def render_positions(self) -> Table:
        """Render positions table"""
        table = Table(title="💼 Positions", show_header=True, header_style="bold cyan")
        table.add_column("Contract", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("Unrealized PnL", justify="right")
        table.add_column("Realized PnL", justify="right")

        try:
            summary = self.session.get_summary()
            positions = summary['portfolio']['positions']

            if not positions or all(pos['quantity'] == 0 for pos in positions):
                table.add_row("—", "—", "—", "—", "—", style="dim")
            else:
                for pos in positions:
                    if pos['quantity'] != 0:
                        unrealized_pnl = pos.get('unrealized_pnl', 0)
                        realized_pnl = pos.get('realized_pnl', 0)

                        # Color based on PnL
                        unrealized_color = "green" if unrealized_pnl >= 0 else "red"
                        realized_color = "green" if realized_pnl >= 0 else "red"

                        table.add_row(
                            pos['contract'],
                            str(pos['quantity']),
                            f"{pos['average_price']:.1f}",
                            f"[{unrealized_color}]{unrealized_pnl:,.2f}[/{unrealized_color}]",
                            f"[{realized_color}]{realized_pnl:,.2f}[/{realized_color}]"
                        )
        except Exception as e:
            table.add_row("Error", str(e), "—", "—", "—", style="red")

        return table

    def render_orders(self) -> Table:
        """Render orders table"""
        table = Table(title="📋 Orders", show_header=True, header_style="bold yellow")
        table.add_column("Type", style="yellow")
        table.add_column("Count", justify="right")

        try:
            summary = self.session.get_summary()
            orders = summary['orders']

            table.add_row("Total", str(orders.get('total_orders', 0)))
            table.add_row("Filled", str(orders.get('filled_orders', 0)), style="green")
            table.add_row("Cancelled", str(orders.get('cancelled_orders', 0)), style="dim")
            table.add_row("Active", str(orders.get('active_orders', 0)), style="cyan")

        except Exception as e:
            table.add_row("Error", str(e), style="red")

        return table

    def render_metrics(self) -> Panel:
        """Render performance metrics"""
        try:
            summary = self.session.get_summary()
            portfolio = summary['portfolio']

            nav = portfolio['final_nav']
            total_return = portfolio['total_return']
            cash = portfolio['cash']

            # Color based on return
            return_color = "green" if total_return >= 0 else "red"

            metrics_text = Text()
            metrics_text.append("NAV: ", style="bold")
            metrics_text.append(f"{nav:,.2f} VND\n", style="white")

            metrics_text.append("Return: ", style="bold")
            metrics_text.append(f"{total_return:+.2f}%\n", style=return_color)

            metrics_text.append("Cash: ", style="bold")
            metrics_text.append(f"{cash:,.2f} VND\n", style="white")

            # Session duration
            if 'session' in summary:
                duration = summary['session'].get('duration_seconds', 0)
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                metrics_text.append("Duration: ", style="bold")
                metrics_text.append(f"{minutes}m {seconds}s\n", style="cyan")

            return Panel(metrics_text, title="📈 Performance", border_style="green")

        except Exception as e:
            return Panel(f"Error: {e}", title="📈 Performance", border_style="red")

    def render_redis(self) -> Panel:
        """Render Redis statistics"""
        try:
            summary = self.session.get_summary()
            redis_stats = summary.get('redis', {})

            redis_text = Text()
            redis_text.append("Status: ", style="bold")

            is_running = redis_stats.get('is_running', False)
            status_text = "Running ✓" if is_running else "Stopped ✗"
            status_color = "green" if is_running else "red"
            redis_text.append(f"{status_text}\n", style=status_color)

            redis_text.append("Messages: ", style="bold")
            processed = redis_stats.get('messages_processed', 0)
            redis_text.append(f"{processed:,}\n", style="cyan")

            redis_text.append("Received: ", style="bold")
            received = redis_stats.get('messages_received', 0)
            redis_text.append(f"{received:,}\n", style="white")

            redis_text.append("Failed: ", style="bold")
            failed = redis_stats.get('messages_failed', 0)
            failed_color = "red" if failed > 0 else "green"
            redis_text.append(f"{failed}\n", style=failed_color)

            # Reconnects
            reconnects = redis_stats.get('reconnect_count', 0)
            if reconnects > 0:
                redis_text.append("Reconnects: ", style="bold")
                redis_text.append(f"{reconnects}\n", style="yellow")

            return Panel(redis_text, title="📡 Redis", border_style="blue")

        except Exception as e:
            return Panel(f"Error: {e}", title="📡 Redis", border_style="red")

    def render_footer(self) -> Panel:
        """Render footer panel"""
        footer_text = Text()
        footer_text.append("Press ", style="dim")
        footer_text.append("Ctrl+C", style="bold yellow")
        footer_text.append(" to stop | ", style="dim")

        # Health status
        try:
            is_healthy = self.session.is_healthy()
            if is_healthy:
                footer_text.append("System: ", style="dim")
                footer_text.append("Healthy ✓", style="green")
            else:
                footer_text.append("System: ", style="dim")
                footer_text.append("Unhealthy ✗", style="red")
        except:
            footer_text.append("System: Unknown", style="dim")

        return Panel(footer_text, style="dim")

    def update_layout(self, layout: Layout):
        """Update all sections of the layout"""
        try:
            layout["header"].update(self.render_header())
            layout["positions"].update(self.render_positions())
            layout["orders"].update(self.render_orders())
            layout["metrics"].update(self.render_metrics())
            layout["redis"].update(self.render_redis())
            layout["footer"].update(self.render_footer())
        except Exception as e:
            self.logger.error(f"Error updating layout: {e}")

    def start(self, refresh_rate: float = 1.0):
        """
        Start live dashboard

        Args:
            refresh_rate: Refresh rate in Hz (updates per second)
        """
        self.logger.info(f"Starting dashboard with refresh rate {refresh_rate} Hz")
        self.running = True

        try:
            with Live(self.generate_layout(), refresh_per_second=refresh_rate, console=self.console) as live:
                while self.running and self.session.running:
                    layout = self.generate_layout()
                    self.update_layout(layout)
                    live.update(layout)
                    time.sleep(1.0 / refresh_rate)

        except KeyboardInterrupt:
            self.logger.info("Dashboard stopped by user")
        finally:
            self.running = False

    def stop(self):
        """Stop dashboard"""
        self.running = False

    def print_summary(self):
        """Print final summary (non-live)"""
        self.console.print("\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]")
        self.console.print("[bold cyan]                 SESSION SUMMARY                        [/bold cyan]")
        self.console.print("[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n")

        try:
            summary = self.session.get_summary()

            # Portfolio summary
            portfolio = summary['portfolio']
            self.console.print(f"[bold]Initial Capital:[/bold] {portfolio['initial_capital']:,.2f} VND")
            self.console.print(f"[bold]Final NAV:[/bold] {portfolio['final_nav']:,.2f} VND")

            total_return = portfolio['total_return']
            return_color = "green" if total_return >= 0 else "red"
            self.console.print(f"[bold]Total Return:[/bold] [{return_color}]{total_return:+.2f}%[/{return_color}]")

            # Orders
            orders = summary['orders']
            self.console.print(f"\n[bold]Orders:[/bold]")
            self.console.print(f"  Total: {orders.get('total_orders', 0)}")
            self.console.print(f"  Filled: {orders.get('filled_orders', 0)}")

            # Redis stats
            redis_stats = summary.get('redis', {})
            self.console.print(f"\n[bold]Redis Messages:[/bold]")
            self.console.print(f"  Processed: {redis_stats.get('messages_processed', 0):,}")
            self.console.print(f"  Failed: {redis_stats.get('messages_failed', 0)}")

        except Exception as e:
            self.console.print(f"[red]Error generating summary: {e}[/red]")

        self.console.print("\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n")
