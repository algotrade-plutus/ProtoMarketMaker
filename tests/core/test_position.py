"""
Unit tests for Position class
"""
import pytest
from decimal import Decimal
from protomarketmaker.core.position import Position


class TestPosition:
    """Test Position functionality"""

    def test_position_creation(self):
        pos = Position(
            contract="VN30F1M",
            quantity=0,
            average_price=Decimal("0")
        )
        assert pos.contract == "VN30F1M"
        assert pos.quantity == 0
        assert pos.is_flat() is True

    def test_long_position_unrealized_pnl(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0")
        )
        pos.update_unrealized_pnl(Decimal("1260.0"))
        # (1260 - 1250) * 2 * 100 = 2000
        assert pos.unrealized_pnl == Decimal("2000")

    def test_short_position_unrealized_pnl(self):
        pos = Position(
            contract="VN30F1M",
            quantity=-2,
            average_price=Decimal("1250.0")
        )
        pos.update_unrealized_pnl(Decimal("1240.0"))
        # (1250 - 1240) * 2 * 100 = 2000
        assert pos.unrealized_pnl == Decimal("2000")

    def test_flat_position_unrealized_pnl(self):
        pos = Position(
            contract="VN30F1M",
            quantity=0,
            average_price=Decimal("1250.0")
        )
        pos.update_unrealized_pnl(Decimal("1260.0"))
        assert pos.unrealized_pnl == Decimal("0")

    def test_long_position_losing_money(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0")
        )
        pos.update_unrealized_pnl(Decimal("1240.0"))
        # (1240 - 1250) * 2 * 100 = -2000
        assert pos.unrealized_pnl == Decimal("-2000")

    def test_short_position_losing_money(self):
        pos = Position(
            contract="VN30F1M",
            quantity=-2,
            average_price=Decimal("1250.0")
        )
        pos.update_unrealized_pnl(Decimal("1260.0"))
        # (1250 - 1260) * 2 * 100 = -2000
        assert pos.unrealized_pnl == Decimal("-2000")

    def test_total_pnl(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0"),
            realized_pnl=Decimal("1000"),
            total_fees=Decimal("40")  # tracked for reporting only
        )
        pos.update_unrealized_pnl(Decimal("1260.0"))
        # realized + unrealized = 1000 + 2000 = 3000
        # Note: fees are already deducted in realized_pnl, total_fees is for reporting only
        assert pos.total_pnl() == Decimal("3000")

    def test_total_pnl_with_losses(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0"),
            realized_pnl=Decimal("-500"),
            total_fees=Decimal("40")  # tracked for reporting only
        )
        pos.update_unrealized_pnl(Decimal("1240.0"))
        # realized + unrealized = -500 + (-2000) = -2500
        # Note: fees are already deducted in realized_pnl, total_fees is for reporting only
        assert pos.total_pnl() == Decimal("-2500")

    def test_position_helpers(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0")
        )
        assert pos.is_long() is True
        assert pos.is_short() is False
        assert pos.is_flat() is False

    def test_short_position_helpers(self):
        pos = Position(
            contract="VN30F1M",
            quantity=-2,
            average_price=Decimal("1250.0")
        )
        assert pos.is_long() is False
        assert pos.is_short() is True
        assert pos.is_flat() is False

    def test_flat_position_helpers(self):
        pos = Position(
            contract="VN30F1M",
            quantity=0,
            average_price=Decimal("1250.0")
        )
        assert pos.is_long() is False
        assert pos.is_short() is False
        assert pos.is_flat() is True

    def test_get_market_value(self):
        pos = Position(
            contract="VN30F1M",
            quantity=3,
            average_price=Decimal("1250.0")
        )
        market_value = pos.get_market_value(Decimal("1260.0"))
        # 3 * 1260 * 100 = 378000
        assert market_value == Decimal("378000")

    def test_get_market_value_short_position(self):
        pos = Position(
            contract="VN30F1M",
            quantity=-3,
            average_price=Decimal("1250.0")
        )
        market_value = pos.get_market_value(Decimal("1260.0"))
        # abs(-3) * 1260 * 100 = 378000
        assert market_value == Decimal("378000")

    def test_position_str_representation(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0")
        )
        str_repr = str(pos)
        assert "VN30F1M" in str_repr
        assert "qty=2" in str_repr


