from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging
from typing import Optional, List, Dict, Union
import time

from .enums import OrderSide, PositionSide, OrderType, OrderStatus
from .data_models import OrderResult, PositionInfo
from .config import load_config

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderExecutor:
    """訂單執行器"""
    
    def __init__(self, client: Client):
        """
        初始化訂單執行器
        
        Args:
            client: Binance API 客戶端
        """
        self.client = client
        self.config = load_config()
        
    def _set_margin_mode(self) -> None:
        """設置保證金模式"""
        try:
            # 設置為全倉模式
            self.client.futures_change_margin_type(
                symbol=self.symbol,
                marginType='CROSSED'
            )
            logger.info(f"已設置 {self.symbol} 為全倉模式")
        except BinanceAPIException as e:
            if e.code == -4046:  # 已經設置為全倉模式
                logger.info(f"{self.symbol} 已經是全倉模式")
            else:
                logger.error(f"設置保證金模式失敗: {str(e)}")
                raise
                
    def _set_leverage(self) -> None:
        """設置槓桿"""
        try:
            # 設置槓桿為 1 倍
            self.client.futures_change_leverage(
                symbol=self.symbol,
                leverage=1
            )
            logger.info(f"已設置 {self.symbol} 槓桿為 1 倍")
        except BinanceAPIException as e:
            logger.error(f"設置槓桿失敗: {str(e)}")
            raise
            
    def open_position(self, symbol: str, side: str, quantity: float, 
                     stop_loss: float, take_profit: float, 
                     trailing_stop_activation: float, trailing_stop_callback_rate: float) -> List[OrderResult]:
        """
        開倉
        
        Args:
            symbol: 交易對
            side: 方向（BUY/SELL）
            quantity: 數量
            stop_loss: 止損價格
            take_profit: 止盈價格
            trailing_stop_activation: 移動止損觸發價格
            trailing_stop_callback_rate: 移動止損回調率
            
        Returns:
            List[OrderResult]: 訂單結果列表
        """
        try:
            self.symbol = symbol
            
            # 設置保證金模式和槓桿
            self._set_margin_mode()
            self._set_leverage()
            
            # 下市價單
            market_order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            
            # 等待訂單成交
            time.sleep(1)
            
            # 下止損單
            stop_loss_order = self.client.futures_create_order(
                symbol=symbol,
                side='SELL' if side == 'BUY' else 'BUY',
                type='STOP_MARKET',
                quantity=quantity,
                stopPrice=stop_loss,
                reduceOnly=True
            )
            
            # 下止盈單
            take_profit_order = self.client.futures_create_order(
                symbol=symbol,
                side='SELL' if side == 'BUY' else 'BUY',
                type='TAKE_PROFIT_MARKET',
                quantity=quantity,
                stopPrice=take_profit,
                reduceOnly=True
            )
            
            # 下移動止損單
            trailing_stop_order = self.client.futures_create_order(
                symbol=symbol,
                side='SELL' if side == 'BUY' else 'BUY',
                type='TRAILING_STOP_MARKET',
                quantity=quantity,
                activationPrice=trailing_stop_activation,
                callbackRate=trailing_stop_callback_rate,
                reduceOnly=True
            )
            
            # 返回訂單結果
            return [
                OrderResult(
                    order_id=order['orderId'],
                    client_order_id=order['clientOrderId'],
                    symbol=order['symbol'],
                    side=OrderSide[order['side']],
                    position_side=PositionSide[order['positionSide']],
                    type=OrderType[order['type']],
                    status=OrderStatus[order['status']],
                    quantity=float(order['origQty']),
                    price=float(order['price']),
                    stop_price=float(order['stopPrice']) if 'stopPrice' in order else None,
                    reduce_only=order['reduceOnly'],
                    close_position=order['closePosition'],
                    activate_price=float(order['activatePrice']) if 'activatePrice' in order else None,
                    price_rate=float(order['priceRate']) if 'priceRate' in order else None,
                    update_time=order['updateTime']
                )
                for order in [market_order, stop_loss_order, take_profit_order, trailing_stop_order]
            ]
            
        except Exception as e:
            logger.error(f"開倉失敗: {str(e)}")
            raise
            
    def close_position(self, symbol: str, percentage: float = 1.0) -> OrderResult:
        """
        平倉
        
        Args:
            symbol: 交易對
            percentage: 平倉比例（0-1）
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            # 獲取當前倉位
            position = self.client.futures_position_information(symbol=symbol)[0]
            position_amt = float(position['positionAmt'])
            
            if position_amt == 0:
                logger.info(f"{symbol} 沒有持倉")
                return None
                
            # 計算平倉數量
            close_amt = abs(position_amt) * percentage
            
            # 下平倉單
            order = self.client.futures_create_order(
                symbol=symbol,
                side='SELL' if position_amt > 0 else 'BUY',
                type='MARKET',
                quantity=close_amt,
                reduceOnly=True
            )
            
            return OrderResult(
                order_id=order['orderId'],
                client_order_id=order['clientOrderId'],
                symbol=order['symbol'],
                side=OrderSide[order['side']],
                position_side=PositionSide[order['positionSide']],
                type=OrderType[order['type']],
                status=OrderStatus[order['status']],
                quantity=float(order['origQty']),
                price=float(order['price']),
                stop_price=None,
                reduce_only=True,
                close_position=True,
                activate_price=None,
                price_rate=None,
                update_time=order['updateTime']
            )
            
        except Exception as e:
            logger.error(f"平倉失敗: {str(e)}")
            raise
            
    def get_order_status(self, symbol: str, order_id: Optional[int] = None, 
                        client_order_id: Optional[str] = None) -> OrderResult:
        """
        獲取訂單狀態
        
        Args:
            symbol: 交易對
            order_id: 訂單 ID
            client_order_id: 客戶訂單 ID
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            if order_id:
                order = self.client.futures_get_order(
                    symbol=symbol,
                    orderId=order_id
                )
            elif client_order_id:
                order = self.client.futures_get_order(
                    symbol=symbol,
                    origClientOrderId=client_order_id
                )
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
                price=float(order['price']),
                stop_price=float(order['stopPrice']) if 'stopPrice' in order else None,
                reduce_only=order['reduceOnly'],
                close_position=order['closePosition'],
                activate_price=float(order['activatePrice']) if 'activatePrice' in order else None,
                price_rate=float(order['priceRate']) if 'priceRate' in order else None,
                update_time=order['updateTime']
            )
            
        except Exception as e:
            logger.error(f"獲取訂單狀態失敗: {str(e)}")
            raise
            
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                    client_order_id: Optional[str] = None) -> OrderResult:
        """
        取消訂單
        
        Args:
            symbol: 交易對
            order_id: 訂單 ID
            client_order_id: 客戶訂單 ID
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            if order_id:
                order = self.client.futures_cancel_order(
                    symbol=symbol,
                    orderId=order_id
                )
            elif client_order_id:
                order = self.client.futures_cancel_order(
                    symbol=symbol,
                    origClientOrderId=client_order_id
                )
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
                price=float(order['price']),
                stop_price=float(order['stopPrice']) if 'stopPrice' in order else None,
                reduce_only=order['reduceOnly'],
                close_position=order['closePosition'],
                activate_price=float(order['activatePrice']) if 'activatePrice' in order else None,
                price_rate=float(order['priceRate']) if 'priceRate' in order else None,
                update_time=order['updateTime']
            )
            
        except Exception as e:
            logger.error(f"取消訂單失敗: {str(e)}")
            raise
            
    def close_all_positions(self) -> List[OrderResult]:
        """
        平掉所有倉位
        
        Returns:
            List[OrderResult]: 訂單結果列表
        """
        try:
            # 獲取所有倉位
            positions = self.client.futures_position_information()
            
            # 過濾出有持倉的倉位
            open_positions = [p for p in positions if float(p['positionAmt']) != 0]
            
            if not open_positions:
                logger.info("沒有持倉")
                return []
                
            # 平掉所有倉位
            results = []
            for position in open_positions:
                result = self.close_position(position['symbol'])
                if result:
                    results.append(result)
                    
            return results
            
        except Exception as e:
            logger.error(f"平掉所有倉位失敗: {str(e)}")
            raise
