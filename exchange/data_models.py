from dataclasses import dataclass
from typing import Optional, List, Dict
from .enums import OrderSide, PositionSide, OrderType, OrderStatus, PositionStatus, CloseReason

@dataclass
class PositionInfo:
    """倉位信息數據類"""
    status: PositionStatus  # 倉位狀態
    symbol: str  # 交易對
    leverage: int  # 槓桿
    size: float  # 倉位大小
    margin: float  # 保證金
    entry_price: float  # 開倉價格
    stop_loss: Optional[float]  # 止損價格
    take_profit: Optional[float]  # 止盈價格
    close_reason: Optional[CloseReason]  # 平倉原因
    close_price: Optional[float]  # 平倉價格
    pnl_usdt: Optional[float]  # 盈虧金額(USDT)
    pnl_percent: Optional[float]  # 盈虧比率(%)

@dataclass
class OrderResult:
    """訂單結果數據類"""
    order_id: int
    client_order_id: str
    symbol: str
    side: OrderSide
    position_side: PositionSide
    type: OrderType
    status: OrderStatus
    quantity: float
    price: float
    stop_price: Optional[float]
    reduce_only: bool
    close_position: bool
    activate_price: Optional[float]
    price_rate: Optional[float]
    update_time: int

@dataclass
class AccountInfo:
    """賬戶信息數據類"""
    total_wallet_balance: float
    total_unrealized_profit: float
    total_margin_balance: float
    available_balance: float
    max_withdraw_amount: float
    assets: List[Dict]
    positions: List[PositionInfo]
    update_time: int 