class TestPositionIndividualContracts:
    """Test individual contract tracking (FIFO)"""

    def test_add_contracts_single(self):
        """Test adding a single contract"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)

        assert len(pos.entry_prices) == 1
        assert pos.entry_prices[0] == Decimal("1540.9")

    def test_add_contracts_multiple(self):
        """Test adding multiple contracts at once"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 3)

        assert len(pos.entry_prices) == 3
        assert all(price == Decimal("1540.9") for price in pos.entry_prices)

    def test_add_contracts_different_prices(self):
        """Test adding contracts at different prices"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.add_contracts(Decimal("1543.0"), 1)
        pos.add_contracts(Decimal("1543.7"), 1)

        assert len(pos.entry_prices) == 3
        assert pos.entry_prices == [
            Decimal("1540.9"),
            Decimal("1543.0"),
            Decimal("1543.7")
        ]

    def test_remove_contracts_fifo_order(self):
        """Test FIFO (First In First Out) order for removing contracts"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.add_contracts(Decimal("1543.0"), 1)
        pos.add_contracts(Decimal("1543.7"), 1)

        # Remove 1 contract - should remove oldest (1540.9)
        removed = pos.remove_contracts(1)

        # Returns list of (entry_price, opening_fee) tuples
        assert removed == [(Decimal("1540.9"), Decimal("20"))]
        assert pos.entry_prices == [Decimal("1543.0"), Decimal("1543.7")]

    def test_remove_contracts_multiple(self):
        """Test removing multiple contracts"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.add_contracts(Decimal("1543.0"), 1)
        pos.add_contracts(Decimal("1543.7"), 1)

        # Remove 2 contracts - should remove 1540.9 and 1543.0 (FIFO)
        removed = pos.remove_contracts(2)

        # Returns list of (entry_price, opening_fee) tuples
        assert removed == [(Decimal("1540.9"), Decimal("20")), (Decimal("1543.0"), Decimal("20"))]
        assert pos.entry_prices == [Decimal("1543.7")]

    def test_remove_contracts_all(self):
        """Test removing all contracts"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 2)

        removed = pos.remove_contracts(2)

        # Returns list of (entry_price, opening_fee) tuples
        assert removed == [(Decimal("1540.9"), Decimal("20")), (Decimal("1540.9"), Decimal("20"))]
        assert pos.entry_prices == []

    def test_remove_contracts_more_than_available(self):
        """Test removing more contracts than available"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 2)

        removed = pos.remove_contracts(5)  # Try to remove 5 but only 2 available

        assert len(removed) == 2  # Should only remove what's available
        assert pos.entry_prices == []

    def test_get_individual_pnls_short_position(self):
        """Test getting individual PnLs for SHORT position"""
        pos = Position(contract="VN30F1M", quantity=-3, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.add_contracts(Decimal("1543.0"), 1)
        pos.add_contracts(Decimal("1543.7"), 1)

        market_price = Decimal("1543.9")
        individual_pnls = pos.get_individual_pnls(market_price)

        # For SHORT: pnl = entry - market
        assert individual_pnls == [
            (Decimal("1540.9"), Decimal("-3.0")),  # 1540.9 - 1543.9 = -3.0
            (Decimal("1543.0"), Decimal("-0.9")),  # 1543.0 - 1543.9 = -0.9
            (Decimal("1543.7"), Decimal("-0.2"))   # 1543.7 - 1543.9 = -0.2
        ]

    def test_get_individual_pnls_long_position(self):
        """Test getting individual PnLs for LONG position"""
        pos = Position(contract="VN30F1M", quantity=2, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.0"), 1)
        pos.add_contracts(Decimal("1545.0"), 1)

        market_price = Decimal("1550.0")
        individual_pnls = pos.get_individual_pnls(market_price)

        # For LONG: pnl = market - entry
        assert individual_pnls == [
            (Decimal("1540.0"), Decimal("10.0")),  # 1550.0 - 1540.0 = 10.0
            (Decimal("1545.0"), Decimal("5.0"))    # 1550.0 - 1545.0 = 5.0
        ]

    def test_update_unrealized_pnl_with_individual_prices(self):
        """Test unrealized PnL calculation using individual entry prices"""
        pos = Position(contract="VN30F1M", quantity=-2, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.add_contracts(Decimal("1543.0"), 1)

        market_price = Decimal("1543.0")
        pos.update_unrealized_pnl(market_price)

        # Expected: (1540.9 - 1543.0) * 100 + (1543.0 - 1543.0) * 100 = -210
        assert pos.unrealized_pnl == Decimal("-210")

    def test_update_unrealized_pnl_fallback_to_average(self):
        """Test unrealized PnL falls back to average_price when entry_prices empty"""
        pos = Position(
            contract="VN30F1M",
            quantity=-2,
            average_price=Decimal("1542.0")
        )
        # entry_prices is empty, should use average_price

        market_price = Decimal("1543.0")
        pos.update_unrealized_pnl(market_price)

        # Expected: (1542.0 - 1543.0) * 2 * 100 = -200
        assert pos.unrealized_pnl == Decimal("-200")

    def test_unrealized_pnl_consistency_with_individual_prices(self):
        """Test that unrealized PnL from individual prices matches VND calculation"""
        pos = Position(contract="VN30F1M", quantity=-3, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.add_contracts(Decimal("1543.0"), 1)
        pos.add_contracts(Decimal("1543.7"), 1)

        market_price = Decimal("1543.9")
        pos.update_unrealized_pnl(market_price)

        # Manual calculation:
        # (1540.9 - 1543.9) * 100 = -300
        # (1543.0 - 1543.9) * 100 = -90
        # (1543.7 - 1543.9) * 100 = -20
        # Total: -410
        assert pos.unrealized_pnl == Decimal("-410")

    def test_fifo_scenario_realistic(self):
        """Test realistic FIFO scenario with opens and closes"""
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))

        # Open SHORT positions
        pos.add_contracts(Decimal("1540.9"), 1)  # [1540.9]
        pos.add_contracts(Decimal("1543.0"), 1)  # [1540.9, 1543.0]
        pos.add_contracts(Decimal("1543.7"), 1)  # [1540.9, 1543.0, 1543.7]
        pos.quantity = -3

        assert len(pos.entry_prices) == 3

        # Close 1 contract (should close 1540.9 first - FIFO)
        removed = pos.remove_contracts(1)
        # Returns (entry_price, opening_fee) tuple
        assert removed[0] == (Decimal("1540.9"), Decimal("20"))
        assert len(pos.entry_prices) == 2
        assert pos.entry_prices == [Decimal("1543.0"), Decimal("1543.7")]

        # Add another SHORT
        pos.add_contracts(Decimal("1543.9"), 1)  # [1543.0, 1543.7, 1543.9]
        assert len(pos.entry_prices) == 3

        # Close 2 contracts (should close 1543.0 and 1543.7 - FIFO)
        removed = pos.remove_contracts(2)
        assert removed == [(Decimal("1543.0"), Decimal("20")), (Decimal("1543.7"), Decimal("20"))]
        assert pos.entry_prices == [Decimal("1543.9")]
