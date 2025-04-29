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
    """訂單基礎類，包含所有必需字段
    
    Attributes:
        symbol: 交易對名稱
        side: 訂單方向（買入/賣出）
        type: 訂單類型（市價/限價等）
        quantity: 訂單數量
    """
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Optional[Decimal] = None

@dataclass
class BaseOrder(OrderBase):
    """訂單狀態基礎類，繼承自 OrderBase，添加狀態相關字段
    
    Attributes:
        order_id: 訂單ID
        client_order_id: 客戶端訂單ID
        price: 訂單價格
        orig_qty: 原始訂單數量
        executed_qty: 已執行數量
        cummulative_quote_qty: 累計成交金額
        status: 訂單狀態
        iceberg_qty: 冰山訂單數量
        time: 訂單創建時間
        update_time: 訂單更新時間
        is_working: 是否正在執行
        orig_quote_order_qty: 原始訂單金額
    """
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
    """訂單類，繼承自 OrderBase，添加訂單相關字段
    
    Attributes:
        price: 訂單價格
        stop_price: 止損價格
        time_in_force: 訂單有效期
        reduce_only: 是否只減倉
        close_position: 是否平倉
        working_type: 價格類型
        price_protect: 是否價格保護
        new_client_order_id: 新的客戶端訂單ID
        position_side: 倉位方向
        price_match: 價格匹配模式
        self_trade_prevention_mode: 自成交防護模式
        good_till_date: 訂單有效期截止時間
        activate_price: 觸發價格
        price_rate: 價格比例
        orig_type: 原始訂單類型
        avg_price: 平均成交價格
        order_id: 訂單ID
        client_order_id: 客戶端訂單ID
        orig_qty: 原始訂單數量
        executed_qty: 已執行數量
        cummulative_quote_qty: 累計成交金額
        realized_profit: 已實現盈虧
        status: 訂單狀態
        timestamp: 訂單創建時間
        update_time: 訂單更新時間
        is_working: 是否正在執行
        newOrderRespType: 訂單響應類型
        execution_type: 執行類型
    """
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
    activate_price: Optional[Decimal] = None
    price_rate: Optional[Decimal] = None
    orig_type: Optional[OrderType] = None
    avg_price: Optional[Decimal] = None
    
    # 訂單狀態
    order_id: Optional[int] = None
    client_order_id: Optional[str] = None
    orig_qty: Optional[Decimal] = None
    executed_qty: Optional[Decimal] = None
    cummulative_quote_qty: Optional[Decimal] = None
    realized_profit: Optional[Decimal] = None
    status: Optional[OrderStatus] = None
    timestamp: Optional[int] = None
    update_time: Optional[int] = None
    is_working: Optional[bool] = None
    newOrderRespType: str = "RESULT"
    execution_type: Optional[str] = None

@dataclass
class OrderResult:
    """訂單結果數據類
    
    Attributes:
        order_id: 訂單ID
        symbol: 交易對名稱
        status: 訂單狀態
        client_order_id: 客戶端訂單ID
        price: 訂單價格
        avg_price: 平均成交價格
        orig_qty: 原始訂單數量
        executed_qty: 已執行數量
        cum_quote: 累計成交金額
        time_in_force: 訂單有效期
        type: 訂單類型
        reduce_only: 是否只減倉
        close_position: 是否平倉
        side: 訂單方向
        position_side: 倉位方向
        stop_price: 止損價格
        working_type: 價格類型
        price_protect: 是否價格保護
        orig_type: 原始訂單類型
        update_time: 訂單更新時間
        activate_price: 觸發價格
        price_rate: 價格比例
        time: 訂單創建時間
        working_time: 訂單執行時間
        self_trade_prevention_mode: 自成交防護模式
        good_till_date: 訂單有效期截止時間
        price_match: 價格匹配模式
        cancel_restrictions: 取消限制
        prevented_match_id: 防止匹配ID
        prevented_quantity: 防止匹配數量
        is_working: 是否正在執行
    """
    # 必需參數
    order_id: int
    symbol: str
    status: OrderStatus
    client_order_id: Optional[str] = None
    price: Optional[Decimal] = None
    avg_price: Optional[Decimal] = None
    orig_qty: Optional[Decimal] = None
    executed_qty: Optional[Decimal] = None
    cum_quote: Optional[Decimal] = None
    time_in_force: Optional[TimeInForce] = None
    type: Optional[OrderType] = None
    reduce_only: Optional[bool] = None
    close_position: Optional[bool] = None
    side: Optional[OrderSide] = None
    position_side: Optional[PositionSide] = None
    stop_price: Optional[Decimal] = None
    working_type: Optional[WorkingType] = None
    price_protect: Optional[bool] = None
    orig_type: Optional[str] = None
    update_time: Optional[int] = None
    activate_price: Optional[Decimal] = None
    price_rate: Optional[Decimal] = None
    time: Optional[int] = None
    working_time: Optional[int] = None
    self_trade_prevention_mode: Optional[SelfTradePreventionMode] = None
    good_till_date: Optional[int] = None
    price_match: Optional[PriceMatch] = None
    cancel_restrictions: Optional[str] = None
    prevented_match_id: Optional[int] = None
    prevented_quantity: Optional[Decimal] = None
    is_working: Optional[bool] = None

@dataclass
class PositionInfo:
    """倉位信息數據類
    
    Attributes:
        symbol: 交易對名稱
        position_side: 倉位方向（多頭/空頭/雙向）
        position_amt: 持倉數量
        entry_price: 開倉價格
        break_even_price: 盈虧平衡價格
        mark_price: 標記價格
        un_realized_profit: 未實現盈虧
        liquidation_price: 強平價格
        isolated_margin: 逐倉保證金
        notional: 名義價值
        margin_asset: 保證金資產
        isolated_wallet: 逐倉錢包
        initial_margin: 初始保證金
        maint_margin: 維持保證金
        position_initial_margin: 持倉初始保證金
        open_order_initial_margin: 開單初始保證金
        adl: 自動減倉等級
        bid_notional: 買方名義價值
        ask_notional: 賣方名義價值
        update_time: 更新時間
    """
    symbol: str
    position_side: PositionSide
    position_amt: Decimal
    entry_price: Decimal
    break_even_price: Decimal
    mark_price: Decimal
    un_realized_profit: Decimal
    liquidation_price: Decimal
    isolated_margin: Decimal
    notional: Decimal
    margin_asset: str
    isolated_wallet: Decimal
    initial_margin: Decimal
    maint_margin: Decimal
    position_initial_margin: Decimal
    open_order_initial_margin: Decimal
    adl: int
    bid_notional: Decimal
    ask_notional: Decimal
    update_time: int

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