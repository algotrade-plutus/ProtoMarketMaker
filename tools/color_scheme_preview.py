"""
Color Scheme Preview for Flashy Logger

Displays all color scheme options with actual rendered colors
so you can choose the best one visually.

Usage:
    python tools/color_scheme_preview.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED, HEAVY

console = Console()

# Define all color schemes
color_schemes = {
    "Current (Original)": {
        "SIGNAL_COLOR": "bold cyan",
        "BID_COLOR": "bold green",
        "ASK_COLOR": "bold red",
        "PROFIT_COLOR": "bright_green",
        "LOSS_COLOR": "bright_red",
        "SECTION_COLOR": "bold cyan",
        "TABLE_BORDER": "cyan",
        "PANEL_BORDER": "bold magenta",
    },
    "Option 1: Monochrome Professional (Bloomberg Style)": {
        "SIGNAL_COLOR": "bold white",
        "BID_COLOR": "bold blue",
        "ASK_COLOR": "bold yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "blue",
        "PANEL_BORDER": "bold blue",
    },
    "Option 2: Matrix Tech (Cyberpunk Style)": {
        "SIGNAL_COLOR": "bold bright_cyan",
        "BID_COLOR": "bold cyan",
        "ASK_COLOR": "bold magenta",
        "PROFIT_COLOR": "bright_green",
        "LOSS_COLOR": "bright_magenta",
        "SECTION_COLOR": "bold bright_cyan",
        "TABLE_BORDER": "cyan",
        "PANEL_BORDER": "bold magenta",
    },
    "Option 3: Dark Mode Finance (Modern Trading App)": {
        "SIGNAL_COLOR": "bold bright_white",
        "BID_COLOR": "bold bright_blue",
        "ASK_COLOR": "bold bright_yellow",
        "PROFIT_COLOR": "bright_green",
        "LOSS_COLOR": "bright_red",
        "SECTION_COLOR": "bold bright_white",
        "TABLE_BORDER": "bright_blue",
        "PANEL_BORDER": "bold bright_yellow",
    },
    "Option 4: Minimalist Gray (Professional Dashboard)": {
        "SIGNAL_COLOR": "bold white",
        "BID_COLOR": "bold cyan",
        "ASK_COLOR": "bold yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "cyan",
        "PANEL_BORDER": "bold yellow",
    },
    "Option 5: Solarized Professional (Developer-Friendly)": {
        "SIGNAL_COLOR": "bold blue",
        "BID_COLOR": "bold cyan",
        "ASK_COLOR": "bold yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold cyan",
        "TABLE_BORDER": "cyan",
        "PANEL_BORDER": "bold blue",
    },
    "Option 6: Financial Terminal (Traditional Finance)": {
        "SIGNAL_COLOR": "bold white",
        "BID_COLOR": "bold green",
        "ASK_COLOR": "bold yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "green",
        "PANEL_BORDER": "bold green",
    },
    "Option 7: Darcula (IntelliJ Dark Theme)": {
        "SIGNAL_COLOR": "white",
        "BID_COLOR": "cyan",
        "ASK_COLOR": "yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "bright_black",
        "PANEL_BORDER": "bright_black",
    },
    "Option 8: VS Code Dark": {
        "SIGNAL_COLOR": "bright_white",
        "BID_COLOR": "blue",
        "ASK_COLOR": "yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bright_white",
        "TABLE_BORDER": "white",
        "PANEL_BORDER": "white",
    },
    "Option 9: GitHub Dark": {
        "SIGNAL_COLOR": "white",
        "BID_COLOR": "blue",
        "ASK_COLOR": "yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "bright_black",
        "PANEL_BORDER": "blue",
    },
    "Option 10: Clean Professional (Recommended)": {
        "SIGNAL_COLOR": "white",
        "BID_COLOR": "cyan",
        "ASK_COLOR": "yellow",
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "bright_black",
        "PANEL_BORDER": "bright_black",
        "ORDERS_BORDER": "bright_black",  # Muted orders table
        "USE_EMOJI": False,  # No emoji for BID/ASK
    },
    "Option 11: Custom (BID=Red, ASK=Green)": {
        "SIGNAL_COLOR": "white",
        "BID_COLOR": "red",  # Dark red for BID and SHORT
        "ASK_COLOR": "green",  # Dark green for ASK and LONG
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "bright_black",
        "PANEL_BORDER": "bright_black",
        "ORDERS_BORDER": "bright_black",
        "SPREAD_COLOR": "cyan",  # Cyan for spread indicator
        "USE_EMOJI": False,
    },
    "Option 12: Custom No Emoji (BID=Red, ASK=Green)": {
        "SIGNAL_COLOR": "white",
        "BID_COLOR": "red",  # Dark red for BID and SHORT
        "ASK_COLOR": "green",  # Dark green for ASK and LONG
        "PROFIT_COLOR": "green",
        "LOSS_COLOR": "red",
        "SECTION_COLOR": "bold white",
        "TABLE_BORDER": "bright_black",
        "PANEL_BORDER": "bright_black",
        "ORDERS_BORDER": "bright_black",
        "SPREAD_COLOR": "cyan",  # Cyan for spread indicator
        "USE_EMOJI": False,
        "NO_EMOJI_HEADERS": True,  # Remove ALL emojis including section headers
    },
}

def show_scheme(name: str, colors: dict):
    """Display a color scheme with actual colors"""
    console.print(f"\n{'=' * 100}")
    console.print(f"[bold white]{name}[/bold white]")
    console.print(f"{'=' * 100}\n")

    # Check if all emojis should be removed
    no_emoji_headers = colors.get("NO_EMOJI_HEADERS", False)

    # 1. SIGNAL CHANGE Section
    console.print("=" * 100)
    signal_header = "SIGNAL CHANGE | VN30F1M" if no_emoji_headers else "📡 SIGNAL CHANGE | VN30F1M"
    console.print(f"[{colors['SECTION_COLOR']}]{signal_header}[/{colors['SECTION_COLOR']}]")

    text = Text()
    text.append("   Reason:                  ", style="bold")
    text.append("ORDER_FILLED", style=colors["SIGNAL_COLOR"])
    console.print(text)

    text = Text()
    text.append("   Market Price:            ", style="bold")
    text.append("1542.0")
    console.print(text)

    # Check if emojis should be used
    use_emoji = colors.get("USE_EMOJI", True)
    bid_prefix = "🟢 " if use_emoji else ""
    ask_prefix = "🔴 " if use_emoji else ""

    text = Text()
    text.append("   New Orders:              ", style="bold")
    text.append(f"{bid_prefix}BID 1539.0", style=colors["BID_COLOR"])
    text.append(" | ")
    text.append(f"{ask_prefix}ASK 1545.0", style=colors["ASK_COLOR"])
    text.append(" | ")
    spread_color = colors.get("SPREAD_COLOR", "white")
    text.append("Spread: 6.0 pts", style=spread_color)
    console.print(text)

    text = Text()
    text.append("   Current Inventory:       ", style="bold")
    # SHORT uses BID_COLOR (red), LONG uses ASK_COLOR (green)
    inventory_color = colors["BID_COLOR"]  # -2 is SHORT, so use BID color (red)
    inventory_prefix = bid_prefix if use_emoji else ""  # SHORT uses BID emoji/prefix
    text.append(f"{inventory_prefix}-2 (SHORT)", style=inventory_color)
    console.print(text)

    console.print()

    # 2. POSITION STATUS TABLE
    position_table_title = "POSITION STATUS | VN30F1M" if no_emoji_headers else "📊 POSITION STATUS | VN30F1M"
    table = Table(
        title=position_table_title,
        title_justify="left",
        border_style=colors["TABLE_BORDER"],
        box=ROUNDED,
        show_header=True,
        header_style=f"bold {colors['TABLE_BORDER']}"
    )

    table.add_column("Inventory", justify="right", style="bold")
    table.add_column("Entry Prices", justify="left")
    table.add_column("Market Price", justify="right")
    table.add_column("Unrealized PnL", justify="right")

    pnl_str = f"[{colors['PROFIT_COLOR']}]+3.70 pts | +370 (k) VND[/{colors['PROFIT_COLOR']}]"
    inventory_indicator = "-2" if no_emoji_headers else "🔴 -2"
    table.add_row(
        inventory_indicator,
        "1545.7 (+3.70pts), 1545.4 (+3.40pts)",
        "1542.0",
        pnl_str
    )

    console.print(table)

    # 3. PENDING ORDERS TABLE
    orders_border = colors.get("ORDERS_BORDER", "yellow")
    orders_table_title = "PENDING ORDERS (2)" if no_emoji_headers else "📋 PENDING ORDERS (2)"
    orders_table = Table(
        title=orders_table_title,
        title_justify="left",
        border_style=orders_border,
        box=ROUNDED,
        show_header=True,
        header_style=f"bold {orders_border}"
    )

    orders_table.add_column("Side", justify="left")
    orders_table.add_column("Qty", justify="right")
    orders_table.add_column("Price", justify="right")
    orders_table.add_column("Status", justify="left")

    bid_str = f"[{colors['BID_COLOR']}]{bid_prefix}BID[/{colors['BID_COLOR']}]"
    ask_str = f"[{colors['ASK_COLOR']}]{ask_prefix}ASK[/{colors['ASK_COLOR']}]"

    orders_table.add_row(bid_str, "1", "1539.0", "SUBMITTED")
    orders_table.add_row(ask_str, "1", "1545.0", "SUBMITTED")

    console.print(orders_table)
    console.print("=" * 100)

    console.print()

    # 4. POSITION CLOSURE PANEL
    content = Text()
    content.append("Fill:         ", style="bold")
    content.append(f"{bid_prefix}BID 1 @ 1540.0\n", style=colors["BID_COLOR"])
    content.append("Position:     -1 → FLAT\n")
    content.append("Closed PnL:   ", style="bold")
    pnl_emoji = "" if no_emoji_headers else " 💚"
    content.append(f"+3.30 pts (+0.21%){pnl_emoji}\n", style=colors["PROFIT_COLOR"])
    content.append("\n")

    cumulative_header = "CUMULATIVE PERFORMANCE:\n" if no_emoji_headers else "📈 CUMULATIVE PERFORMANCE:\n"
    content.append(cumulative_header, style=colors["SECTION_COLOR"])
    content.append("   Total Realized (Gross):  +4.50 pts\n")
    content.append("   Total Realized (Net):    +3.30 pts\n")
    content.append("   Closed Trades:           3\n")
    content.append("   Avg PnL/Trade:           +1.10 pts | +0.18%\n")
    content.append("\n")

    portfolio_header = "PORTFOLIO STATUS:\n" if no_emoji_headers else "💼 PORTFOLIO STATUS:\n"
    content.append(portfolio_header, style=colors["SECTION_COLOR"])
    content.append("   Realized PnL:           ")
    content.append("+3.30 pts | +330 (k) VND\n", style=colors["PROFIT_COLOR"])
    content.append("   Unrealized PnL:         ")
    content.append("+0.00 pts | +0 (k) VND\n", style=colors["PROFIT_COLOR"])
    content.append("   Current NAV:            500,330 (k) VND\n")
    content.append("   Portfolio PnL:          ")
    content.append("+330 (k) VND (+0.07%)", style=colors["PROFIT_COLOR"])
    content.append(" | Total Fee: 120 (k) VND")

    panel_title = "POSITION CLOSED | VN30F1M" if no_emoji_headers else "💰 POSITION CLOSED | VN30F1M"
    panel = Panel(
        content,
        title=panel_title,
        border_style=colors["PANEL_BORDER"],
        box=HEAVY,
        expand=False
    )
    console.print(panel)
    console.print()


# Main execution
console.print("\n")
console.print("[bold bright_white]" + "=" * 100 + "[/bold bright_white]")
console.print("[bold bright_white]                    COLOR SCHEME PREVIEW - FLASHY LOGGER[/bold bright_white]")
console.print("[bold bright_white]" + "=" * 100 + "[/bold bright_white]")

for name, colors in color_schemes.items():
    show_scheme(name, colors)

console.print("\n" + "=" * 100)
console.print("[bold white]Which color scheme do you prefer? (Current, Option 1-12)[/bold white]")
console.print("[dim]Options 7-9: IDE-inspired themes (Darcula, VS Code, GitHub)[/dim]")
console.print("[dim]Option 10: Clean Professional - muted borders, no BID/ASK emojis[/dim]")
console.print("[dim]Option 11: Custom (BID=Red, ASK=Green) - no BID/ASK emojis[/dim]")
console.print("[dim]Option 12: Custom No Emoji (BID=Red, ASK=Green) - NO emojis anywhere[/dim]")
console.print("=" * 100 + "\n")
