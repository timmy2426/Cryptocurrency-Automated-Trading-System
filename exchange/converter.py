from typing import Dict, Optional
from decimal import Decimal
import logging
from .data_models import Order, OrderResult, PositionInfo, AccountInfo
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
            if isinstance(order_data, dict) and 'o' in order_data and 'T' in order_data:
                # 如果是 WebSocket 消息，提取訂單數據
                transaction_time = order_data['T']
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
                    good_till_date=int(order_data.get('gtd', 0)),
                    avg_price=Decimal(str(order_data.get('ap', 0))) if order_data.get('ap') != '0' else None,
                    last_filled_qty=Decimal(str(order_data.get('l', 0))) if order_data.get('l') != '0' else None,
                    executed_qty=Decimal(str(order_data.get('z', 0))) if order_data.get('z') != '0' else None,
                    realized_profit=Decimal(str(order_data.get('rp', 0))) if order_data.get('rp') != '0' else None,
                    status=OrderStatus[order_data.get('X', 'NEW')],
                    execution_type=order_data.get('x', 'NEW'),
                    timestamp=int(transaction_time)
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
                order_id=response.get('orderId', 0),
                symbol=response.get('symbol', ''),
                status=OrderStatus[response.get('status', 'NEW')],
                client_order_id=response.get('clientOrderId', ''),
                price=Decimal(str(response.get('price', 0))) if response.get('price') != '0' else None,
                avg_price=Decimal(str(response.get('avgPrice', 0))) if response.get('avgPrice') != '0' else None,
                orig_qty=Decimal(str(response.get('origQty', 0))),
                executed_qty=Decimal(str(response.get('executedQty', 0))),
                cum_quote=Decimal(str(response.get('cumQuote', 0))),
                time_in_force=TimeInForce[response.get('timeInForce', 'GTC')],
                type=OrderType[response.get('type', 'MARKET')],
                reduce_only=response.get('reduceOnly', False),
                close_position=response.get('closePosition', False),
                side=OrderSide[response.get('side', 'BUY')],
                position_side=PositionSide[response.get('positionSide', 'BOTH')],
                stop_price=Decimal(str(response.get('stopPrice', 0))) if response.get('stopPrice') != '0' else None,
                working_type=WorkingType[response.get('workingType', 'CONTRACT_PRICE')],
                price_protect=response.get('priceProtect', False),
                orig_type=response.get('origType', ''),
                update_time=response.get('updateTime', 0),
                activate_price=Decimal(str(response.get('activatePrice', 0))) if response.get('activatePrice') else None,
                price_rate=Decimal(str(response.get('priceRate', 0))) if response.get('priceRate') else None,
                time=response.get('time', 0),
                working_time=response.get('workingTime', 0),
                self_trade_prevention_mode=SelfTradePreventionMode[response.get('selfTradePreventionMode', 'NONE')],
                good_till_date=int(response.get('goodTillDate', 0)),
                price_match=PriceMatch[response.get('priceMatch', 'NONE')],
                cancel_restrictions=response.get('cancelRestrictions', ''),
                prevented_match_id=response.get('preventedMatchId', 0),
                prevented_quantity=Decimal(str(response.get('preventedQuantity', 0))) if response.get('preventedQuantity') else None,
                is_working=response.get('isWorking', True)
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
                    position_side=position.get('ps', 'BOTH'),
                    position_amt=Decimal(str(position.get('pa', 0))),
                    entry_price=Decimal(str(position.get('ep', 0))),
                    break_even_price=Decimal(str(position.get('bep', 0))),
                    mark_price=Decimal(str(position.get('mp', 0))),
                    un_realized_profit=Decimal(str(position.get('up', 0))),
                    liquidation_price=Decimal(str(position.get('lp', 0))),
                    isolated_margin=Decimal(str(position.get('im', 0))),
                    notional=Decimal(str(position.get('n', 0))),
                    margin_asset=position.get('ma', 'USDT'),
                    isolated_wallet=Decimal(str(position.get('iw', 0))),
                    initial_margin=Decimal(str(position.get('im', 0))),
                    maint_margin=Decimal(str(position.get('mm', 0))),
                    position_initial_margin=Decimal(str(position.get('pim', 0))),
                    open_order_initial_margin=Decimal(str(position.get('oim', 0))),
                    adl=int(position.get('adl', 0)),
                    bid_notional=Decimal(str(position.get('bn', 0))),
                    ask_notional=Decimal(str(position.get('an', 0))),
                    update_time=int(position.get('t', 0))
                )
            else:
                # REST API 格式
                return PositionInfo(
                    symbol=position_data.get('symbol', ''),
                    position_side=position_data.get('positionSide', 'BOTH'),
                    position_amt=Decimal(str(position_data.get('positionAmt', 0))),
                    entry_price=Decimal(str(position_data.get('entryPrice', 0))),
                    break_even_price=Decimal(str(position_data.get('breakEvenPrice', 0))),
                    mark_price=Decimal(str(position_data.get('markPrice', 0))),
                    un_realized_profit=Decimal(str(position_data.get('unRealizedProfit', 0))),
                    liquidation_price=Decimal(str(position_data.get('liquidationPrice', 0))),
                    isolated_margin=Decimal(str(position_data.get('isolatedMargin', 0))),
                    notional=Decimal(str(position_data.get('notional', 0))),
                    margin_asset=position_data.get('marginAsset', 'USDT'),
                    isolated_wallet=Decimal(str(position_data.get('isolatedWallet', 0))),
                    initial_margin=Decimal(str(position_data.get('initialMargin', 0))),
                    maint_margin=Decimal(str(position_data.get('maintMargin', 0))),
                    position_initial_margin=Decimal(str(position_data.get('positionInitialMargin', 0))),
                    open_order_initial_margin=Decimal(str(position_data.get('openOrderInitialMargin', 0))),
                    adl=int(position_data.get('adl', 0)),
                    bid_notional=Decimal(str(position_data.get('bidNotional', 0))),
                    ask_notional=Decimal(str(position_data.get('askNotional', 0))),
                    update_time=int(position_data.get('updateTime', 0))
                )
        except Exception as e:
            logger.error(f"轉換倉位數據失敗: {str(e)}")
            raise

    @staticmethod
    def get_close_reason(order: Order) -> Optional[str]:
        """從訂單數據中獲取平倉原因
        
        Args:
            order: Order 物件，包含訂單信息
            
        Returns:
            str: 平倉原因，如果沒有則返回 None
        """
        try:
            # 根據原始訂單類型判斷
            if order.orig_type:
                if order.orig_type == OrderType.TAKE_PROFIT_MARKET:
                    return CloseReason.TAKE_PROFIT.value
                elif order.orig_type == OrderType.STOP_MARKET:
                    return CloseReason.STOP_LOSS.value
                elif order.orig_type == OrderType.TRAILING_STOP_MARKET:
                    return CloseReason.TRAILING_STOP.value
            
            # 根據執行類型判斷
            if order.execution_type:
                if order.execution_type == 'LIQUIDATION':
                    return CloseReason.LIQUIDATION.value
                elif order.execution_type == 'EXPIRED':
                    return CloseReason.MANUAL.value
            
            # 如果都無法判斷，則返回手動平倉
            return CloseReason.MANUAL.value
            
        except Exception as e:
            logger.error(f"獲取平倉原因失敗: {str(e)}")
            return None

    @staticmethod
    def to_account_info(account_data: Dict) -> AccountInfo:
        """將幣安 API 返回的帳戶數據轉換為 AccountInfo 對象
        
        Args:
            account_data: 幣安 API 返回的帳戶數據
            
        Returns:
            AccountInfo: 轉換後的帳戶信息對象
        """
        return AccountInfo(
            total_wallet_balance=Decimal(str(account_data.get('totalWalletBalance', 0))),
            total_unrealized_profit=Decimal(str(account_data.get('totalUnrealizedProfit', 0))),
            total_margin_balance=Decimal(str(account_data.get('totalMarginBalance', 0))),
            total_position_initial_margin=Decimal(str(account_data.get('totalPositionInitialMargin', 0))),
            total_open_order_initial_margin=Decimal(str(account_data.get('totalOpenOrderInitialMargin', 0))),
            total_cross_wallet_balance=Decimal(str(account_data.get('totalCrossWalletBalance', 0))),
            available_balance=Decimal(str(account_data.get('availableBalance', 0))),
            max_withdraw_amount=Decimal(str(account_data.get('maxWithdrawAmount', 0))),
            total_initial_margin=Decimal(str(account_data.get('totalInitialMargin', 0))),
            total_maint_margin=Decimal(str(account_data.get('totalMaintMargin', 0))),
            total_cross_un_pnl=Decimal(str(account_data.get('totalCrossUnPnl', 0))),
            assets=[{
                'asset': asset.get('asset', ''),
                'wallet_balance': Decimal(str(asset.get('walletBalance', 0))),
                'unrealized_profit': Decimal(str(asset.get('unrealizedProfit', 0))),
                'margin_balance': Decimal(str(asset.get('marginBalance', 0))),
                'maint_margin': Decimal(str(asset.get('maintMargin', 0))),
                'initial_margin': Decimal(str(asset.get('initialMargin', 0))),
                'position_initial_margin': Decimal(str(asset.get('positionInitialMargin', 0))),
                'open_order_initial_margin': Decimal(str(asset.get('openOrderInitialMargin', 0))),
                'cross_wallet_balance': Decimal(str(asset.get('crossWalletBalance', 0))),
                'cross_un_pnl': Decimal(str(asset.get('crossUnPnl', 0))),
                'available_balance': Decimal(str(asset.get('availableBalance', 0))),
                'max_withdraw_amount': Decimal(str(asset.get('maxWithdrawAmount', 0))),
                'margin_available': bool(asset.get('marginAvailable', False)),
                'update_time': int(time.time() * 1000)
            } for asset in account_data.get('assets', [])],
            positions=[{
                'symbol': position.get('symbol', ''),
                'initial_margin': Decimal(str(position.get('initialMargin', 0))),
                'maint_margin': Decimal(str(position.get('maintMargin', 0))),
                'unrealized_profit': Decimal(str(position.get('unrealizedProfit', 0))),
                'position_initial_margin': Decimal(str(position.get('positionInitialMargin', 0))),
                'open_order_initial_margin': Decimal(str(position.get('openOrderInitialMargin', 0))),
                'leverage': int(position.get('leverage', 1)),
                'isolated': bool(position.get('isolated', False)),
                'entry_price': Decimal(str(position.get('entryPrice', 0))),
                'max_notional': Decimal(str(position.get('maxNotional', 0))),
                'position_side': position.get('positionSide', 'BOTH'),
                'position_amt': Decimal(str(position.get('positionAmt', 0))),
                'notional': Decimal(str(position.get('notional', 0))),
                'isolated_wallet': Decimal(str(position.get('isolatedWallet', 0))),
                'update_time': int(time.time() * 1000)
            } for position in account_data.get('positions', [])],
            update_time=int(time.time() * 1000)
        )
