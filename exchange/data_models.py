from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from .enums import (
    OrderSide, OrderType, OrderStatus, PositionStatus, CloseReason, 
    TimeInForce, WorkingType, PositionSide, PriceMatch, 
    SelfTradePreventionMode, NewOrderRespType
)
from datetime import datetime
from decimal import Decimal

@dataclass
class AssetInfo:
    """資產信息數據類
    
    Attributes:
        asset: 資產名稱
        wallet_balance: 錢包餘額
        unrealized_profit: 未實現盈虧
        margin_balance: 保證金餘額
        maint_margin: 維持保證金
        initial_margin: 初始保證金
        position_initial_margin: 持倉初始保證金
        open_order_initial_margin: 開單初始保證金
        cross_wallet_balance: 全倉錢包餘額
        cross_un_pnl: 全倉未實現盈虧
        available_balance: 可用餘額
        max_withdraw_amount: 最大可提現金額
        margin_available: 可用保證金
        update_time: 更新時間
    """
    asset: str
    wallet_balance: Decimal
    unrealized_profit: Decimal
    margin_balance: Decimal
    maint_margin: Decimal
    initial_margin: Decimal
    position_initial_margin: Decimal
    open_order_initial_margin: Decimal
    cross_wallet_balance: Decimal
    cross_un_pnl: Decimal
    available_balance: Decimal
    max_withdraw_amount: Decimal
    margin_available: Decimal
    update_time: int

@dataclass
class OrderBase:
    """訂單基礎類，包含所有必需字段"""
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal

@dataclass
class BaseOrder(OrderBase):
    """訂單狀態基礎類，繼承自 OrderBase，添加狀態相關字段"""
    # 訂單狀態相關字段
    order_id: Optional[int] = None
    client_order_id: Optional[str] = None
    price: Optional[Decimal] = None
    orig_qty: Optional[Decimal] = None
    executed_qty: Optional[Decimal] = None
    cummulative_quote_qty: Optional[Decimal] = None
    status: Optional[OrderStatus] = None
    iceberg_qty: Optional[Decimal] = None
    time: Optional[int] = None
    update_time: Optional[int] = None
    is_working: Optional[bool] = None
    orig_quote_order_qty: Optional[Decimal] = None

@dataclass
class Order(OrderBase):
    """訂單類，繼承自 OrderBase，添加訂單相關字段"""
    # 訂單參數
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: Optional[TimeInForce] = None
    reduce_only: bool = False
    close_position: bool = False
    working_type: Optional[WorkingType] = None
    price_protect: bool = False
    new_client_order_id: Optional[str] = None
    position_side: Optional[PositionSide] = None
    price_match: Optional[PriceMatch] = None
    self_trade_prevention_mode: Optional[SelfTradePreventionMode] = None
    good_till_date: Optional[int] = None
    activate_price: Optional[Decimal] = None  # 追蹤止損訂單的激活價格
    price_rate: Optional[Decimal] = None  # 追蹤止損訂單的回調率
    orig_type: Optional[OrderType] = None  # 原始訂單類型
    avg_price: Optional[Decimal] = None  # 平均成交價格
    
    # 訂單狀態相關字段
    order_id: Optional[int] = None
    client_order_id: Optional[str] = None
    orig_qty: Optional[Decimal] = None
    executed_qty: Optional[Decimal] = None
    cummulative_quote_qty: Optional[Decimal] = None
    status: Optional[OrderStatus] = None
    time: Optional[int] = None
    update_time: Optional[int] = None
    is_working: Optional[bool] = None

