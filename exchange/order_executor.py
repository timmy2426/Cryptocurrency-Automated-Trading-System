from binance.error import ClientError
import logging
from typing import Optional, List, Dict, Union, Any
import time
from decimal import Decimal
from datetime import datetime

from .enums import OrderSide, OrderType, OrderStatus, TimeInForce, PositionStatus, CloseReason, WorkingType
from .data_models import OrderResult, PositionInfo, Order, AccountInfo
from .binance_api import BinanceAPI
from core import check_config_parameters

logger = logging.getLogger(__name__)

class OrderExecutor:
    """訂單執行器"""
    
    def __init__(self, api: BinanceAPI):
        """
        初始化訂單執行器
        
        Args:
            api: BinanceAPI 實例
        """
        self.api = api
        
    def _setup_trading_config(self, symbol: str) -> None:
        """設置交易配置"""
        try:
            # 檢查配置參數
            required_params = [
                'leverage',
                'price_protect'
            ]
            
            config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
            
            # 直接設置槓桿
            self.api.change_leverage(symbol=symbol, leverage=config['leverage'])
                
        except Exception as e:
            logger.error(f"設置交易配置失敗: {str(e)}")
            raise

    def _build_order_params(self, order: Order) -> dict:
        """構建訂單參數"""
        params = {
            'symbol': order.symbol,
            'side': order.side.value,
            'type': order.type.value,
            'quantity': str(order.quantity)
        }
        
        if order.price is not None:
            params['price'] = str(order.price)
            
        if order.stop_price is not None:
            params['stopPrice'] = str(order.stop_price)
            
        if order.working_type is not None:
            params['workingType'] = order.working_type.value
            
        # 只在非市價單時添加 timeInForce 參數
        if order.time_in_force is not None and order.type != OrderType.MARKET:
            params['timeInForce'] = order.time_in_force.value
            
        return params

    def _check_symbol_trading_status(self, symbol: str) -> Dict:
        """
        檢查交易對狀態
        
        Args:
            symbol: 交易對
            
        Returns:
            Dict: 交易對信息
            
        Raises:
            ValueError: 如果交易對不可用
        """
        symbol_info = self.api.get_symbol_info(symbol)
        if symbol_info.get('status') != 'TRADING':
            raise ValueError(f"交易對 {symbol} 當前不可交易")
        return symbol_info
        
    def _check_quantity_limits(self, symbol: str, quantity: Decimal) -> None:
        """
        檢查交易數量限制
        
        Args:
            symbol: 交易對
            quantity: 交易數量
            
        Raises:
            ValueError: 如果數量不符合限制
        """
        lot_size_info = self.api.get_lot_size_info(symbol)
        
        # 檢查數量是否在允許範圍內
        if quantity < lot_size_info['min_qty']:
            raise ValueError(f"交易數量 {quantity} 小於最小允許數量 {lot_size_info['min_qty']}")
        if quantity > lot_size_info['max_qty']:
            raise ValueError(f"交易數量 {quantity} 大於最大允許數量 {lot_size_info['max_qty']}")
            
        # 檢查數量是否符合步長要求
        if (quantity % lot_size_info['step_size']) != 0:
            raise ValueError(f"交易數量 {quantity} 不符合步長要求 {lot_size_info['step_size']}")
            
    def _check_price_limits(self, symbol: str, price: Decimal) -> None:
        """
        檢查價格限制
        
        Args:
            symbol: 交易對
            price: 價格
            
        Raises:
            ValueError: 如果價格不符合限制
        """
        price_info = self.api.get_price_filter_info(symbol)
        
        # 檢查價格是否在允許範圍內
        if price < price_info['min_price']:
            raise ValueError(f"價格 {price} 小於最小允許價格 {price_info['min_price']}")
        if price > price_info['max_price']:
            raise ValueError(f"價格 {price} 大於最大允許價格 {price_info['max_price']}")
            
        # 檢查價格是否符合步長要求
        if (price % price_info['tick_size']) != 0:
            raise ValueError(f"價格 {price} 不符合步長要求 {price_info['tick_size']}")
            
    def _check_stop_price_limits(self, symbol: str, stop_price: Decimal) -> None:
        """
        檢查止損價格限制
        
        Args:
            symbol: 交易對
            stop_price: 止損價格
            
        Raises:
            ValueError: 如果止損價格不符合限制
        """
        price_info = self.api.get_price_filter_info(symbol)
        
        # 檢查止損價格是否在允許範圍內
        if stop_price < price_info['min_price']:
            raise ValueError(f"止損價格 {stop_price} 小於最小允許價格 {price_info['min_price']}")
        if stop_price > price_info['max_price']:
            raise ValueError(f"止損價格 {stop_price} 大於最大允許價格 {price_info['max_price']}")
            
        # 檢查止損價格是否符合步長要求
        if (stop_price % price_info['tick_size']) != 0:
            raise ValueError(f"止損價格 {stop_price} 不符合步長要求 {price_info['tick_size']}")
            
    def _check_order_limits(self, order: Order) -> None:
        """
        檢查訂單限制
        
        Args:
            order: 訂單對象
            
        Raises:
            ValueError: 如果訂單不符合限制
        """
        # 檢查交易對狀態
        self._check_symbol_trading_status(order.symbol)
        
        # 檢查數量限制
        self._check_quantity_limits(order.symbol, order.quantity)
        
        # 檢查最小名義價值
        if order.type == OrderType.MARKET:
            # 獲取當前價格
            current_price = self.api.get_current_price(order.symbol)
            if current_price is None:
                raise ValueError(f"無法獲取 {order.symbol} 的當前價格")
                
            # 獲取最小名義價值要求
            min_notional = self.api.get_min_notional(order.symbol)
            if min_notional is None:
                raise ValueError(f"無法獲取 {order.symbol} 的最小名義價值要求")
                
            notional_value = current_price * order.quantity
            if notional_value < min_notional:
                raise ValueError(f"訂單名義價值 {notional_value} USDT 小於最小要求 {min_notional} USDT")
        
        # 如果是限價單，檢查價格限制
        if order.type in [OrderType.LIMIT, OrderType.STOP, OrderType.TAKE_PROFIT]:
            if not order.price:
                raise ValueError("限價單必須指定價格")
            self._check_price_limits(order.symbol, order.price)
            
        # 如果是止損單，檢查止損價格限制
        if order.type in [OrderType.STOP, OrderType.STOP_MARKET, OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET]:
            if not order.stop_price:
                raise ValueError("止損單必須指定止損價格")
            self._check_stop_price_limits(order.symbol, order.stop_price)

    def open_position_market(self, order: Order) -> OrderResult:
        """市價開倉
        
        Args:
            order: 訂單信息
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            # 設置訂單類型為市價單
            order.type = OrderType.MARKET
            
            # 下單
            order_info = self.api.new_order(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                quantity=order.quantity,
                position_side=order.position_side,
                reduce_only=order.reduce_only,
                close_position=order.close_position,
                working_type=order.working_type,
                price_protect=order.price_protect,
                new_client_order_id=order.new_client_order_id,
                time_in_force=order.time_in_force
            )
            
            # 構建訂單結果
            result = OrderResult(
                symbol=order_info.symbol,
                side=order_info.side,
                type=order_info.type,
                quantity=order_info.quantity,
                transact_time=order_info.transact_time,
                time_in_force=order_info.time_in_force,
                order_id=order_info.order_id,
                client_order_id=order_info.client_order_id,
                price=order_info.price,
                orig_qty=order_info.orig_qty,
                executed_qty=order_info.executed_qty,
                cummulative_quote_qty=order_info.cummulative_quote_qty,
                status=order_info.status,
                iceberg_qty=order_info.iceberg_qty,
                time=order_info.time,
                update_time=order_info.update_time,
                is_working=order_info.is_working,
                orig_quote_order_qty=order_info.orig_quote_order_qty,
                stop_price=order_info.stop_price,
                working_type=order_info.working_type,
                price_protect=order_info.price_protect,
                reduce_only=order_info.reduce_only,
                close_position=order_info.close_position,
                position_side=order_info.position_side,
                price_match=order_info.price_match,
                self_trade_prevention_mode=order_info.self_trade_prevention_mode,
                good_till_date=order_info.good_till_date
            )
            
            return result
            
        except Exception as e:
            logger.error(f"開市價倉位發生錯誤: {str(e)}")
            raise

    def open_position_take_profit(self, order: Order) -> OrderResult:
        """開止盈倉位"""
        try:
            # 設置交易配置
            self._setup_trading_config(order.symbol)
            
            # 檢查訂單限制
            self._check_order_limits(order)
            
            # 構建訂單參數
            order_params = {
                'symbol': order.symbol,
                'side': order.side.value,
                'type': order.type.value,
                'quantity': str(order.quantity),
                'stopPrice': str(order.stop_price),
                'timeInForce': order.time_in_force.value if order.time_in_force else None,
                'reduceOnly': order.reduce_only,
                'closePosition': order.close_position,
                'workingType': order.working_type.value if order.working_type else None,
                'priceProtect': order.price_protect,
                'newClientOrderId': order.new_client_order_id
            }
            
            # 下單
            order_info = self.api.new_order(**order_params)
            
            # 構建訂單結果
            result = OrderResult(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                quantity=order.quantity,
                transact_time=order_info['transactTime'],
                time_in_force=TimeInForce[order_info['timeInForce']],
                order_id=order_info['orderId'],
                client_order_id=order_info['clientOrderId'],
                price=Decimal(str(order_info['price'])) if order_info['price'] != '0' else None,
                orig_qty=Decimal(str(order_info['origQty'])),
                executed_qty=Decimal(str(order_info['executedQty'])),
                cummulative_quote_qty=Decimal(str(order_info['cummulativeQuoteQty'])),
                status=OrderStatus[order_info['status']],
                iceberg_qty=Decimal(str(order_info['icebergQty'])) if order_info['icebergQty'] else None,
                time=order_info['time'],
                update_time=order_info['updateTime'],
                is_working=order_info['isWorking'],
                orig_quote_order_qty=Decimal(str(order_info['origQuoteOrderQty'])) if order_info['origQuoteOrderQty'] else None
            )
            
            return result
            
        except ClientError as e:
            logger.error(f"開止盈倉位失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"開止盈倉位發生錯誤: {str(e)}")
            raise

    def open_position_stop_loss(self, order: Order) -> OrderResult:
        """開止損倉位"""
        try:
            # 設置交易配置
            self._setup_trading_config(order.symbol)
            
            # 檢查訂單限制
            self._check_order_limits(order)
            
            # 構建訂單參數
            order_params = {
                'symbol': order.symbol,
                'side': order.side.value,
                'type': order.type.value,
                'quantity': str(order.quantity),
                'stopPrice': str(order.stop_price),
                'timeInForce': order.time_in_force.value if order.time_in_force else None,
                'reduceOnly': order.reduce_only,
                'closePosition': order.close_position,
                'workingType': order.working_type.value if order.working_type else None,
                'priceProtect': order.price_protect,
                'newClientOrderId': order.new_client_order_id
            }
            
            # 下單
            order_info = self.api.new_order(**order_params)
            
            # 構建訂單結果
            result = OrderResult(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                quantity=order.quantity,
                transact_time=order_info['transactTime'],
                time_in_force=TimeInForce[order_info['timeInForce']],
                order_id=order_info['orderId'],
                client_order_id=order_info['clientOrderId'],
                price=Decimal(str(order_info['price'])) if order_info['price'] != '0' else None,
                orig_qty=Decimal(str(order_info['origQty'])),
                executed_qty=Decimal(str(order_info['executedQty'])),
                cummulative_quote_qty=Decimal(str(order_info['cummulativeQuoteQty'])),
                status=OrderStatus[order_info['status']],
                iceberg_qty=Decimal(str(order_info['icebergQty'])) if order_info['icebergQty'] else None,
                time=order_info['time'],
                update_time=order_info['updateTime'],
                is_working=order_info['isWorking'],
                orig_quote_order_qty=Decimal(str(order_info['origQuoteOrderQty'])) if order_info['origQuoteOrderQty'] else None
            )
            
            return result
            
        except ClientError as e:
            logger.error(f"開止損倉位失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"開止損倉位發生錯誤: {str(e)}")
            raise

    def open_position_trailing(self, order: Order, activation_price: float, callback_rate: float) -> OrderResult:
        """開追蹤止損倉位"""
        try:
            # 設置交易配置
            self._setup_trading_config(order.symbol)
            
            # 檢查訂單限制
            self._check_order_limits(order)
            
            # 構建訂單參數
            order_params = {
                'symbol': order.symbol,
                'side': order.side.value,
                'type': order.type.value,
                'quantity': str(order.quantity),
                'activationPrice': str(activation_price),
                'callbackRate': str(callback_rate),
                'timeInForce': order.time_in_force.value if order.time_in_force else None,
                'reduceOnly': order.reduce_only,
                'closePosition': order.close_position,
                'workingType': order.working_type.value if order.working_type else None,
                'priceProtect': order.price_protect,
                'newClientOrderId': order.new_client_order_id
            }
            
            # 下單
            order_info = self.api.new_order(**order_params)
            
            # 構建訂單結果
            result = OrderResult(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                quantity=order.quantity,
                transact_time=order_info['transactTime'],
                time_in_force=TimeInForce[order_info['timeInForce']],
                order_id=order_info['orderId'],
                client_order_id=order_info['clientOrderId'],
                price=Decimal(str(order_info['price'])) if order_info['price'] != '0' else None,
                orig_qty=Decimal(str(order_info['origQty'])),
                executed_qty=Decimal(str(order_info['executedQty'])),
                cummulative_quote_qty=Decimal(str(order_info['cummulativeQuoteQty'])),
                status=OrderStatus[order_info['status']],
                iceberg_qty=Decimal(str(order_info['icebergQty'])) if order_info['icebergQty'] else None,
                time=order_info['time'],
                update_time=order_info['updateTime'],
                is_working=order_info['isWorking'],
                orig_quote_order_qty=Decimal(str(order_info['origQuoteOrderQty'])) if order_info['origQuoteOrderQty'] else None
            )
            
            return result
            
        except ClientError as e:
            logger.error(f"開追蹤止損倉位失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"開追蹤止損倉位發生錯誤: {str(e)}")
            raise
            
    def get_order_status(self, symbol: str, order_id: str) -> OrderResult:
        """查詢訂單狀態"""
        return self.api.get_order_status(symbol=symbol, order_id=order_id)
        
    def get_all_orders(self, symbol: Optional[str] = None, limit: int = 500) -> List[Order]:
        """查詢所有訂單"""
        return self.api.get_all_orders(symbol, limit)
        
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                    client_order_id: Optional[str] = None) -> Order:
        """取消訂單"""
        return self.api.cancel_order(symbol, order_id, client_order_id)
        
    def cancel_all_orders(self, symbol: str) -> List[Order]:
        """取消所有訂單"""
        return self.api.cancel_all_orders(symbol)
        
    def close_position(self, symbol: str, max_retries: int = 3) -> OrderResult:
        """平倉"""
        try:
            # 獲取當前持倉信息
            position_info = self.api.get_position_risk(symbol)
            if not position_info or position_info['positionAmt'] == 0:
                logger.info(f"沒有找到 {symbol} 的持倉信息或持倉數量為0")
                return None
                
            # 構建平倉訂單
            order = Order(
                symbol=symbol,
                side=OrderSide.SELL if position_info['positionAmt'] > 0 else OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=abs(position_info['positionAmt']),
                reduce_only=True
            )
            
            # 嘗試平倉
            for attempt in range(max_retries):
                try:
                    # 下單
                    order_info = self.api.new_order(
                        symbol=order.symbol,
                        side=order.side.value,
                        type=order.type.value,
                        quantity=str(order.quantity),
                        reduceOnly=order.reduce_only
                    )
                    
                    # 構建訂單結果
                    result = OrderResult(
                        symbol=order.symbol,
                        side=order.side,
                        type=order.type,
                        quantity=order.quantity,
                        transact_time=order_info['transactTime'],
                        time_in_force=TimeInForce[order_info['timeInForce']],
                        order_id=order_info['orderId'],
                        client_order_id=order_info['clientOrderId'],
                        price=Decimal(str(order_info['price'])) if order_info['price'] != '0' else None,
                        orig_qty=Decimal(str(order_info['origQty'])),
                        executed_qty=Decimal(str(order_info['executedQty'])),
                        cummulative_quote_qty=Decimal(str(order_info['cummulativeQuoteQty'])),
                        status=OrderStatus[order_info['status']],
                        iceberg_qty=Decimal(str(order_info['icebergQty'])) if order_info['icebergQty'] else None,
                        time=order_info['time'],
                        update_time=order_info['updateTime'],
                        is_working=order_info['isWorking'],
                        orig_quote_order_qty=Decimal(str(order_info['origQuoteOrderQty'])) if order_info['origQuoteOrderQty'] else None
                    )
                    
                    return result
                    
                except ClientError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"平倉失敗，重試中... ({attempt + 1}/{max_retries})")
                        time.sleep(1)
                    else:
                        logger.error(f"平倉失敗: {str(e)}")
                        raise
                    
        except Exception as e:
            logger.error(f"平倉發生錯誤: {str(e)}")
            raise

    def close_all_positions(self) -> List[OrderResult]:
        """平掉所有倉位"""
        try:
            # 獲取所有持倉信息
            positions = self.api.get_position_risk()
            if not positions:
                logger.info("沒有找到任何持倉")
                return []
                
            results = []
            for position in positions:
                if position['positionAmt'] != 0:
                    try:
                        # 構建平倉訂單
                        order = Order(
                            symbol=position['symbol'],
                            side=OrderSide.SELL if position['positionAmt'] > 0 else OrderSide.BUY,
                            type=OrderType.MARKET,
                            quantity=abs(position['positionAmt']),
                            reduce_only=True
                        )
                        
                        # 下單
                        order_info = self.api.new_order(
                            symbol=order.symbol,
                            side=order.side.value,
                            type=order.type.value,
                            quantity=str(order.quantity),
                            reduceOnly=order.reduce_only
                        )
                        
                        # 構建訂單結果
                        result = OrderResult(
                            symbol=order.symbol,
                            side=order.side,
                            type=order.type,
                            quantity=order.quantity,
                            transact_time=order_info['transactTime'],
                            time_in_force=TimeInForce[order_info['timeInForce']],
                            order_id=order_info['orderId'],
                            client_order_id=order_info['clientOrderId'],
                            price=Decimal(str(order_info['price'])) if order_info['price'] != '0' else None,
                            orig_qty=Decimal(str(order_info['origQty'])),
                            executed_qty=Decimal(str(order_info['executedQty'])),
                            cummulative_quote_qty=Decimal(str(order_info['cummulativeQuoteQty'])),
                            status=OrderStatus[order_info['status']],
                            iceberg_qty=Decimal(str(order_info['icebergQty'])) if order_info['icebergQty'] else None,
                            time=order_info['time'],
                            update_time=order_info['updateTime'],
                            is_working=order_info['isWorking'],
                            orig_quote_order_qty=Decimal(str(order_info['origQuoteOrderQty'])) if order_info['origQuoteOrderQty'] else None
                        )
                        
                        results.append(result)
                        logger.info(f"平倉成功: {position['symbol']}")
                        
                    except Exception as e:
                        logger.error(f"平倉失敗 {position['symbol']}: {str(e)}")
                        continue
                    
            return results
            
        except Exception as e:
            logger.error(f"平掉所有倉位發生錯誤: {str(e)}")
            raise

    def get_position(self, symbol: str = None) -> Union[PositionInfo, List[PositionInfo], None]:
        """獲取倉位信息"""
        try:
            response = self.api.get_position_risk(symbol)
            if not response:
                return None
                
            if symbol:
                # 如果倉位數量為 0，返回 None
                if Decimal(response['positionAmt']) == 0:
                    return None
                    
                return PositionInfo(
                    symbol=response['symbol'],
                    position_amt=Decimal(response['positionAmt']),
                    entry_price=Decimal(response['entryPrice']),
                    mark_price=Decimal(response['markPrice']),
                    un_realized_profit=Decimal(response['unRealizedProfit']),
                    liquidation_price=Decimal(response['liquidationPrice']),
                    leverage=int(response['leverage']),
                    max_notional_value=Decimal(response['maxNotionalValue']),
                    margin_type=response['marginType'],
                    isolated_margin=Decimal(response['isolatedMargin']),
                    is_auto_add_margin=response['isAutoAddMargin']
                )
            else:
                # 過濾掉倉位數量為 0 的倉位
                positions = []
                for pos in response:
                    if Decimal(pos['positionAmt']) != 0:
                        positions.append(PositionInfo(
                            symbol=pos['symbol'],
                            position_amt=Decimal(pos['positionAmt']),
                            entry_price=Decimal(pos['entryPrice']),
                            mark_price=Decimal(pos['markPrice']),
                            un_realized_profit=Decimal(pos['unRealizedProfit']),
                            liquidation_price=Decimal(pos['liquidationPrice']),
                            leverage=int(pos['leverage']),
                            max_notional_value=Decimal(pos['maxNotionalValue']),
                            margin_type=pos['marginType'],
                            isolated_margin=Decimal(pos['isolatedMargin']),
                            is_auto_add_margin=pos['isAutoAddMargin']
                        ))
                return positions if positions else None
                
        except Exception as e:
            logger.error(f"獲取倉位信息失敗: {str(e)}")
            return None
            
    def get_account_info(self) -> AccountInfo:
        """獲取賬戶信息"""
        try:
            account = self.api.get_account_info()
            if not account:
                logger.warning("沒有找到賬戶信息")
                return None
                
            return account
            
        except Exception as e:
            logger.error(f"獲取賬戶信息失敗: {str(e)}")
            raise

    def open_position_limit(self, order: Order) -> OrderResult:
        """開限價倉位
        
        Args:
            order: 訂單信息
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            # 檢查交易對狀態
            self._check_symbol_trading_status(order.symbol)
            
            # 構建訂單參數
            params = self._build_order_params(order)
            
            # 下單
            order_info = self.api.new_order(**params)
            
            # 構建訂單結果
            return OrderResult(
                symbol=order_info.symbol,
                side=order_info.side,
                type=order_info.type,
                quantity=order_info.quantity,
                transact_time=order_info.transact_time,
                time_in_force=order_info.time_in_force,
                order_id=order_info.order_id,
                client_order_id=order_info.client_order_id,
                price=order_info.price,
                orig_qty=order_info.orig_qty,
                executed_qty=order_info.executed_qty,
                cummulative_quote_qty=order_info.cummulative_quote_qty,
                status=order_info.status,
                iceberg_qty=order_info.iceberg_qty,
                time=order_info.time,
                update_time=order_info.update_time,
                is_working=order_info.is_working,
                orig_quote_order_qty=order_info.orig_quote_order_qty,
                stop_price=order_info.stop_price,
                working_type=order_info.working_type,
                price_protect=order_info.price_protect,
                reduce_only=order_info.reduce_only,
                close_position=order_info.close_position,
                activation_price=order_info.activation_price,
                callback_rate=order_info.callback_rate,
                position_side=order_info.position_side,
                price_match=order_info.price_match,
                self_trade_prevention_mode=order_info.self_trade_prevention_mode,
                good_till_date=order_info.good_till_date
            )
            
        except Exception as e:
            logger.error(f"開限價倉位發生錯誤: {str(e)}")
            raise

    def _handle_position_update(self, response: Dict) -> None:
        """處理倉位更新
        
        Args:
            response: API 響應
        """
        try:
            if Decimal(response.get('positionAmt', '0')) == 0:
                return
                
            position = PositionInfo(
                symbol=response.get('symbol'),
                position_amt=Decimal(response.get('positionAmt', '0')),
                entry_price=Decimal(response.get('entryPrice', '0')),
                mark_price=Decimal(response.get('markPrice', '0')),
                un_realized_profit=Decimal(response.get('unRealizedProfit', '0')),
                liquidation_price=Decimal(response.get('liquidationPrice', '0')),
                leverage=int(response.get('leverage', 1)),
                max_notional_value=Decimal(response.get('maxNotionalValue', '0')),
                margin_type=response.get('marginType', 'isolated'),
                isolated_margin=Decimal(response.get('isolatedMargin', '0')),
                is_auto_add_margin=response.get('isAutoAddMargin', False)
            )
            
            self._update_position(position)
            
        except Exception as e:
            logger.error(f"處理倉位更新失敗: {str(e)}")
            raise
