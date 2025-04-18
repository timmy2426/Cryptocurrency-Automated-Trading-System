from enum import Enum

class OrderSide(Enum):
    """訂單方向"""
    BUY = "BUY"
    SELL = "SELL"

class PositionSide(Enum):
    """倉位方向"""
    BOTH = "BOTH"
    LONG = "LONG"
    SHORT = "SHORT"

class OrderType(Enum):
    """訂單類型"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"
    LIQUIDATION = "LIQUIDATION"

class TimeInForce(Enum):
    """訂單有效期"""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTX = "GTX"  # Good Till Crossing
    POST_ONLY = "POST_ONLY"  # Post Only

class OrderStatus(Enum):
    """訂單狀態"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    NEW_INSURANCE = "NEW_INSURANCE"
    NEW_ADL = "NEW_ADL"

class PositionStatus(Enum):
    """倉位狀態"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATING = "LIQUIDATING"
    LIQUIDATED = "LIQUIDATED"

class CloseReason(Enum):
    """平倉原因"""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL = "MANUAL"
    LIQUIDATION = "LIQUIDATION"
    OTHER = "OTHER"

class WorkingType(Enum):
    """價格類型"""
    MARK_PRICE = "MARK_PRICE"
    CONTRACT_PRICE = "CONTRACT_PRICE"

class PriceMatch(Enum):
    """價格匹配模式"""
    NONE = "NONE"
    OPPONENT = "OPPONENT"
    OPPONENT_5 = "OPPONENT_5"
    OPPONENT_10 = "OPPONENT_10"
    OPPONENT_20 = "OPPONENT_20"
    QUEUE = "QUEUE"
    QUEUE_5 = "QUEUE_5"
    QUEUE_10 = "QUEUE_10"
    QUEUE_20 = "QUEUE_20"

class SelfTradePreventionMode(Enum):
    """自成交防護模式"""
    NONE = "NONE"
    EXPIRE_TAKER = "EXPIRE_TAKER"
    EXPIRE_MAKER = "EXPIRE_MAKER"
    EXPIRE_BOTH = "EXPIRE_BOTH"

class NewOrderRespType(Enum):
    """新訂單響應類型"""
    ACK = "ACK"
    RESULT = "RESULT" 