@dataclass
class OrderResult:
    """訂單結果數據類
    
    Attributes:
        symbol: 交易對
        side: 買賣方向
        type: 訂單類型
        quantity: 數量
        transact_time: 交易時間
        time_in_force: 訂單有效期
        order_id: 訂單ID
        client_order_id: 客戶訂單ID
        price: 價格
        orig_qty: 原始數量
        executed_qty: 已成交數量
        cummulative_quote_qty: 累計成交金額
        status: 訂單狀態
        iceberg_qty: 冰山訂單數量
        time: 訂單時間
        update_time: 更新時間
        is_working: 是否有效
        orig_quote_order_qty: 原始訂單金額
        stop_price: 止損價格
        working_type: 價格類型
        price_protect: 是否開啟價格保護
        reduce_only: 是否只減倉
        close_position: 是否平倉
        activation_price: 移動止損激活價格
        callback_rate: 移動止損回調率
        position_side: 倉位方向
        price_match: 價格匹配模式
        self_trade_prevention_mode: 自成交防護模式
        good_till_date: 訂單到期時間
    """
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal
    transact_time: int
    time_in_force: TimeInForce
    order_id: int
    client_order_id: str
    price: Optional[Decimal] = None
    orig_qty: Optional[Decimal] = None
    executed_qty: Optional[Decimal] = None
    cummulative_quote_qty: Optional[Decimal] = None
    status: Optional[OrderStatus] = None
    iceberg_qty: Optional[Decimal] = None
    time: Optional[int] = None
    update_time: Optional[int] = None
    is_working: Optional[bool] = None
    orig_quote_order_qty: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    working_type: Optional[str] = None
    price_protect: Optional[bool] = None
    reduce_only: Optional[bool] = None
    close_position: Optional[bool] = None
    activation_price: Optional[Decimal] = None
    callback_rate: Optional[Decimal] = None
    position_side: Optional[PositionSide] = None
    price_match: Optional[PriceMatch] = None
    self_trade_prevention_mode: Optional[SelfTradePreventionMode] = None
    good_till_date: Optional[int] = None

@dataclass
class PositionInfo:
    """倉位信息數據類
    
    Attributes:
        symbol: 交易對
        position_amt: 持倉數量
        entry_price: 開倉價格
        mark_price: 標記價格
        un_realized_profit: 未實現盈虧
        liquidation_price: 強平價格
        leverage: 槓桿倍數
        max_notional_value: 最大名義價值
        margin_type: 保證金類型
        isolated_margin: 逐倉保證金
        is_auto_add_margin: 是否自動追加保證金
        status: 倉位狀態
        position_balance: 倉位餘額
        margin_ratio: 保證金率
        margin_ratio_level: 保證金率等級
        update_time: 更新時間
        stop_loss: 止損價格
        take_profit: 止盈價格
        close_reason: 平倉原因
        close_price: 平倉價格
        pnl_usdt: 盈虧（USDT）
        pnl_percent: 盈虧百分比
    """
    symbol: str
    position_amt: Decimal
    entry_price: Decimal
    mark_price: Decimal
    un_realized_profit: Decimal
    liquidation_price: Decimal
    leverage: int
    max_notional_value: Decimal
    margin_type: str
    isolated_margin: Decimal
    is_auto_add_margin: bool
    status: PositionStatus = PositionStatus.CLOSED
    position_balance: Decimal = Decimal('0')
    margin_ratio: Decimal = Decimal('0')
    margin_ratio_level: str = ''
    update_time: datetime = datetime.now()
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    close_reason: Optional[CloseReason] = None
    close_price: Optional[float] = None
    pnl_usdt: float = 0.0
    pnl_percent: float = 0.0

@dataclass
class AccountInfo:
    """賬戶信息數據類
    
    Attributes:
        total_wallet_balance: 總錢包餘額
        total_unrealized_profit: 總未實現盈虧
        total_margin_balance: 總保證金餘額
        total_position_initial_margin: 總持倉初始保證金
        total_open_order_initial_margin: 總開單初始保證金
        total_cross_wallet_balance: 總全倉錢包餘額
        available_balance: 可用餘額
        max_withdraw_amount: 最大可提現金額
        total_initial_margin: 總初始保證金
        total_maint_margin: 總維持保證金
        total_cross_un_pnl: 總全倉未實現盈虧
        assets: 資產列表
        positions: 倉位列表
        update_time: 更新時間
    """
    total_wallet_balance: Decimal
    total_unrealized_profit: Decimal
    total_margin_balance: Decimal
    total_position_initial_margin: Decimal
    total_open_order_initial_margin: Decimal
    total_cross_wallet_balance: Decimal
    available_balance: Decimal
    max_withdraw_amount: Decimal
    total_initial_margin: Decimal
    total_maint_margin: Decimal
    total_cross_un_pnl: Decimal
    assets: List[AssetInfo]
    positions: List[PositionInfo]
    update_time: int 