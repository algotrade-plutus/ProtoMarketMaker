"""
Flashy Logger for Paper Trading Demo

Uses Rich library to create visually appealing, colorful terminal output for demos.
Provides panels, tables, and color-coded logging for trading events.

Date: November 20, 2025
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED, HEAVY
from decimal import Decimal
from typing import Optional, List
from datetime import datetime


class FlashyLogger:
    """
    Flashy logger for paper trading demo

    Uses Rich library for colorful, visually appealing terminal output.
    Provides color-coded fills, Rich panels for closures, and Rich tables for status.

    Example:
        flashy = FlashyLogger()
        flashy.log_fill(side="BID", qty=1, price=Decimal('1540.0'))
        flashy.log_position_closure(...all params...)
    """

    # Color Scheme Constants - Option 12: Custom No Emoji (BID=Red, ASK=Green)
    # BID (red) represents buying/covering short, SHORT positions (negative inventory)
    # ASK (green) represents selling/opening short, LONG positions (positive inventory)
    SIGNAL_COLOR = "white"
    BID_COLOR = "red"  # Dark red for BID orders and SHORT positions
    ASK_COLOR = "green"  # Dark green for ASK orders and LONG positions
    PROFIT_COLOR = "green"
    LOSS_COLOR = "red"
    SECTION_COLOR = "bold white"
    TABLE_BORDER_COLOR = "bright_black"  # Muted gray borders
    PANEL_BORDER_COLOR = "bright_black"  # Muted gray borders
    ORDERS_BORDER_COLOR = "bright_black"  # Muted gray borders for pending orders
    SPREAD_COLOR = "cyan"  # Cyan for spread indicator
    ROLLOVER_COLOR = "bold orange1"  # Keep for potential future use
    NEUTRAL_COLOR = "white"

    # No emojis in Option 12

    def __init__(self):
        """Initialize FlashyLogger with Rich Console"""
        self.console = Console()

    def log_signal(
        self,
        signal_num: int,
        timestamp: datetime,
        market_price: Decimal,
        bid: Decimal,
        ask: Decimal,
        inventory: int,
        contract: str
    ):
        """
        Log SIGNAL event with color coding (simple one-line format)

        Args:
            signal_num: Signal sequence number
            timestamp: Signal timestamp
            market_price: Current market price
            bid: Bid price from strategy
            ask: Ask price from strategy
            inventory: Current inventory
            contract: Contract symbol
        """
        text = Text()
        text.append(f"[SIGNAL] #{signal_num}", style=self.SIGNAL_COLOR)
        text.append(f" | time={timestamp} | market={float(market_price):.1f} | ")
        text.append(f"bid={float(bid):.1f} | ask={float(ask):.1f} | inv={inventory:+d} | {contract}")

        self.console.print(text)

    def log_signal_change(
        self,
        contract: str,
        timestamp: datetime,
        reason: str,
        market_price: Decimal,
        bid_price: Decimal,
        ask_price: Decimal,
        spread: Decimal,
        inventory: int
    ):
        """
        Log SIGNAL CHANGE event with structured format

        Args:
            contract: Contract symbol
            timestamp: Signal timestamp
            reason: Signal trigger reason (TIME_ELAPSED, ORDER_FILLED, etc.)
            market_price: Current market price
            bid_price: New bid price from strategy
            ask_price: New ask price from strategy
            spread: Bid-ask spread
            inventory: Current inventory position
        """
        self.print_separator()
        self.console.print(f"[{self.SECTION_COLOR}]SIGNAL CHANGE | {contract}[/{self.SECTION_COLOR}]")

        text = Text()
        text.append("   Reason:                  ", style="bold")
        # Color-code reason: yellow for TIME_ELAPSED, cyan for ORDER_FILLED
        reason_color = "yellow" if reason == "TIME_ELAPSED" else "cyan"
        text.append(f"{reason}", style=reason_color)
        self.console.print(text)

        text = Text()
        text.append("   Time:                    ", style="bold")
        text.append(f"{timestamp}")
        self.console.print(text)

        text = Text()
        text.append("   Market Price:            ", style="bold")
        # Highlight market price with white bold
        text.append(f"{float(market_price):.1f}", style="bold white")
        self.console.print(text)

        text = Text()
        text.append("   New Orders:              ", style="bold")
        text.append(f"BID {float(bid_price):.1f}", style=self.BID_COLOR)
        text.append(" | ")
        text.append(f"ASK {float(ask_price):.1f}", style=self.ASK_COLOR)
        text.append(" | ")
        text.append(f"Spread: {float(spread):.1f} pts", style=self.SPREAD_COLOR)
        self.console.print(text)

        text = Text()
        text.append("   Current Inventory:       ", style="bold")
        if inventory > 0:
            # LONG position uses ASK_COLOR (green)
            text.append(f"{inventory:+d} (LONG)", style=self.ASK_COLOR)
        elif inventory < 0:
            # SHORT position uses BID_COLOR (red)
            text.append(f"{inventory:+d} (SHORT)", style=self.BID_COLOR)
        else:
            text.append(f"FLAT (0)", style="dim")
        self.console.print(text)

        self.console.print()

    def log_fill(
        self,
        side: str,
        qty: int,
        price: Decimal,
        realized_pnl_pts: Optional[Decimal] = None,
        realized_pnl_vnd: Optional[Decimal] = None
    ):
        """
        Log FILL event with color coding (red for BID, green for ASK)

        Args:
            side: "BID" or "ASK"
            qty: Quantity filled
            price: Fill price
            realized_pnl_pts: Realized PnL in points (if closing position)
            realized_pnl_vnd: Realized PnL in VND (if closing position)
        """
        text = Text()
        text.append("   Fill:                    ", style="bold")

        # Color-code by side (no emojis)
        side_color = self.BID_COLOR if side == "BID" else self.ASK_COLOR
        text.append(f"{side} {qty} @ {float(price):.1f}", style=side_color)

        # Add realized PnL if provided (position closure)
        if realized_pnl_pts is not None and realized_pnl_vnd is not None:
            pnl_color = self.PROFIT_COLOR if realized_pnl_pts > 0 else self.LOSS_COLOR
            text.append(" | Realized PnL: ")
            text.append(
                f"{float(realized_pnl_pts):+.2f} pts | {float(realized_pnl_vnd):+,.0f} (k) VND",
                style=pnl_color
            )

        self.console.print(text)

    def log_position_before_after(
        self,
        inv_before: int,
        inv_after: int,
        position_before_detail: str,
        position_after_detail: str
    ):
        """
        Log position before/after with color-coded entries

        Args:
            inv_before: Inventory before fill
            inv_after: Inventory after fill
            position_before_detail: Position detail string (e.g., "[(1544.2, LONG, -0.40pts)]")
            position_after_detail: Position detail string after fill
        """
        import re

        def colorize_position_detail(detail_str: str, inventory: int) -> Text:
            """Parse and colorize position detail string"""
            text = Text()

            # Parse entries: [(price, side, pnl_pts), ...]
            entries = re.findall(r'\(([\d.]+),\s*(\w+),\s*([-+][\d.]+)pts\)', detail_str)

            if not entries:
                # Empty position (FLAT)
                text.append(detail_str)
                return text

            text.append("[")
            for i, (price, side, pnl) in enumerate(entries):
                if i > 0:
                    text.append(", ")

                # Color the entry based on PnL
                pnl_val = float(pnl)
                entry_color = self.PROFIT_COLOR if pnl_val >= 0 else self.LOSS_COLOR

                text.append(f"({price}, {side}, {pnl}pts)", style=entry_color)

            text.append("]")
            return text

        # Position Before
        text = Text()
        text.append("   Position Before (", style="bold")
        # Color inventory based on position direction (convert to int for format)
        inv_before_int = int(inv_before)
        if inv_before_int > 0:
            text.append(f"{inv_before_int:+d}", style=self.ASK_COLOR)  # LONG = green
        elif inv_before_int < 0:
            text.append(f"{inv_before_int:+d}", style=self.BID_COLOR)  # SHORT = red
        else:
            text.append(f"{inv_before_int:+d}", style="dim")  # FLAT
        text.append("):    ", style="bold")
        text.append_text(colorize_position_detail(position_before_detail, inv_before))
        self.console.print(text)

        # Position After
        text = Text()
        text.append("   Position After (", style="bold")
        # Color inventory based on position direction (convert to int for format)
        inv_after_int = int(inv_after)
        if inv_after_int > 0:
            text.append(f"{inv_after_int:+d}", style=self.ASK_COLOR)  # LONG = green
        elif inv_after_int < 0:
            text.append(f"{inv_after_int:+d}", style=self.BID_COLOR)  # SHORT = red
        else:
            text.append(f"{inv_after_int:+d}", style="dim")  # FLAT
        text.append("):     ", style="bold")
        text.append_text(colorize_position_detail(position_after_detail, inv_after))
        self.console.print(text)

    def log_position_closure(
        self,
        contract: str,
        side: str,
        qty: int,
        price: Decimal,
        inv_before: int,
        inv_after: int,
        closed_pnl_pts: Decimal,
        closed_pnl_pct: Decimal,
        total_realized_gross_pts: Decimal,
        total_realized_pts: Decimal,
        closed_trades: int,
        avg_pnl_pts: Decimal,
        avg_pnl_pct: Decimal,
        current_nav: Decimal,
        portfolio_pnl: Decimal,
        portfolio_pnl_pct: Decimal,
        total_fees: Decimal,
        realized_pnl_vnd: Decimal,
        realized_pnl_pts: Decimal,
        unrealized_pnl_vnd: Decimal,
        unrealized_pnl_pts: Decimal
    ):
        """
        Log position closure with Rich Panel

        Args:
            contract: Contract symbol
            side: "BID" or "ASK"
            qty: Quantity filled
            price: Fill price
            inv_before: Inventory before this fill
            inv_after: Inventory after this fill
            closed_pnl_pts: Closed position PnL in points
            closed_pnl_pct: Closed position PnL percentage
            total_realized_gross_pts: Cumulative realized PnL in points (before fees)
            total_realized_pts: Cumulative realized PnL in points (after fees, net)
            closed_trades: Total number of closed trades
            avg_pnl_pts: Average PnL per trade in points
            avg_pnl_pct: Average PnL per trade percentage
            current_nav: Current NAV
            portfolio_pnl: Total portfolio PnL
            portfolio_pnl_pct: Portfolio PnL percentage
            total_fees: Total fees paid
            realized_pnl_vnd: Realized PnL in VND
            realized_pnl_pts: Realized PnL in points
            unrealized_pnl_vnd: Unrealized PnL in VND
            unrealized_pnl_pts: Unrealized PnL in points
        """
        # Build content
        content = Text()

        # Fill info with color (no emojis)
        side_color = self.BID_COLOR if side == "BID" else self.ASK_COLOR
        content.append("Fill:         ", style="bold")
        content.append(f"{side} {qty} @ {float(price):.1f}\n", style=side_color)

        # Position change
        if inv_after == 0:
            position_after_str = "FLAT"
        else:
            position_after_str = f"{inv_after:+d}"
        content.append(f"Position:     {inv_before:+d} → {position_after_str}\n")

        # Closed PnL with color (no emoji)
        pnl_color = self.PROFIT_COLOR if closed_pnl_pts > 0 else self.LOSS_COLOR
        content.append("Closed PnL:   ", style="bold")
        content.append(
            f"{float(closed_pnl_pts):+.2f} pts ({float(closed_pnl_pct):+.2f}%)\n",
            style=pnl_color
        )

        content.append("\n")

        # Cumulative performance (no emoji)
        content.append(f"CUMULATIVE PERFORMANCE:\n", style=self.SECTION_COLOR)
        content.append(f"   Total Realized (Gross):  {float(total_realized_gross_pts):+.2f} pts\n")
        content.append(f"   Total Realized (Net):    {float(total_realized_pts):+.2f} pts\n")
        content.append(f"   Closed Trades:           {closed_trades}\n")
        content.append(f"   Avg PnL/Trade:           {float(avg_pnl_pts):+.2f} pts | {float(avg_pnl_pct):+.2f}%\n")

        content.append("\n")

        # Portfolio status (no emoji)
        content.append(f"PORTFOLIO STATUS:\n", style=self.SECTION_COLOR)

        # Realized PnL
        rpnl_color = self.PROFIT_COLOR if realized_pnl_pts > 0 else self.LOSS_COLOR
        content.append("   Realized PnL:           ")
        content.append(
            f"{float(realized_pnl_pts):+.2f} pts | {float(realized_pnl_vnd):+,.0f} (k) VND\n",
            style=rpnl_color
        )

        # Unrealized PnL
        upnl_color = self.PROFIT_COLOR if unrealized_pnl_pts > 0 else self.LOSS_COLOR
        content.append("   Unrealized PnL:         ")
        content.append(
            f"{float(unrealized_pnl_pts):+.2f} pts | {float(unrealized_pnl_vnd):+,.0f} (k) VND\n",
            style=upnl_color
        )

        # NAV
        content.append(f"   Current NAV:            {float(current_nav):,.0f} (k) VND\n")

        # Portfolio PnL
        ppnl_color = self.PROFIT_COLOR if portfolio_pnl > 0 else self.LOSS_COLOR
        content.append("   Portfolio PnL:          ")
        content.append(
            f"{float(portfolio_pnl):+,.0f} (k) VND ({float(portfolio_pnl_pct):+.2f}%) | ",
            style=ppnl_color
        )
        content.append(f"Total Fee: {float(total_fees):,.0f} (k) VND")

        # Create panel with heavy borders for visual impact (no emoji)
        panel = Panel(
            content,
            title=f"POSITION CLOSED | {contract}",
            border_style=self.PANEL_BORDER_COLOR,
            box=HEAVY,
            expand=False
        )

        self.console.print(panel)
        self.console.print()  # Blank line

    def log_position_status(
        self,
        contract: str,
        inventory: int,
        entry_prices: List[Decimal],
        market_price: Decimal,
        unrealized_pnl_pts: Decimal,
        unrealized_pnl_vnd: Decimal,
        active_orders: List
    ):
        """
        Log position status with Rich Table

        Args:
            contract: Contract symbol
            inventory: Current inventory
            entry_prices: List of entry prices (FIFO)
            market_price: Current market price
            unrealized_pnl_pts: Unrealized PnL in points
            unrealized_pnl_vnd: Unrealized PnL in VND
            active_orders: List of active orders
        """
        # Position status table (no emoji)
        table = Table(
            title=f"POSITION STATUS | {contract}",
            title_justify="left",
            border_style=self.TABLE_BORDER_COLOR,
            box=ROUNDED,
            show_header=True,
            header_style=f"bold {self.TABLE_BORDER_COLOR}"
        )

        if inventory != 0:
            # Add columns
            table.add_column("Inventory", justify="right", style="bold")
            table.add_column("Entry Prices", justify="left")
            table.add_column("Market Price", justify="right")
            table.add_column("Unrealized PnL", justify="right")

            # Format entry prices with individual PnLs (color-coded)
            side = "LONG" if inventory > 0 else "SHORT"

            # Get individual PnLs with colors
            individual_pnls = []
            for entry in entry_prices:
                if inventory > 0:
                    pnl_pts = market_price - entry
                else:
                    pnl_pts = entry - market_price

                # Color each entry based on its PnL
                pnl_color = self.PROFIT_COLOR if pnl_pts >= 0 else self.LOSS_COLOR
                individual_pnls.append(f"[{pnl_color}]{float(entry):.1f} ({float(pnl_pts):+.2f}pts)[/{pnl_color}]")

            entry_prices_str = ", ".join(individual_pnls)

            # Color-code unrealized PnL
            pnl_color = self.PROFIT_COLOR if unrealized_pnl_pts >= 0 else self.LOSS_COLOR
            pnl_str = (
                f"[{pnl_color}]{float(unrealized_pnl_pts):+.2f} pts | "
                f"{float(unrealized_pnl_vnd):+,.0f} (k) VND[/{pnl_color}]"
            )

            # Color-code inventory: SHORT=red, LONG=green
            inv_color = self.ASK_COLOR if inventory > 0 else self.BID_COLOR  # LONG=green, SHORT=red
            inventory_str = f"[{inv_color}]{inventory:+d}[/{inv_color}]"

            table.add_row(
                inventory_str,
                entry_prices_str,
                f"{float(market_price):.1f}",
                pnl_str
            )
        else:
            # FLAT position
            table.add_column("Status", justify="center", style="dim")
            table.add_row("FLAT (0 contracts)")

        self.console.print(table)

        # Pending orders table (no emoji)
        if active_orders:
            orders_table = Table(
                title=f"PENDING ORDERS ({len(active_orders)})",
                title_justify="left",
                border_style=self.ORDERS_BORDER_COLOR,
                box=ROUNDED,
                show_header=True,
                header_style=f"bold {self.ORDERS_BORDER_COLOR}"
            )

            orders_table.add_column("Side", justify="left")
            orders_table.add_column("Qty", justify="right")
            orders_table.add_column("Price", justify="right")
            orders_table.add_column("Status", justify="left")

            for order in active_orders:
                side_color = self.BID_COLOR if order.side.value == "BID" else self.ASK_COLOR
                side_str = f"[{side_color}]{order.side.value}[/{side_color}]"

                orders_table.add_row(
                    side_str,
                    str(order.quantity),
                    f"{float(order.price):.1f}",
                    order.status.value
                )

            self.console.print(orders_table)
        else:
            self.console.print(f"[dim]PENDING ORDERS:    None[/dim]")

        self.print_separator()  # Separator to match the one before SIGNAL CHANGE

    def log_portfolio_status(
        self,
        realized_pnl_pts: Decimal,
        realized_pnl_vnd: Decimal,
        unrealized_pnl_pts: Decimal,
        unrealized_pnl_vnd: Decimal,
        current_nav: Decimal,
        portfolio_pnl: Decimal,
        portfolio_pnl_pct: Decimal,
        total_fees: Decimal
    ):
        """
        Log portfolio status with formatted PnL breakdown

        Args:
            realized_pnl_pts: Realized PnL in points
            realized_pnl_vnd: Realized PnL in VND
            unrealized_pnl_pts: Unrealized PnL in points
            unrealized_pnl_vnd: Unrealized PnL in VND
            current_nav: Current NAV
            portfolio_pnl: Total portfolio PnL
            portfolio_pnl_pct: Portfolio PnL percentage
            total_fees: Total fees paid
        """
        self.console.print()
        self.console.print(f"[{self.SECTION_COLOR}]PORTFOLIO STATUS:[/{self.SECTION_COLOR}]")

        # Realized PnL
        rpnl_color = self.PROFIT_COLOR if realized_pnl_pts > 0 else self.LOSS_COLOR
        text = Text()
        text.append("   Realized PnL:            ")
        text.append(
            f"{float(realized_pnl_pts):+.2f} pts | {float(realized_pnl_vnd):+,.0f} (k) VND",
            style=rpnl_color
        )
        self.console.print(text)

        # Unrealized PnL
        upnl_color = self.PROFIT_COLOR if unrealized_pnl_pts > 0 else self.LOSS_COLOR
        text = Text()
        text.append("   Unrealized PnL:          ")
        text.append(
            f"{float(unrealized_pnl_pts):+.2f} pts | {float(unrealized_pnl_vnd):+,.0f} (k) VND",
            style=upnl_color
        )
        self.console.print(text)

        # NAV
        text = Text()
        text.append("   Current NAV:             ")
        text.append(f"{float(current_nav):,.0f} (k) VND", style=self.NEUTRAL_COLOR)
        self.console.print(text)

        # Portfolio PnL
        ppnl_color = self.PROFIT_COLOR if portfolio_pnl > 0 else self.LOSS_COLOR
        text = Text()
        text.append("   Portfolio PnL:           ")
        text.append(
            f"{float(portfolio_pnl):+,.0f} (k) VND ({float(portfolio_pnl_pct):+.2f}%)",
            style=ppnl_color
        )
        text.append(f" | Total Fee: {float(total_fees):,.0f} (k) VND")
        self.console.print(text)

        self.console.print("=" * 80 + "\n")

    def print_separator(self):
        """Print a visual separator"""
        self.console.print("=" * 80)

    def print_blank_line(self):
        """Print a blank line"""
        self.console.print()
