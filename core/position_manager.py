import logging
from threading import Lock
from typing import Dict, Optional, List, Any, Union, Callable, TYPE_CHECKING
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, time as dt_time
import time
import pandas as pd

from .event_logger import EventLogger
from exchange import (
    OrderExecutor,
    PositionInfo,
    Order,
    OrderResult,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionStatus,
    CloseReason,
    BinanceConverter
)
from utils.config import check_config_parameters
from data.indicators import TechnicalIndicators

if TYPE_CHECKING:
    from discord_bot import MessageFormatter, SendMessage

logger = logging.getLogger(__name__)

class PositionManager:
    """倉位管理器"""
    
    def __init__(self, order_executor: OrderExecutor, 
                message_formatter: 'MessageFormatter' = None,
                send_message: 'SendMessage' = None):
        """
        初始化倉位管理器
        
        Args:
            order_executor: 訂單執行器實例
            message_formatter: Discord 消息格式化器實例
            send_message: Discord 消息發送器實例
        """
        self.order_executor = order_executor
        self.message_formatter = message_formatter
        self.send_message = send_message
        self.event_logger = EventLogger()
        self.lock = Lock()
        self.consecutive_losses = 0  # 連續虧損次數
        self.cooldown_start_time = 0  # 冷卻期開始時間
        self.is_cooldown_activate = False  # 冷卻期是否激活
        
        # 初始化帳戶信息字典
        self.account_info = {
            'status': None,
            'environment': None,
            'account_equity': Decimal('0'),
            'daily_trades': 0,
            'daily_pnl': Decimal('0'),
            'unrealized_pnl': Decimal('0'),
            'unrealized_pnl_percentage': Decimal('0'),
            'positions': []
        }

        # 初始化倉位信息字典模板
        self._position_template = {
            'symbol': None,
            'side': None,
            'strategy': None,
            'open_time': None,
            'close_time': None,
            'open_price': Decimal('0'),
            'open_amt': Decimal('0'),
            'open_size': Decimal('0'),
            'close_price': Decimal('0'),
            'close_amt': Decimal('0'),
            'close_size': Decimal('0'),
            'close_reason': None,
            'stop_loss': None,
            'take_profit': None,
            'trailing_stop': None,
            'price_rate': None,
            'pnl': Decimal('0'),
            'pnl_percentage': Decimal('0'),
            'is_open_message_sent': False,
            'is_close_message_sent': False
        }
        
        # 初始化倉位信息字典
        self.positions = {}
        
        # 設置為當天凌晨0點
        now = datetime.now()
        midnight = datetime.combine(now.date(), dt_time.min)
        self.last_reset_time = int(midnight.timestamp())
        
        # 加載配置參數
        self._load_config()
        
    def _load_config(self) -> None:
        """加載配置參數"""
        try:
            # 檢查配置參數
            required_params = [
                'symbol_list',
                'max_margin_usage',
                'max_daily_loss',
                'max_daily_trades',
                'consecutive_losses',
                'cooldown_period',
                'max_holding_bars',
                'risk_per_trade',
                'max_loss_percent',
                'mean_reversion_sl',
                'slippage_percent'
            ]
            
            self.config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in self.config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
                
        except Exception as e:
            logger.error(f"加載配置參數失敗: {str(e)}")
            raise
            
    def _reset_daily_data(self) -> None:
        """重置單日累計數據"""
        current_time = int(time.time())
        # 將當前時間轉換為datetime對象
        now = datetime.fromtimestamp(current_time)
        # 設置為當天凌晨0點
        midnight = datetime.combine(now.date(), dt_time.min)
        midnight_timestamp = int(midnight.timestamp())
        
        # 將上次重置時間轉換為datetime對象
        last_reset_date = datetime.fromtimestamp(self.last_reset_time).date()
        
        # 如果當前日期大於上次重置的日期，進行重置
        if now.date() > last_reset_date:
            self.account_info['daily_pnl'] = Decimal('0')
            self.account_info['daily_trades'] = 0
            self.last_reset_time = midnight_timestamp
            logger.info("重置單日累計數據")

    def _match_precision(self, value: Decimal, reference: Decimal) -> Decimal:
        """
        將 value 的小數精度調整為 reference 的精度
        """
        ref_str = format(reference, 'f')  # 避免科學記號
        if '.' in ref_str:
            precision = Decimal('1e-{}'.format(len(ref_str.split('.')[-1])))
            return value.quantize(precision, rounding=ROUND_HALF_UP)
        else:
            return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    def update_account_info(self, update_config: Optional[Dict[str, Any]] = None) -> None:
        """
        更新帳戶信息
        
        Args:
            update_config: 更新配置字典，包含以下可選鍵：
                - status: 機器人狀態
                - environment: 運行環境
        """
        try:
            # 獲取帳戶信息
            account_info = self.order_executor.get_account_info()
            if not account_info:
                logger.error("無法獲取帳戶信息")
                return
                
            # 更新狀態和環境（如果提供）
            if update_config:
                if 'status' in update_config:
                    self.account_info['status'] = update_config['status']
                if 'environment' in update_config:
                    self.account_info['environment'] = update_config['environment']
                
            # 更新帳戶權益
            self.account_info['account_equity'] = account_info.total_wallet_balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # 更新單日累計盈虧
            self.account_info['daily_pnl'] = self.account_info['daily_pnl'].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # 更新未實現盈虧
            self.account_info['unrealized_pnl'] = account_info.total_unrealized_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # 計算並更新未實現盈虧率
            if account_info.total_wallet_balance != 0:
                self.account_info['unrealized_pnl_percentage'] = (
                    (account_info.total_unrealized_profit / account_info.total_wallet_balance * 100)
                    .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                )
            else:
                self.account_info['unrealized_pnl_percentage'] = Decimal('0')
                
            # 更新持倉交易對列表
            self.account_info['positions'] = [
                position['symbol'] 
                for position in account_info.positions 
                if float(position.get('position_amt', 0)) != 0
            ]
            
            logger.info("帳戶信息更新成功")
            logger.info(f"帳戶信息: {self.account_info}")
            
        except Exception as e:
            logger.error(f"更新帳戶信息失敗: {str(e)}")
            raise

    def check_account_info(self) -> Dict[str, Any]:
        """
        獲取帳戶信息
        """
        try:
            if not self.account_info:
                raise ValueError("帳戶信息未初始化")
                
            return self.account_info
            
        except Exception as e:
            logger.error(f"獲取帳戶信息失敗: {str(e)}")
            raise

    def update_position_info(
        self, 
        position_data: Union[OrderResult, Order],
        update_config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        更新倉位信息
        
        Args:
            position_data: OrderResult 或 Order 對象，包含倉位信息
            update_config: 更新配置字典
        """
        try:
            # 獲取交易對
            symbol = position_data.symbol
            if not symbol:
                logger.error("無法獲取交易對信息")
                return
            
            # 檢查交易對是否在標的列表中
            if symbol not in self.config['symbol_list']:
                logger.info(f"交易對 {symbol} 不在標的列表中，跳過紀錄倉位信息")
                return
                
            # 如果倉位不存在，創建新的倉位信息字典
            if symbol not in self.positions:
                self.positions[symbol] = self._position_template.copy()  # 使用模板創建新的字典
                self.positions[symbol]['symbol'] = symbol  # 更新交易對

            # 更新訂單結果
            if isinstance(position_data, Order) and position_data.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
                if position_data.reduce_only  or position_data.close_position: # 平倉單成交
                    self.positions[symbol]['side'] = position_data.side.value
                    self.positions[symbol]['close_time'] = position_data.timestamp
                    self.positions[symbol]['close_reason'] = BinanceConverter.get_close_reason(position_data)
                    if self.positions[symbol]['close_price'] == Decimal('0'):
                        self.positions[symbol]['close_price'] = position_data.avg_price
                        self.positions[symbol]['close_amt'] = position_data.last_filled_qty
                    elif abs(position_data.executed_qty) > abs(self.positions[symbol]['close_amt']):
                        total_cost = self.positions[symbol]['close_price'] * self.positions[symbol]['close_amt'] + position_data.avg_price * position_data.last_filled_qty
                        self.positions[symbol]['close_amt'] += position_data.last_filled_qty
                        self.positions[symbol]['close_price'] = self._match_precision(total_cost / self.positions[symbol]['close_amt'], position_data.avg_price)
                    self.positions[symbol]['close_size'] = self._match_precision(self.positions[symbol]['close_amt'] * self.positions[symbol]['close_price'], position_data.last_filled_qty)
                    self.positions[symbol]['close_size'] *= Decimal('-1') if self.positions[symbol]['side'] == 'SELL' else Decimal('1')
                    self.positions[symbol]['pnl'] += position_data.realized_profit
                    if self.positions[symbol]['close_size'] != Decimal('0') and self.positions[symbol]['pnl'] != Decimal('0'):
                        self.positions[symbol]['pnl_percentage'] = (
                            (self.positions[symbol]['pnl'] / abs(self.positions[symbol]['close_size'])) * Decimal('100')
                            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    
                else: # 開倉單成交
                    self.positions[symbol]['side'] = position_data.side.value
                    self.positions[symbol]['open_time'] = position_data.timestamp
                    if self.positions[symbol]['open_price'] == Decimal('0'):
                        self.positions[symbol]['open_price'] = position_data.avg_price
                        self.positions[symbol]['open_amt'] = position_data.last_filled_qty
                    else:
                        total_cost = self.positions[symbol]['open_price'] * self.positions[symbol]['open_amt'] + position_data.avg_price * position_data.last_filled_qty
                        self.positions[symbol]['open_amt'] += position_data.last_filled_qty
                        self.positions[symbol]['open_price'] = self._match_precision(total_cost / self.positions[symbol]['open_amt'], position_data.avg_price)
                    self.positions[symbol]['open_size'] = self._match_precision(self.positions[symbol]['open_amt'] * self.positions[symbol]['open_price'], position_data.last_filled_qty)
                    self.positions[symbol]['open_size'] *= Decimal('-1') if self.positions[symbol]['side'] == 'SELL' else Decimal('1')

            # 更新開倉信息
            if update_config and 'strategy' in update_config:
                self.positions[symbol]['strategy'] = update_config['strategy']
            if update_config and 'stop_loss' in update_config:
                self.positions[symbol]['stop_loss'] = update_config['stop_loss']
            if update_config and 'take_profit' in update_config:
                self.positions[symbol]['take_profit'] = update_config['take_profit']
            if update_config and 'trailing_stop' in update_config:
                self.positions[symbol]['trailing_stop'] = update_config['trailing_stop']
            if update_config and 'price_rate' in update_config:
                self.positions[symbol]['price_rate'] = update_config['price_rate']

            logger.info(f"更新倉位信息成功: {symbol}")
            logger.info(f"倉位信息: {self.positions[symbol]}")
                
            # 判斷開倉/平倉是否完成
            if position_data.status == OrderStatus.FILLED:
                if position_data.reduce_only or position_data.close_position:
                    self.close_position_complete(symbol)
                elif self.positions[symbol]['strategy'] and self.positions[symbol]['stop_loss']:
                    if self.positions[symbol]['take_profit'] or self.positions[symbol]['trailing_stop']:
                        self.open_position_complete(symbol)
            elif position_data.status in [OrderStatus.CANCELED, OrderStatus.EXPIRED]:
                if position_data.executed_qty:
                    if position_data.reduce_only or position_data.close_position:
                        self.close_position_complete(symbol)
                    elif self.positions[symbol]['strategy'] and self.positions[symbol]['stop_loss']:
                        if self.positions[symbol]['take_profit'] or self.positions[symbol]['trailing_stop']:
                            self.open_position_complete(symbol)
        
        except Exception as e:
            logger.error(f"更新倉位信息失敗: {str(e)}")
            raise

    def check_position_info(self, symbol: str) -> Dict[str, Any]:
        """
        查詢特定交易對的倉位信息
        
        Args:
            symbol: 交易對名稱
            
        Returns:
            Dict[str, Any]: 倉位信息字典，如果交易對不存在則返回 None
        """
        try:
            if symbol not in self.positions:
                logger.warning(f"交易對 {symbol} 不存在")
                return None
                
            return self.positions[symbol]
            
        except Exception as e:
            logger.error(f"查詢倉位信息失敗: {str(e)}")
            raise
        
    def delete_position_info(self, symbol: str) -> None:
        """
        刪除特定交易對的倉位信息
        
        Args:
            symbol: 交易對名稱
        """
        try:
            if symbol not in self.positions:
                logger.warning(f"交易對 {symbol} 不存在，無需刪除")
                return
                
            # 刪除倉位信息
            del self.positions[symbol]
            logger.info(f"成功刪除交易對 {symbol} 的倉位信息")
            
        except Exception as e:
            logger.error(f"刪除倉位信息失敗: {str(e)}")
            raise

    def open_position_complete(self, symbol: str) -> None:
        """
        開倉完成
        
        Args:
            symbol: 交易對
        """
        try:
            # 檢查交易對是否存在
            if symbol not in self.positions:
                logger.error(f"交易對 {symbol} 不存在")
                return
            
            with self.lock:
                if self.positions[symbol]['is_open_message_sent'] == True:
                    logger.info(f"交易對 {symbol} 已發送開倉消息，無需重複發送")
                    return
                    
                # 更新每日開倉數量
                self.account_info['daily_trades'] += 1

                # 創建開倉消息
                embed = self.message_formatter.create_open_position_message(
                    symbol=self.positions[symbol]['symbol'],
                    side=self.positions[symbol]['side'],
                    strategy=self.positions[symbol]['strategy'],
                    open_time=self.positions[symbol]['open_time'],
                    open_price=self.positions[symbol]['open_price'],
                    position_size=self.positions[symbol]['open_size'],
                    stop_loss=self.positions[symbol].get('stop_loss'),
                    take_profit=self.positions[symbol].get('take_profit'),
                    trailing_stop=self.positions[symbol].get('trailing_stop'),
                    price_rate=self.positions[symbol].get('price_rate')
                )
                
                # 發送開倉消息
                self.send_message.send_open_position_message(embed)
                logger.info(f"成功發送交易對 {symbol} 的開倉消息")

                # 設置開倉消息已發送標記
                self.positions[symbol]['is_open_message_sent'] = True

        except Exception as e:
            logger.error(f"開倉完成失敗: {str(e)}")
            raise

    def close_position_complete(self, symbol: str) -> None:
        """
        平倉完成
        
        Args:
            symbol: 交易對
        """
        try:
            # 檢查交易對是否存在
            if symbol not in self.positions:
                logger.error(f"交易對 {symbol} 不存在")
                return
            
            with self.lock:
                if self.positions[symbol]['is_close_message_sent'] == True:
                    logger.info(f"交易對 {symbol} 已發送平倉消息，無需重複發送")
                    return
                
                current_time = int(time.time() * 1000)

                # 紀錄盈虧並檢查是否為虧損平倉
                self.account_info['daily_pnl'] += self.positions[symbol]['pnl']
                if self.positions[symbol]['pnl'] < 0:
                    self.consecutive_losses += 1
                    if self.consecutive_losses >= self.config['consecutive_losses']:
                        self.cooldown_start_time = current_time
                        self.is_cooldown_activate = True
                        logger.info(f"連續虧損達到 {self.config['consecutive_losses']} 次，進入冷卻期")
                else:
                    self.consecutive_losses = 0

                # 創建平倉消息
                embed = self.message_formatter.create_close_position_message(
                    symbol=self.positions[symbol]['symbol'],
                    side=self.positions[symbol]['side'],
                    strategy=self.positions[symbol]['strategy'],
                    open_time=self.positions[symbol]['open_time'],
                    close_time=self.positions[symbol]['close_time'],
                    open_price=self.positions[symbol]['open_price'],
                    close_price=self.positions[symbol]['close_price'],
                    close_reason=self.positions[symbol]['close_reason'],
                    position_size=self.positions[symbol]['close_size'],
                    pnl=self.positions[symbol]['pnl'],
                    pnl_percentage=self.positions[symbol]['pnl_percentage']
                )
                
                # 發送平倉消息
                self.send_message.send_close_position_message(embed)
                logger.info(f"成功發送交易對 {symbol} 的平倉消息")

                # 設置平倉消息已發送標記
                self.positions[symbol]['is_close_message_sent'] = True

                # 使用 EventLogger 記錄倉位信息
                self.event_logger.trade_log(self.positions[symbol])
                logger.info(f"成功記錄交易對 {symbol} 的倉位信息")

                # 取消該交易對的所有未成交訂單
                canceled_orders = self.order_executor.cancel_all_orders(symbol)
                logger.info(f"取消 {symbol} 的未成交訂單: {len(canceled_orders)} 個")

                # 刪除倉位信息
                self.delete_position_info(symbol)

        except Exception as e:
            logger.error(f"平倉完成失敗: {str(e)}")
            raise

    def check_margin_usage(self) -> bool:
        """
        檢查保證金使用比率
        
        Returns:
            bool: 是否小於最大保證金使用比率
        """
        try:
            account_info = self.order_executor.get_account_info()
            margin_usage = account_info.total_position_initial_margin / account_info.total_wallet_balance
            return margin_usage <= Decimal(str(self.config['max_margin_usage']))
        
        except Exception as e:
            logger.error(f"檢查保證金使用比率失敗: {str(e)}")
            return False
            
    def check_daily_pnl(self) -> bool:
        """
        檢查單日累計盈虧
        
        Returns:
            bool: 是否小於最大單日虧損
        """
        try:
            #計算最大允許虧損金額
            max_daily_loss = self.account_info['account_equity'] * Decimal(str(self.config['max_daily_loss']))
        
            # 檢查單日累計虧損金額
            if self.account_info['daily_pnl'] < -max_daily_loss:
                logger.warning(f"單日累計虧損超過限制: {self.account_info['daily_pnl']}")
                return False
                
            return True
        
        except Exception as e:
            logger.error(f"檢查單日累計盈虧失敗: {str(e)}")
            return False
            
    def check_daily_trades(self) -> bool:
        """
        檢查單日累計開倉數量
        
        Returns:
            bool: 是否小於最大單日交易次數
        """
        try:
            self._reset_daily_data()
            return self.account_info['daily_trades'] < self.config['max_daily_trades']
        
        except Exception as e:
            logger.error(f"檢查單日累計開倉數量失敗: {str(e)}")
            return False
            
    def check_cooldown(self) -> bool:
        """
        檢查是否處於冷卻期
        
        Returns:
            bool: 是否不在冷卻期
        """
        try:
            current_time = int(time.time() * 1000)
            if self.is_cooldown_activate:
                if current_time - self.cooldown_start_time < self.config['cooldown_period'] * 1000:
                    return False
                else:
                    self.consecutive_losses = 0
                    self.cooldown_start_time = 0
                    self.is_cooldown_activate = False
                    logger.info(f"冷卻期結束")
            return True
        
        except Exception as e:
            logger.error(f"檢查冷卻期失敗: {str(e)}")
            return False
            
    def check_holding_period(self, symbol: str) -> bool:
        """
        檢查倉位存續期
        
        Args:
            symbol: 交易對
            
        Returns:
            bool: 是否小於最大持倉時間
        """
        try:
            if symbol not in self.positions:
                return False
                
            current_time = int(time.time() * 1000)
            holding_time = current_time - self.positions[symbol]['open_time']
            return holding_time <= self.config['max_holding_bars'] * 15 * 60 * 1000  # 轉換為毫秒
        
        except Exception as e:
            logger.error(f"檢查倉位存續期失敗: {str(e)}")
            return False
            
    def calculate_position_size(self, symbol: str, is_trend: bool, df: pd.DataFrame) -> Decimal:
        """
        計算倉位大小
        
        Args:
            symbol: 交易對
            is_trend: 是否為順勢單
            df: 包含K線數據的DataFrame
            
        Returns:
            Decimal: 倉位大小
        """
        try:
            current_price = self.order_executor.get_current_price(symbol)

            base_size = (self.account_info['account_equity'] * Decimal(str(self.config['risk_per_trade']))) / (
                Decimal(str(self.config['max_loss_percent'])) if is_trend else Decimal(str(self.config['mean_reversion_sl']))
            )

            #計算倉位大小(代幣數量)
            position_size = base_size / current_price

            
            # 計算 ATR 百分比
            indicators = TechnicalIndicators()
            atr_percentage = indicators.calculate_atr_percentage(df)
            current_atr_percentage = float(atr_percentage.iloc[-1])
            
            # 根據 ATR 百分比調整倉位大小
            if current_atr_percentage > 0.01:  # ATR 百分比大於 1%
                size_multiplier = 0.7
            elif current_atr_percentage > 0.005:  # ATR 百分比大於 0.5%
                size_multiplier = 1.0
            else:  # ATR 百分比小於 0.5%
                size_multiplier = 1.2
                
            logger.info(f"計算倉位大小: {position_size * Decimal(str(size_multiplier))}")
            return position_size * Decimal(str(size_multiplier))
        
        except Exception as e:
            logger.error(f"計算倉位大小失敗: {str(e)}")
            return Decimal('0')
            
    def can_open_position(self) -> bool:
        """
        檢查是否可以開倉
        
        Args:
            symbol: 交易對
            
        Returns:
            bool: 是否可以開倉
        """
        return all([
            self.check_margin_usage(),
            self.check_daily_pnl(),
            self.check_daily_trades(),
            self.check_cooldown()
        ])
        
    def can_close_position(self, symbol: str) -> bool:
        """
        檢查是否可以平倉
        
        Args:
            symbol: 交易對
            
        Returns:
            bool: 是否可以平倉
        """
        return not self.check_holding_period(symbol)
        
    def check_slippage(self, symbol: str) -> bool:
        """
        檢查滑價比率
        
        Args:
            symbol: 交易對
            
        Returns:
            bool: 是否小於最大滑價比率
        """
        try:
            # 獲取訂單簿
            orderbook = self.order_executor.get_order_book(symbol)
            
            # 檢查訂單簿是否為空
            if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
                logger.warning(f"無法獲取 {symbol} 的訂單簿")
                return False
                
            # 計算滑價比率
            best_bid = Decimal(str(orderbook['bids'][0][0]))
            best_ask = Decimal(str(orderbook['asks'][0][0]))
            mid_price = (best_bid + best_ask) / 2
            
            # 計算滑價比率
            slippage = abs(best_ask - best_bid) / mid_price * 100
            
            # 檢查是否超過限制
            if slippage > self.config['slippage_percent']:
                logger.warning(f"{symbol} 滑價比率過高: {slippage} %")
                return False
                
            return True
        
        except Exception as e:
            logger.error(f"檢查滑價比率失敗: {str(e)}")
            return False