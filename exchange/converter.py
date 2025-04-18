from typing import Dict, Optional
from decimal import Decimal
import logging
from .data_models import Order, OrderResult, PositionInfo
from .enums import (
    OrderSide, OrderType, OrderStatus, TimeInForce, WorkingType,
    PositionSide, PriceMatch, SelfTradePreventionMode, PositionStatus, CloseReason
)
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class BinanceConverter:
    """Binance API 數據轉換器"""
    
    @staticmethod
    def to_order(order_data: Dict) -> Order:
        """將 Binance API 返回的訂單數據轉換為 Order 對象
        
        Args:
            order_data: Binance API 返回的訂單數據，可以是 REST API 或 WebSocket 格式
            
        Returns:
            Order: 轉換後的 Order 對象
        """
        try:
            # 檢查是否為 WebSocket 格式（包含 'o' 字段）
            if isinstance(order_data, dict) and 'o' in order_data:
                # 如果是 WebSocket 消息，提取訂單數據
                order_data = order_data['o']
                return Order(
                    symbol=order_data.get('s', ''),
                    side=OrderSide[order_data.get('S', 'BUY')],
                    type=OrderType[order_data.get('o', 'MARKET')],
                    quantity=Decimal(str(order_data.get('q', 0))),
                    price=Decimal(str(order_data.get('p', 0))) if order_data.get('p') != '0' else None,
                    stop_price=Decimal(str(order_data.get('sp', 0))) if order_data.get('sp') != '0' else None,
                    time_in_force=TimeInForce[order_data.get('f', 'GTC')],
                    order_id=order_data.get('i', 0),
                    client_order_id=order_data.get('c', ''),
                    reduce_only=order_data.get('R', False),
                    close_position=order_data.get('cp', False),
                    working_type=WorkingType[order_data.get('wt', 'CONTRACT_PRICE')],
                    price_protect=order_data.get('pP', False),
                    activate_price=Decimal(str(order_data.get('AP', 0))) if order_data.get('AP') else None,
                    price_rate=Decimal(str(order_data.get('cr', 0))) if order_data.get('cr') else None,
                    position_side=PositionSide[order_data.get('ps', 'BOTH')],
                    orig_type=OrderType[order_data.get('ot', 'MARKET')],
                    price_match=PriceMatch[order_data.get('pm', 'NONE')],
                    self_trade_prevention_mode=SelfTradePreventionMode[order_data.get('stpm', 'NONE')],
                    good_till_date=int(order_data.get('gtd', 0))
                )
            else:
                # REST API 格式使用完整字段名
                return Order(
                    symbol=order_data.get('symbol', ''),
                    side=OrderSide[order_data.get('side', 'BUY')],
                    type=OrderType[order_data.get('type', 'MARKET')],
                    quantity=Decimal(str(order_data.get('quantity', 0))),
                    price=Decimal(str(order_data.get('price', 0))) if order_data.get('price') != '0' else None,
                    stop_price=Decimal(str(order_data.get('stopPrice', 0))) if order_data.get('stopPrice') != '0' else None,
                    time_in_force=TimeInForce[order_data.get('timeInForce', 'GTC')],
                    order_id=order_data.get('orderId', 0),
                    client_order_id=order_data.get('clientOrderId', ''),
                    reduce_only=order_data.get('reduceOnly', False),
                    close_position=order_data.get('closePosition', False),
                    working_type=WorkingType[order_data.get('workingType', 'CONTRACT_PRICE')],
                    price_protect=order_data.get('priceProtect', False),
                    activate_price=Decimal(str(order_data.get('activatePrice', 0))) if order_data.get('activatePrice') else None,
                    price_rate=Decimal(str(order_data.get('priceRate', 0))) if order_data.get('priceRate') else None,
                    position_side=PositionSide[order_data.get('positionSide', 'BOTH')],
                    orig_type=OrderType[order_data.get('origType', 'MARKET')],
                    price_match=PriceMatch[order_data.get('priceMatch', 'NONE')],
                    self_trade_prevention_mode=SelfTradePreventionMode[order_data.get('selfTradePreventionMode', 'NONE')],
                    good_till_date=int(order_data.get('goodTillDate', 0))
                )
        except Exception as e:
            logger.error(f"轉換訂單數據失敗: {str(e)}")
            raise

    @staticmethod
    def to_order_result(response: Dict) -> OrderResult:
        """將 Binance API 返回的訂單數據轉換為 OrderResult 對象
        
        Args:
            response: Binance API 返回的訂單數據
            
        Returns:
            OrderResult: 轉換後的 OrderResult 對象
        """
        try:
            # 如果已經是 OrderResult 對象，直接返回
            if isinstance(response, OrderResult):
                return response
                
            return OrderResult(
                symbol=response.get('symbol', ''),
                side=OrderSide[response.get('side', 'BUY')],
                type=OrderType[response.get('type', 'MARKET')],
                quantity=Decimal(str(response.get('quantity', 0))),
                transact_time=response.get('transactTime', 0),
                time_in_force=TimeInForce[response.get('timeInForce', 'GTC')],
                order_id=response.get('orderId', 0),
                client_order_id=response.get('clientOrderId', ''),
                price=Decimal(str(response.get('price', 0))) if response.get('price') != '0' else None,
                orig_qty=Decimal(str(response.get('origQty', 0))),
                executed_qty=Decimal(str(response.get('executedQty', 0))),
                cummulative_quote_qty=Decimal(str(response.get('cummulativeQuoteQty', 0))),
                status=OrderStatus[response.get('status', 'NEW')],
                time=response.get('time', 0),
                update_time=response.get('updateTime', 0),
                is_working=response.get('isWorking', True),
                stop_price=Decimal(str(response.get('stopPrice', 0))) if response.get('stopPrice') != '0' else None,
                working_type=WorkingType[response.get('workingType', 'CONTRACT_PRICE')],
                price_protect=response.get('priceProtect', False),
                reduce_only=response.get('reduceOnly', False),
                close_position=response.get('closePosition', False),
                position_side=PositionSide[response.get('positionSide', 'BOTH')],
                activation_price=Decimal(str(response.get('activatePrice', 0))) if response.get('activatePrice') else None,
                callback_rate=Decimal(str(response.get('priceRate', 0))) if response.get('priceRate') else None,
                price_match=PriceMatch[response.get('priceMatch', 'NONE')],
                self_trade_prevention_mode=SelfTradePreventionMode[response.get('selfTradePreventionMode', 'NONE')],
                good_till_date=int(response.get('goodTillDate', 0))
            )
        except Exception as e:
            logger.error(f"轉換訂單結果失敗: {str(e)}")
            raise

    @staticmethod
    def to_position(position_data: Dict) -> PositionInfo:
        """將 Binance API 返回的倉位數據轉換為 PositionInfo 對象
        
        Args:
            position_data: Binance API 返回的倉位數據
            
        Returns:
            PositionInfo: 轉換後的 PositionInfo 對象
        """
        try:
            # 檢查是否為 WebSocket 格式
            if 'e' in position_data and position_data['e'] == 'ACCOUNT_UPDATE':
                position = position_data.get('a', {}).get('P', [{}])[0]
                return PositionInfo(
                    symbol=position.get('s', ''),
                    position_amt=Decimal(str(position.get('pa', 0))),
                    entry_price=Decimal(str(position.get('ep', 0))),
                    mark_price=Decimal(str(position.get('mp', 0))),
                    un_realized_profit=Decimal(str(position.get('up', 0))),
                    liquidation_price=Decimal(str(position.get('lp', 0))),
                    leverage=int(position.get('l', 1)),
                    max_notional_value=Decimal(str(position.get('mnv', 0))),
                    margin_type=position.get('mt', 'isolated'),
                    isolated_margin=Decimal(str(position.get('im', 0))),
                    is_auto_add_margin=position.get('iam', False),
                    status=PositionStatus.OPEN if float(position.get('pa', 0)) != 0 else PositionStatus.CLOSED,
                    stop_loss=float(position.get('sl', 0)) if position.get('sl') else None,
                    take_profit=float(position.get('tp', 0)) if position.get('tp') else None,
                    close_reason=BinanceConverter._get_close_reason(position),
                    close_price=float(position.get('cp', 0)) if position.get('cp') else None,
                    pnl_usdt=float(position.get('up', 0)),
                    pnl_percent=float(position.get('cr', 0)),
                    position_balance=Decimal(str(position.get('pb', 0))),
                    margin_ratio=Decimal(str(position.get('mr', 0))) if position.get('mr') else None,
                    margin_ratio_level=position.get('mrl', ''),
                    update_time=datetime.fromtimestamp(position.get('t', 0) / 1000)
                )
            else:
                # REST API 格式
                return PositionInfo(
                    symbol=position_data.get('symbol', ''),
                    position_amt=Decimal(str(position_data.get('positionAmt', 0))),
                    entry_price=Decimal(str(position_data.get('entryPrice', 0))),
                    mark_price=Decimal(str(position_data.get('markPrice', 0))),
                    un_realized_profit=Decimal(str(position_data.get('unRealizedProfit', 0))),
                    liquidation_price=Decimal(str(position_data.get('liquidationPrice', 0))),
                    leverage=int(position_data.get('leverage', 1)),
                    max_notional_value=Decimal(str(position_data.get('maxNotionalValue', 0))),
                    margin_type=position_data.get('marginType', 'isolated'),
                    isolated_margin=Decimal(str(position_data.get('isolatedMargin', 0))),
                    is_auto_add_margin=position_data.get('isAutoAddMargin', False),
                    status=PositionStatus.OPEN if float(position_data.get('positionAmt', 0)) != 0 else PositionStatus.CLOSED,
                    stop_loss=float(position_data.get('stopLoss', 0)) if position_data.get('stopLoss') else None,
                    take_profit=float(position_data.get('takeProfit', 0)) if position_data.get('takeProfit') else None,
                    close_reason=BinanceConverter._get_close_reason(position_data),
                    close_price=float(position_data.get('closePrice', 0)) if position_data.get('closePrice') else None,
                    pnl_usdt=float(position_data.get('unRealizedProfit', 0)),
                    pnl_percent=float(position_data.get('closeRatio', 0)) if position_data.get('closeRatio') else None,
                    position_balance=Decimal(str(position_data.get('positionBalance', 0))),
                    margin_ratio=Decimal(str(position_data.get('marginRatio', 0))) if position_data.get('marginRatio') else None,
                    margin_ratio_level=position_data.get('marginRatioLevel', ''),
                    update_time=datetime.fromtimestamp(int(time.time() * 1000))
                )
        except Exception as e:
            logger.error(f"轉換倉位數據失敗: {str(e)}")
            raise

    @staticmethod
    def _get_close_reason(position_data: Dict) -> Optional[CloseReason]:
        """從倉位數據中獲取平倉原因
        
        Args:
            position_data: 倉位數據
            
        Returns:
            CloseReason: 平倉原因，如果沒有則返回 None
        """
        try:
            # 檢查是否有平倉原因字段
            reason = position_data.get('closeReason') or position_data.get('cr')
            if not reason:
                return None
                
            # 轉換平倉原因
            reason_map = {
                'TAKE_PROFIT': CloseReason.TAKE_PROFIT,
                'STOP_LOSS': CloseReason.STOP_LOSS,
                'LIQUIDATION': CloseReason.LIQUIDATION,
                'MANUAL': CloseReason.MANUAL,
                'TRAILING_STOP': CloseReason.TRAILING_STOP
            }
            return reason_map.get(reason.upper(), None)
            
        except Exception as e:
            logger.error(f"獲取平倉原因失敗: {str(e)}")
            return None
