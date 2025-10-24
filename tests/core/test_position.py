"""
Unit tests for Position class
"""
import pytest
from decimal import Decimal
from core.position import Position


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
            total_fees=Decimal("40")
        )
        pos.update_unrealized_pnl(Decimal("1260.0"))
        # realized + unrealized - fees = 1000 + 2000 - 40 = 2960
        assert pos.total_pnl() == Decimal("2960")

    def test_total_pnl_with_losses(self):
        pos = Position(
            contract="VN30F1M",
            quantity=2,
            average_price=Decimal("1250.0"),
            realized_pnl=Decimal("-500"),
            total_fees=Decimal("40")
        )
        pos.update_unrealized_pnl(Decimal("1240.0"))
        # realized + unrealized - fees = -500 + (-2000) - 40 = -2540
        assert pos.total_pnl() == Decimal("-2540")

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
