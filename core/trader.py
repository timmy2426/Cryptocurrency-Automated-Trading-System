import logging
import time
from typing import List
from decimal import Decimal
import pandas as pd

from exchange import OrderExecutor
from core.position_manager import PositionManager
from core.strategy import Strategy
from core.signals import SignalGenerator
from core.risk_control import RiskControl
from utils.config import check_config_parameters
from data.data_loader import DataLoader
from exchange.data_models import Order
from exchange.enums import OrderSide, OrderType, OrderStatus

logger = logging.getLogger(__name__)

class Trader:
    """交易執行器"""
    
    def __init__(
        self,
        order_executor: OrderExecutor,
        symbol_list: List[str],
        position_manager: PositionManager,
        data_loader: DataLoader
    ):
        """
        初始化交易執行器
        
        Args:
            order_executor: 訂單執行器實例
            symbol_list: 交易對列表
            position_manager: 倉位管理器實例
            data_loader: 數據加載器實例
        """
        self.order_executor = order_executor
        self.symbol_list = symbol_list
        self.position_manager = position_manager
        self.data_loader = data_loader
        self.strategy = Strategy(position_manager)
        self.signal_generator = SignalGenerator()
        
        # 加載配置參數
        self._load_config()
        
    def _load_config(self) -> None:
        """加載配置參數"""
        try:
            # 檢查配置參數
            required_params = [
                'max_loss_percent',
                'activate_price_rate',
                'trailing_percent',
                'mean_reversion_sl',
                'mean_reversion_tp'
            ]
            
            self.config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in self.config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
                
        except Exception as e:
            logger.error(f"加載配置參數失敗: {str(e)}")
            raise
        
    def run(self) -> None:
        """執行交易邏輯"""
        try:
            # 更新帳戶信息
            self.position_manager.update_account_info()
            positions = self.position_manager.account_info.get('positions', [])
            time.sleep(10) # 等待平台伺服器K線結算完成
            
            # 處理已存在的倉位
            for symbol in self.symbol_list:
                if symbol in positions:
                    self._handle_existing_position(symbol)
                    
            # 檢查全帳號的風險控制
            if not self.position_manager.can_open_position():
                logger.info("帳號風險控制檢查未通過，跳過本輪交易檢查")
                return
                
            # 處理開倉邏輯
            for symbol in self.symbol_list:
                if symbol not in positions:
                    self._process_open_position(symbol)

            logger.info("交易檢查完成")
                    
        except Exception as e:
            logger.error(f"交易執行失敗: {str(e)}")
            raise
            
    def _get_klines(self, symbol: str, interval: str = '1h') -> pd.DataFrame:
        """
        獲取K線數據
        
        Args:
            symbol: 交易對
            interval: 時間週期，默認為1小時
            
        Returns:
            pd.DataFrame: K線數據
        """
        try:
            return self.data_loader.load_klines(symbol, interval)
        except Exception as e:
            logger.error(f"獲取K線數據失敗: {str(e)}")
            raise
            
    def _handle_existing_position(self, symbol: str) -> None:
        """處理已存在的倉位"""
        try:
            # 獲取當前倉位資訊
            position = self.position_manager.positions[symbol]
            logger.info(f"倉位 {symbol} 資訊: {position}")
            # 獲取K線數據
            df_1h = self._get_klines(symbol)
            indicators = self.signal_generator.calculate_indicators(df_1h)

            # 根據開倉策略檢查出場信號
            logger.info('-' * 100)
            logger.info(f"檢查 {symbol} 平倉信號")
            logger.info(f"收盤價格: {df_1h['close'].iloc[-2]}")

            should_close = False
            is_trend = position['strategy'].startswith("trend")
            if position['strategy'] != None:
                if is_trend:
                    if position['side'] == "BUY":
                        should_close = self.signal_generator.is_trend_long_exit(df_1h, indicators).iloc[-2]
                    else:
                        should_close = self.signal_generator.is_trend_short_exit(df_1h, indicators).iloc[-2]
                else:  # mean_reversion
                    if position['side'] == "BUY":
                        should_close = self.signal_generator.is_mean_rev_long_exit(df_1h, indicators).iloc[-2]
                    else:
                        should_close = self.signal_generator.is_mean_rev_short_exit(df_1h, indicators).iloc[-2]

            # 檢查倉位管理條件
            close_position = self.position_manager.can_close_position(symbol, is_trend)

            # 開倉不完整的自我修正機制
            if (self.position_manager.positions[symbol]['open_time'] == None or
                self.position_manager.positions[symbol]['strategy'] == None or
                self.position_manager.positions[symbol]['stop_loss'] == None):
                should_close = True
                logger.info(f"{symbol} 開倉不完整，強制平倉")
            
            logger.info('-' * 100)

            # 如果出場信號為真或倉位管理器建議平倉，則執行平倉
            if should_close or close_position:
                # 執行市價平倉
                order_result = self.order_executor.close_position(symbol)
                
                # 等待倉位完全更新
                time.sleep(1)
                max_retries = 60
                retry_count = 0
                while retry_count < max_retries:
                    # 檢查倉位狀態
                    order_status = self.order_executor.get_order_status(symbol, order_result.order_id)
                    
                    if order_status.status == OrderStatus.FILLED:
                        self.position_manager.update_position_info(order_status)
                        logger.info(f"{symbol} 訂單已完全成交")
                        break
                    elif order_status.status in [OrderStatus.CANCELED, OrderStatus.EXPIRED]:
                        if order_status.executed_qty != Decimal('0'):
                            logger.info(f"{symbol} 訂單部分成交，其餘已取消或過期")
                            break
                    else:
                        logger.error(f"平倉訂單 {order_result.order_id} 狀態異常: {order_status}")
                        return
                    
                    logger.info(f"等待平倉訂單成交，當前狀態: {order_status}")
                    time.sleep(1)
                    retry_count += 1
                else:
                    logger.error(f"{symbol} 倉位在 {max_retries} 秒內未成交")
                    return
                
                self.position_manager.close_position_complete(symbol)

        except Exception as e:
            logger.error(f"處理倉位 {symbol} 時發生錯誤: {str(e)}")
            
    def _process_open_position(self, symbol: str) -> None:
        """處理開倉邏輯"""
        try:
            # 獲取多個時間框架的K線數據
            df_1h = self._get_klines(symbol, '1h')
            df_4h = self._get_klines(symbol, '4h')
            df_1d = self._get_klines(symbol, '1d')
            
            # 檢查開倉信號
            logger.info('-' * 100)
            logger.info(f"檢查 {symbol} 開倉信號")
            logger.info(f"收盤價格: {df_1h['close'].iloc[-2]}， 成交量: {df_1h['volume'].iloc[-2]}")

            selected_strategy = self.strategy.select(symbol, df_1h, df_4h, df_1d)

            logger.info(f"倉位 {symbol} 開倉信號: {selected_strategy}")
            logger.info('-' * 100)

            if selected_strategy == "no_trade":
                return
                
            # 執行開倉
            self._open_position(symbol, selected_strategy, df_1h, df_4h, df_1d)
            
        except Exception as e:
            logger.error(f"處理開倉 {symbol} 失敗: {str(e)}")
            
    def _open_position(self, symbol: str, selected_strategy: str, df_1h: pd.DataFrame, df_4h: pd.DataFrame, df_1d: pd.DataFrame) -> None:
        """執行開倉操作"""
        try:
            # 計算倉位大小
            is_trend = selected_strategy.startswith("trend")
            position_size = self.position_manager.calculate_position_size(
                symbol=symbol,
                is_trend=is_trend,
                df=df_1h
            )
            
            # 創建市價開倉訂單
            order = Order(
                symbol=symbol,
                side=OrderSide.BUY if selected_strategy.endswith("long") else OrderSide.SELL,
                type=OrderType.MARKET,
                quantity=position_size
            )
            
            # 執行市價開倉
            order_result = self.order_executor.open_position_market(order)

            # 更新倉位信息
            self.position_manager.update_position_info(order_result, {'strategy': selected_strategy})
            logger.info(f"倉位策略： {self.position_manager.positions[symbol]['strategy']}")

            # 等待訂單完全成交
            time.sleep(1)
            max_retries = 60
            retry_count = 0
            while retry_count < max_retries:
                # 檢查訂單狀態
                order_status = self.order_executor.get_order_status(symbol, order_result.order_id)
                
                if order_status.status == OrderStatus.FILLED:
                    self.position_manager.update_position_info(order_status)
                    logger.info(f"{symbol} 訂單已完全成交")
                    break
                elif order_status.status in [OrderStatus.CANCELED, OrderStatus.EXPIRED]:
                    if order_status.executedQty != Decimal('0'):
                        logger.info(f"{symbol} 訂單部分成交，其餘已取消或過期")
                        break
                    else:
                        logger.error(f"開倉訂單 {order_result.order_id} 狀態異常: {order_status}")
                        return
                
                logger.info(f"等待開倉訂單成交，當前狀態: {order_status}")
                time.sleep(1)
                retry_count += 1
            else:
                logger.error(f"{symbol} 倉位在 {max_retries} 秒內未成交")
                return

            # 記錄市場條件
            self.position_manager.record_market_condition(symbol, df_1h, df_4h, df_1d)

            # 獲取開倉價格
            open_price = self.position_manager.positions[symbol]['open_price']
            
            if is_trend:
                self._set_trend_stop_orders(symbol, open_price, selected_strategy)
            else:
                self._set_mean_reversion_stop_orders(symbol, open_price, selected_strategy)

        except Exception as e:
            logger.error(f"開倉失敗: {str(e)}")
            
    def _set_trend_stop_orders(self, symbol: str, open_price: Decimal, selected_strategy: str) -> None:
        """設置順勢單的止損止盈"""
        try:
            # 計算止損價格
            if selected_strategy.endswith("long"):
                stop_loss_multiplier = Decimal('1') - Decimal(str(self.config['max_loss_percent']))
                stop_loss_price = open_price * stop_loss_multiplier
            else:
                stop_loss_multiplier = Decimal('1') + Decimal(str(self.config['max_loss_percent']))
                stop_loss_price = open_price * stop_loss_multiplier
            
            # 設置止損單
            stop_loss_order = Order(
                symbol=symbol,
                side=OrderSide.SELL if self.position_manager.positions[symbol]['side'] == "BUY" else OrderSide.BUY,
                type=OrderType.STOP_MARKET,
                stop_price=stop_loss_price,
                close_position=True
            )
            stop_loss_order_result = self.order_executor.open_position_stop_loss(stop_loss_order)

            # 更新倉位信息
            self.position_manager.update_position_info(stop_loss_order_result, {'stop_loss': stop_loss_price})
            
            # 計算激活價格
            if selected_strategy.endswith("long"):
                activate_price_multiplier = Decimal('1') + Decimal(str(self.config['activate_price_rate']))
                activate_price = open_price * activate_price_multiplier
            else:
                activate_price_multiplier = Decimal('1') - Decimal(str(self.config['activate_price_rate']))
                activate_price = open_price * activate_price_multiplier
            
            # 設置移動止損
            trailing_stop_order = Order(
                symbol=symbol,
                side=OrderSide.SELL if self.position_manager.positions[symbol]['side'] == "BUY" else OrderSide.BUY,
                type=OrderType.TRAILING_STOP_MARKET,
                quantity=abs(self.position_manager.positions[symbol]['open_amt']),
                activate_price=activate_price,
                price_rate=Decimal(str(self.config['trailing_percent'])),
                reduce_only=True
            )
            trailing_stop_order_result = self.order_executor.open_position_trailing(trailing_stop_order)

            # 更新倉位信息
            self.position_manager.update_position_info(
                trailing_stop_order_result, 
                {'trailing_stop': activate_price, 'price_rate': Decimal(str(self.config['trailing_percent']))})
            
            self.position_manager.open_position_complete(symbol)
            
            logger.info(f"倉位 {symbol} 止損止盈設定完成")
        except Exception as e:
            logger.error(f"設置順勢單止損止盈失敗: {str(e)}")
        
    def _set_mean_reversion_stop_orders(self, symbol: str, open_price: Decimal, selected_strategy: str) -> None:
        """設置逆勢單的止損止盈"""
        try:
            # 計算止損價格
            if selected_strategy.endswith("long"):
                stop_loss_multiplier = Decimal('1') - Decimal(str(self.config['mean_reversion_sl']))
                stop_loss_price = open_price * stop_loss_multiplier
            else:
                stop_loss_multiplier = Decimal('1') + Decimal(str(self.config['mean_reversion_sl']))
                stop_loss_price = open_price * stop_loss_multiplier
            
            # 設置止損單
            stop_loss_order = Order(
                symbol=symbol,
                side=OrderSide.SELL if self.position_manager.positions[symbol]['side'] == "BUY" else OrderSide.BUY,
                type=OrderType.STOP_MARKET,
                stop_price=stop_loss_price,
                close_position=True
            )
            stop_loss_order_result = self.order_executor.open_position_stop_loss(stop_loss_order)

            # 更新倉位信息
            self.position_manager.update_position_info(stop_loss_order_result, {'stop_loss': stop_loss_price})
            
            # 計算止盈價格
            if selected_strategy.endswith("long"):
                take_profit_multiplier = Decimal('1') + Decimal(str(self.config['mean_reversion_tp']))
                take_profit_price = open_price * take_profit_multiplier
            else:
                take_profit_multiplier = Decimal('1') - Decimal(str(self.config['mean_reversion_tp']))
                take_profit_price = open_price * take_profit_multiplier
            
            # 設置止盈單
            take_profit_order = Order(
                symbol=symbol,
                side=OrderSide.SELL if self.position_manager.positions[symbol]['side'] == "BUY" else OrderSide.BUY,
                type=OrderType.TAKE_PROFIT_MARKET,
                stop_price=take_profit_price,
                close_position=True
            )
            take_profit_order_result = self.order_executor.open_position_take_profit(take_profit_order)

            # 更新倉位信息
            self.position_manager.update_position_info(take_profit_order_result, {'take_profit': take_profit_price})

            self.position_manager.open_position_complete(symbol)

            logger.info(f"倉位 {symbol} 止損止盈設定完成")
        except Exception as e:
            logger.error(f"設置逆勢單止損止盈失敗: {str(e)}")