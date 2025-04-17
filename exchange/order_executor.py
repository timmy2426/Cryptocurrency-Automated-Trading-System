from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging
from typing import Optional, List, Dict, Union
from enum import Enum
from dataclasses import dataclass
import yaml
import os

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderSide(Enum):
    """訂單方向枚舉"""
    BUY = "BUY"
    SELL = "SELL"

class PositionSide(Enum):
    """倉位方向枚舉"""
    LONG = "LONG"
    SHORT = "SHORT"

class OrderType(Enum):
    """訂單類型枚舉"""
    MARKET = "MARKET"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"

class OrderStatus(Enum):
    """訂單狀態枚舉"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    NEW_INSURANCE = "NEW_INSURANCE"
    NEW_ADL = "NEW_ADL"

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

class OrderExecutor:
    """訂單執行器"""
    
    def __init__(self, client: Client):
        """
        初始化訂單執行器
        
        Args:
            client: Binance API 客戶端實例
        """
        self.client = client
        
        # 讀取設置文件
        with open('config/settings.yaml', 'r', encoding='utf-8') as f:
            self.settings = yaml.safe_load(f)
            
        # 設置全倉和聯合保證金模式
        self._set_margin_mode()
        
        # 設置槓桿
        self._set_leverage()
        
    def _set_margin_mode(self) -> None:
        """設置全倉和聯合保證金模式"""
        try:
            # 設置全倉模式
            self.client.futures_change_margin_type(marginType='CROSSED')
            
            # 設置聯合保證金模式
            self.client.futures_change_position_mode(dualSidePosition=False)
            
            logger.info("已設置全倉和聯合保證金模式")
        except Exception as e:
            logger.error(f"設置保證金模式失敗: {str(e)}")
            raise
            
    def _set_leverage(self) -> None:
        """設置槓桿"""
        try:
            leverage = self.settings['trade']['leverage']
            self.client.futures_change_leverage(leverage=leverage)
            logger.info(f"已設置槓桿為 {leverage}x")
        except Exception as e:
            logger.error(f"設置槓桿失敗: {str(e)}")
            raise
            
    def open_position(self,
                     symbol: str,
                     side: OrderSide,
                     quantity: float,
                     stop_loss: float,
                     take_profit: float,
                     trailing_stop_activation: float,
                     trailing_stop_callback_rate: float) -> List[OrderResult]:
        """
        開倉
        
        Args:
            symbol: 交易對
            side: 方向（多/空）
            quantity: 數量
            stop_loss: 止損價格
            take_profit: 止盈價格
            trailing_stop_activation: 移動止損觸發價格
            trailing_stop_callback_rate: 移動止損回調率（百分比）
            
        Returns:
            List[OrderResult]: 訂單結果列表
        """
        try:
            orders = []
            
            # 1. 開倉市價單
            market_order = self.client.futures_create_order(
                symbol=symbol,
                side=side.value,
                type=OrderType.MARKET.value,
                quantity=quantity
            )
            orders.append(OrderResult(
                order_id=market_order['orderId'],
                client_order_id=market_order['clientOrderId'],
                symbol=market_order['symbol'],
                side=OrderSide(market_order['side']),
                position_side=PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT,
                type=OrderType(market_order['type']),
                status=OrderStatus(market_order['status']),
                quantity=float(market_order['origQty']),
                price=float(market_order['price']),
                stop_price=None,
                reduce_only=False,
                close_position=False,
                activate_price=None,
                price_rate=None,
                update_time=market_order['updateTime']
            ))
            
            # 2. 止損單
            stop_loss_order = self.client.futures_create_order(
                symbol=symbol,
                side=OrderSide.SELL.value if side == OrderSide.BUY else OrderSide.BUY.value,
                type=OrderType.STOP_MARKET.value,
                stopPrice=stop_loss,
                closePosition=True
            )
            orders.append(OrderResult(
                order_id=stop_loss_order['orderId'],
                client_order_id=stop_loss_order['clientOrderId'],
                symbol=stop_loss_order['symbol'],
                side=OrderSide(stop_loss_order['side']),
                position_side=PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT,
                type=OrderType(stop_loss_order['type']),
                status=OrderStatus(stop_loss_order['status']),
                quantity=0,
                price=0,
                stop_price=float(stop_loss_order['stopPrice']),
                reduce_only=True,
                close_position=True,
                activate_price=None,
                price_rate=None,
                update_time=stop_loss_order['updateTime']
            ))
            
            # 3. 止盈單
            take_profit_order = self.client.futures_create_order(
                symbol=symbol,
                side=OrderSide.SELL.value if side == OrderSide.BUY else OrderSide.BUY.value,
                type=OrderType.TAKE_PROFIT_MARKET.value,
                stopPrice=take_profit,
                closePosition=True
            )
            orders.append(OrderResult(
                order_id=take_profit_order['orderId'],
                client_order_id=take_profit_order['clientOrderId'],
                symbol=take_profit_order['symbol'],
                side=OrderSide(take_profit_order['side']),
                position_side=PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT,
                type=OrderType(take_profit_order['type']),
                status=OrderStatus(take_profit_order['status']),
                quantity=0,
                price=0,
                stop_price=float(take_profit_order['stopPrice']),
                reduce_only=True,
                close_position=True,
                activate_price=None,
                price_rate=None,
                update_time=take_profit_order['updateTime']
            ))
            
            # 4. 移動止損單
            trailing_stop_order = self.client.futures_create_order(
                symbol=symbol,
                side=OrderSide.SELL.value if side == OrderSide.BUY else OrderSide.BUY.value,
                type=OrderType.TRAILING_STOP_MARKET.value,
                activationPrice=trailing_stop_activation,
                callbackRate=trailing_stop_callback_rate,
                closePosition=True
            )
            orders.append(OrderResult(
                order_id=trailing_stop_order['orderId'],
                client_order_id=trailing_stop_order['clientOrderId'],
                symbol=trailing_stop_order['symbol'],
                side=OrderSide(trailing_stop_order['side']),
                position_side=PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT,
                type=OrderType(trailing_stop_order['type']),
                status=OrderStatus(trailing_stop_order['status']),
                quantity=0,
                price=0,
                stop_price=None,
                reduce_only=True,
                close_position=True,
                activate_price=float(trailing_stop_order['activatePrice']),
                price_rate=float(trailing_stop_order['priceRate']),
                update_time=trailing_stop_order['updateTime']
            ))
            
            logger.info(f"已創建 {symbol} {side.value} 倉位，數量: {quantity}")
            return orders
            
        except Exception as e:
            logger.error(f"開倉失敗: {str(e)}")
            raise
            
    def close_position(self, symbol: str, percentage: float) -> OrderResult:
        """
        平倉
        
        Args:
            symbol: 交易對
            percentage: 平倉百分比（0-1）
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            # 獲取當前倉位
            position = self.client.futures_position_information(symbol=symbol)[0]
            position_amt = float(position['positionAmt'])
            
            if position_amt == 0:
                raise ValueError(f"{symbol} 沒有持倉")
                
            # 計算平倉數量
            close_amt = abs(position_amt) * percentage
            
            # 創建市價平倉單
            order = self.client.futures_create_order(
                symbol=symbol,
                side=OrderSide.SELL.value if position_amt > 0 else OrderSide.BUY.value,
                type=OrderType.MARKET.value,
                quantity=close_amt,
                reduceOnly=True
            )
            
            result = OrderResult(
                order_id=order['orderId'],
                client_order_id=order['clientOrderId'],
                symbol=order['symbol'],
                side=OrderSide(order['side']),
                position_side=PositionSide.LONG if position_amt > 0 else PositionSide.SHORT,
                type=OrderType(order['type']),
                status=OrderStatus(order['status']),
                quantity=float(order['origQty']),
                price=float(order['price']),
                stop_price=None,
                reduce_only=True,
                close_position=False,
                activate_price=None,
                price_rate=None,
                update_time=order['updateTime']
            )
            
            logger.info(f"已平倉 {symbol} {percentage*100}%，數量: {close_amt}")
            return result
            
        except Exception as e:
            logger.error(f"平倉失敗: {str(e)}")
            raise

    def get_order_status(self, symbol: str, order_id: Optional[int] = None, 
                        client_order_id: Optional[str] = None) -> OrderResult:
        """
        查詢訂單狀態
        
        Args:
            symbol: 交易對
            order_id: 訂單ID
            client_order_id: 客戶訂單ID
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            if order_id:
                order = self.client.futures_get_order(symbol=symbol, orderId=order_id)
            elif client_order_id:
                order = self.client.futures_get_order(symbol=symbol, origClientOrderId=client_order_id)
            else:
                raise ValueError("必須提供 order_id 或 client_order_id")
                
            return OrderResult(
                order_id=order['orderId'],
                client_order_id=order['clientOrderId'],
                symbol=order['symbol'],
                side=OrderSide[order['side']],
                position_side=PositionSide[order['positionSide']],
                type=OrderType[order['type']],
                status=OrderStatus[order['status']],
                quantity=float(order['origQty']),
                price=float(order['price']) if order['price'] else None,
                stop_price=float(order['stopPrice']) if order['stopPrice'] else None,
                reduce_only=order['reduceOnly'],
                close_position=order['closePosition'],
                activate_price=float(order['activationPrice']) if order['activationPrice'] else None,
                price_rate=float(order['priceRate']) if order['priceRate'] else None,
                update_time=order['updateTime']
            )
            
        except Exception as e:
            logger.error(f"查詢訂單狀態失敗: {str(e)}")
            raise
            
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                    client_order_id: Optional[str] = None) -> OrderResult:
        """
        取消訂單
        
        Args:
            symbol: 交易對
            order_id: 訂單ID
            client_order_id: 客戶訂單ID
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            if order_id:
                order = self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
            elif client_order_id:
                order = self.client.futures_cancel_order(symbol=symbol, origClientOrderId=client_order_id)
            else:
                raise ValueError("必須提供 order_id 或 client_order_id")
                
            return OrderResult(
                order_id=order['orderId'],
                client_order_id=order['clientOrderId'],
                symbol=order['symbol'],
                side=OrderSide[order['side']],
                position_side=PositionSide[order['positionSide']],
                type=OrderType[order['type']],
                status=OrderStatus[order['status']],
                quantity=float(order['origQty']),
                price=float(order['price']) if order['price'] else None,
                stop_price=float(order['stopPrice']) if order['stopPrice'] else None,
                reduce_only=order['reduceOnly'],
                close_position=order['closePosition'],
                activate_price=float(order['activationPrice']) if order['activationPrice'] else None,
                price_rate=float(order['priceRate']) if order['priceRate'] else None,
                update_time=order['updateTime']
            )
            
        except Exception as e:
            logger.error(f"取消訂單失敗: {str(e)}")
            raise
            
    def close_all_positions(self) -> List[OrderResult]:
        """
        全部平倉
        
        Returns:
            List[OrderResult]: 平倉訂單結果列表
        """
        try:
            # 獲取所有倉位
            positions = self.client.futures_position_information()
            
            # 過濾出有倉位的交易對
            positions = [p for p in positions if float(p['positionAmt']) != 0]
            
            results = []
            for position in positions:
                symbol = position['symbol']
                position_amt = float(position['positionAmt'])
                
                # 根據倉位方向決定平倉方向
                if position_amt > 0:
                    side = OrderSide.SELL
                else:
                    side = OrderSide.BUY
                    
                # 市價平倉
                order = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type=OrderType.MARKET.value,
                    quantity=abs(position_amt),
                    reduceOnly=True
                )
                
                results.append(OrderResult(
                    order_id=order['orderId'],
                    client_order_id=order['clientOrderId'],
                    symbol=order['symbol'],
                    side=OrderSide[order['side']],
                    position_side=PositionSide[order['positionSide']],
                    type=OrderType[order['type']],
                    status=OrderStatus[order['status']],
                    quantity=float(order['origQty']),
                    price=None,
                    stop_price=None,
                    reduce_only=True,
                    close_position=False,
                    activate_price=None,
                    price_rate=None,
                    update_time=order['updateTime']
                ))
                
            return results
            
        except Exception as e:
            logger.error(f"全部平倉失敗: {str(e)}")
            raise
