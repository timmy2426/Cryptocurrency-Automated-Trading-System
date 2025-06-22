import os
import sys
import pandas as pd
from datetime import datetime, time as dt_time, timezone
from typing import Optional, List, Dict, Tuple
import logging
from decimal import Decimal, ROUND_HALF_UP
import json
import time

# 添加專案根目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from data_manager import DataManager
from core.risk_control import RiskControl
from data.indicators import TechnicalIndicators
from utils.config import check_config_parameters

logger = logging.getLogger(__name__)

class Broker:
    """回測經紀商，負責處理所有交易相關操作"""
    
    def __init__(self, config: Dict):
        """
        初始化回測經紀商
        
        Args:
            config: 配置參數，包含：
                - initial_balance: 初始資金
                - leverage: 槓桿倍數
                - slippage: 滑點率
                - fee: 手續費率
                - symbol: 交易對列表
        """
        self.config = config
        self.commission_rate = Decimal(str(config.get('fee', 0.0005)))    
        self.slippage_rate = Decimal(str(config.get('slippage', 0.0005))) 
        self.leverage = Decimal(str(config.get('leverage', 5)))           
        
        # 載入其他相關參數
        params = check_config_parameters([
            'max_margin_usage',   
            'max_daily_loss',     
            'max_daily_trades',  
            'consecutive_losses',  
            'cooldown_period',    
            'max_trend_holding_bars',
            'max_mean_rev_holding_bars',
            'risk_per_trade',
            'activate_price_rate',
            'trailing_percent',
            'max_loss_percent',
            'mean_reversion_sl',
            'mean_reversion_tp'
        ])
        
        # 初始化限制參數
        self.max_margin_usage = Decimal(str(params['max_margin_usage']))
        self.max_daily_loss = Decimal(str(params['max_daily_loss']))
        self.max_daily_trades = int(params['max_daily_trades'])
        self.max_consecutive_loss = int(params['consecutive_losses'])  
        self.cooldown_period = int(params['cooldown_period'])
        self.max_trend_holding_bars = int(params['max_trend_holding_bars'])
        self.max_mean_rev_holding_bars = int(params['max_mean_rev_holding_bars'])
        self.risk_per_trade = Decimal(str(params['risk_per_trade']))
        self.max_loss_percent = Decimal(str(params['max_loss_percent']))
        self.mean_reversion_sl = Decimal(str(params['mean_reversion_sl']))
        self.mean_reversion_tp = Decimal(str(params['mean_reversion_tp']))
        self.activate_price_rate = Decimal(str(params['activate_price_rate']))
        self.trailing_percent = Decimal(str(params['trailing_percent']))
        
        # 初始化賬戶信息
        self.account_info = {
            'account_equity': Decimal(str(config.get('initial_balance', 10000))),
            'total_trades': 0,
            'total_pnl': Decimal('0'),
            'daily_trades': 0,
            'daily_pnl': Decimal('0')
        }
        
        self.positions = {}
        self.trades = []
        self.equity_curve = [] 
        
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
            'margin': Decimal('0'),
            'close_reason': None,
            'stop_loss': None,
            'take_profit': None,
            'trailing_stop': None,
            'price_rate': None,
            'pnl': Decimal('0'),
            'pnl_percentage': Decimal('0'),
            'market_condition': None
        }
        
        # 初始化模組
        self.data_manager = DataManager()
        self.risk_control = RiskControl()
        
        # 初始化冷卻期相關變量
        self.consecutive_losses = 0  
        self.cooldown_start_time = 0  
        self.is_cooldown_activate = False  

        # 初始化重置時間
        self.last_reset_time = 0
        
        # 創建交易日誌目錄
        self.trade_log_dir = os.path.join(project_root, "backtest", "backtest_log")
        os.makedirs(self.trade_log_dir, exist_ok=True)
        
    def _round_decimal(self, value: Decimal) -> Decimal:
        """
        將 Decimal 數值四捨五入到小數點後8位
        
        Args:
            value: 要四捨五入的數值
            
        Returns:
            Decimal: 四捨五入後的數值
        """
        return value.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
        
    def load_data(self, symbol: str, interval: str, start_date: str, end_date: str) -> bool:
        """
        載入K線數據
        
        Args:
            symbol: 交易對
            interval: K線間隔
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            bool: 是否成功載入數據
        """
        try:
            # 使用 DataManager 載入數據
            df = self.data_manager.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                logger.error(f"無法載入數據: {symbol}")
                return False
                
            self.data = df
            logger.info(f"成功載入數據: {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"載入數據失敗: {str(e)}")
            return False
        
    def calculate_commission(self, amount: Decimal) -> Decimal:
        """
        計算手續費
        
        Args:
            amount: 交易金額
            
        Returns:
            Decimal: 手續費
        """
        return self._round_decimal(amount * self.commission_rate)
        
    def calculate_slippage(self, price: Decimal, is_buy: bool) -> Decimal:
        """
        計算滑點
        
        Args:
            price: 原始價格
            is_buy: 是否為買入
            
        Returns:
            Decimal: 考慮滑點後的價格
        """
        if is_buy:
            return self._round_decimal(price * (Decimal('1') + self.slippage_rate))
        return self._round_decimal(price * (Decimal('1') - self.slippage_rate))
    
    def record_market_condition(self, symbol: str, timestamp: int, df_1h: pd.DataFrame, df_4h: pd.DataFrame, df_1d: pd.DataFrame) -> None:
        """
        記錄市場條件
        """
        timestamp = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()
        market_condition = self.risk_control.check_trend_filter(df_1h, df_4h, df_1d)

        self.positions[symbol]['market_condition'] = {
            'timestamp': timestamp,
            '1h_open_time': str(df_1h.iloc[-2]['timestamp']),
            '1h_open_price': df_1h.iloc[-2]['open'],
            '4h_open_time': str(df_4h.iloc[-2]['timestamp']),
            '4h_open_price': df_4h.iloc[-2]['open'],
            '1d_open_time': str(df_1d.iloc[-2]['timestamp']),
            '1d_open_price': df_1d.iloc[-2]['open'],
            'trend_filter': market_condition
        }
        
    def open_position(self, symbol: str, side: str, amount: Decimal, price: Decimal, timestamp: int, 
                     strategy: str = None, stop_loss: Decimal = None, 
                     take_profit: Decimal = None, trailing_stop: Decimal = None,
                     price_rate: Decimal = None) -> bool:
        """
        開倉
        
        Args:
            symbol: 交易對
            side: 方向 (BUY/SELL)
            amount: 數量
            price: 開倉價格
            timestamp: 時間戳
            strategy: 策略名稱
            stop_loss: 止損價格
            take_profit: 止盈價格
            trailing_stop: 追蹤止損
            price_rate: 回調率
            
        Returns:
            bool: 是否成功開倉
        """
        # 根據交易方向計算滑點
        if side == 'BUY':  # 做多
            slippage_price = self.calculate_slippage(price, True)  
        else:  # 做空
            slippage_price = self.calculate_slippage(price, False)  
            
        # 使用滑點後的價格計算交易金額和保證金
        trade_size = self._round_decimal(amount * slippage_price)
        commission = self._round_decimal(self.calculate_commission(trade_size))
        margin = self._round_decimal(trade_size / self.leverage)
        
        # 檢查資金是否足夠
        if margin + commission > self.account_info['account_equity']:
            logger.warning("資金不足，無法開倉")
            return False
            
        # 更新持倉
        if symbol not in self.positions:
            position = self._position_template.copy()
            position.update({
                'symbol': symbol,
                'side': side,
                'strategy': strategy,
                'open_time': timestamp,
                'open_price': slippage_price,
                'open_amt': amount,
                'open_size': trade_size,
                'margin': margin,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'trailing_stop': trailing_stop,
                'price_rate': price_rate
            })
            self.positions[symbol] = position
        else:
            logger.warning(f"已有持倉: {symbol}")
            return False
            
        # 更新賬戶信息
        self.account_info['account_equity'] -= commission
        self.account_info['total_trades'] += 1
        self.account_info['daily_trades'] += 1
        
        logger.info(f"開倉成功: {symbol} {side} {amount} @ {slippage_price}, margin: {margin}, commission: {commission}")
        return True
        
    def close_position(self, symbol: str, price: Decimal, timestamp: int, reason: str = None) -> bool:
        """
        平倉
        
        Args:
            symbol: 交易對
            price: 平倉價格
            timestamp: 時間戳
            reason: 平倉原因
            
        Returns:
            bool: 是否成功平倉
        """
        if symbol not in self.positions:
            logger.warning(f"沒有持倉: {symbol}")
            return False
            
        # 獲取持倉信息
        position = self.positions[symbol]
        if position['side'] == 'BUY':
            position['side'] = 'SELL'
        else:
            position['side'] = 'BUY'
        side = position['side']
        amount = position['open_amt']
        entry_price = position['open_price']
        
        # 根據交易方向計算滑點
        if side == 'BUY':  # 做多平倉
            slippage_price = self.calculate_slippage(price, False)  
        else:  # 做空平倉
            slippage_price = self.calculate_slippage(price, True)  
            
        # 使用滑點後的價格計算交易金額和保證金
        trade_size = self._round_decimal(amount * slippage_price)
        commission = self._round_decimal(self.calculate_commission(trade_size))
        
        # 計算盈虧
        if side == 'BUY':
            pnl = self._round_decimal((entry_price - slippage_price) * amount)
        else:
            pnl = self._round_decimal((slippage_price - entry_price) * amount)
            
        # 更新持倉信息
        position.update({
            'close_time': timestamp,
            'close_price': slippage_price,
            'close_amt': amount,
            'close_size': trade_size,
            'close_reason': reason,
            'pnl': pnl,
            'pnl_percentage': self._round_decimal(pnl / position['open_size'] * Decimal('100'))
        })
        
        # 更新賬戶信息
        self.account_info['account_equity'] = self._round_decimal(
            self.account_info['account_equity'] + pnl
        )
        self.account_info['total_pnl'] = self._round_decimal(
            self.account_info['total_pnl'] + pnl
        )
        self.account_info['daily_pnl'] = self._round_decimal(
            self.account_info['daily_pnl'] + pnl
        )
        self.account_info['account_equity'] -= commission
        
        # 檢查是否為虧損平倉
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_loss:
                self.cooldown_start_time = timestamp
                self.is_cooldown_activate = True
                logger.info(f"連續虧損達到 {self.max_consecutive_loss} 次，進入冷卻期")
        else:
            self.consecutive_losses = 0
        
        # 寫入交易紀錄
        self.trades.append(self.positions[symbol].copy())

        # 清除持倉
        del self.positions[symbol]
        
        logger.info(f"平倉成功: {symbol} {amount} @ {slippage_price}, PNL: {pnl}")
        return True
            
    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        獲取持倉信息
        
        Args:
            symbol: 交易對
            
        Returns:
            Optional[Dict]: 持倉信息
        """
        return self.positions.get(symbol)
        
    def get_account_info(self) -> Dict:
        """
        獲取賬戶信息
        
        Returns:
            Dict: 賬戶信息
        """
        return self.account_info
        
    def _reset_daily_data(self, current_time: int) -> None:
        """
        重置單日累計數據
        """
        # 將當前時間轉換為datetime對象
        now = datetime.fromtimestamp(current_time / 1000, tz=timezone.utc)
        # 設置為當天凌晨0點
        midnight = datetime.combine(now.date(), dt_time.min, tzinfo=timezone.utc)
        midnight_timestamp = int(midnight.timestamp() * 1000)
        
        # 將上次重置時間轉換為datetime對象
        if self.last_reset_time == 0:
            self.last_reset_time = midnight_timestamp
            return
            
        last_reset_date = datetime.fromtimestamp(self.last_reset_time / 1000, tz=timezone.utc).date()
        
        # 如果當前日期大於上次重置的日期，進行重置
        if now.date() > last_reset_date:
            self.account_info['daily_pnl'] = Decimal('0')
            self.account_info['daily_trades'] = 0
            self.last_reset_time = midnight_timestamp
            logger.info(f"重置單日累計數據: {now.date()} UTC")
        
        logger.info(f"帳戶總權益: {self.account_info['account_equity']}, 每日盈虧: {self.account_info['daily_pnl']}, 每日交易次數: {self.account_info['daily_trades']}")
            
    def check_margin_usage(self) -> bool:
        """
        檢查保證金使用比率
        
        Returns:
            bool: 是否小於最大保證金使用比率
        """
        try:
            if self.account_info['account_equity'] == Decimal('0'):
                return False
                
            # 累加所有持倉的保證金
            total_margin = sum(position['margin'] for position in self.positions.values())
            margin_usage = total_margin / self.account_info['account_equity']
            if not margin_usage <= self.max_margin_usage:
                logger.warning(f"保證金使用比率超過限制: {margin_usage}")
            
            return margin_usage <= self.max_margin_usage
        
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
            # 計算最大允許虧損金額
            max_daily_loss = self.account_info['account_equity'] * self.max_daily_loss
        
            # 檢查單日累計虧損金額
            if self.account_info['daily_pnl'] < -max_daily_loss:
                logger.warning(f"單日累計虧損超過限制: {self.account_info['daily_pnl']}")
                return False
                
            return True
        
        except Exception as e:
            logger.error(f"檢查單日累計盈虧失敗: {str(e)}")
            return False
            
    def check_daily_trades(self, current_time: int) -> bool:
        """
        檢查單日累計開倉數量
        
        Returns:
            bool: 是否小於最大單日交易次數
        """
        try:
            self._reset_daily_data(current_time)
            if not self.account_info['daily_trades'] < self.max_daily_trades:
                logger.warning(f"單日累計開倉數量超過限制: {self.account_info['daily_trades']}")
            
            return self.account_info['daily_trades'] < self.max_daily_trades
        
        except Exception as e:
            logger.error(f"檢查單日累計開倉數量失敗: {str(e)}")
            return False
            
    def check_cooldown(self, current_time: int) -> bool:
        """
        檢查是否處於冷卻期
        
        Args:
            current_time: 當前時間戳（毫秒）
            
        Returns:
            bool: 是否不在冷卻期
        """
        try:
            if self.is_cooldown_activate:
                if current_time - self.cooldown_start_time < self.cooldown_period * 1000:
                    logger.warning(f"冷卻期中: {current_time - self.cooldown_start_time / 1000} 秒")
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
            
    def check_holding_period(self, symbol: str, current_time: int, is_trend: bool) -> bool:
        """
        檢查倉位存續期
        
        Args:
            symbol: 交易對
            current_time: 當前時間戳（毫秒）
            is_trend: 是否為順勢單
            
        Returns:
            bool: 是否小於最大持倉K棒數
        """
        try:
            if symbol not in self.positions:
                return False
                
            # 獲取開倉時間戳
            open_time = self.positions[symbol]['open_time']
            
            # 轉換開倉時間和當前時間為K棒時間戳
            open_candle_time = self._convert_to_candle_timestamp(open_time)
            current_candle_time = self._convert_to_candle_timestamp(current_time)
            
            # 計算K棒數量
            candle_count = (current_candle_time - open_candle_time) // (60 * 60 * 1000)
            
            # 檢查是否小於最大持倉K棒數
            if is_trend:
                holding_bars_not_over = candle_count < self.max_trend_holding_bars
            else:
                holding_bars_not_over = candle_count < self.max_mean_rev_holding_bars
            logger.info(f"倉位存續期: {candle_count} 根 K 棒, 是否需平倉: {not holding_bars_not_over}")

            return holding_bars_not_over
        
        except Exception as e:
            logger.error(f"檢查倉位存續期失敗: {str(e)}")
            return False
            
    def _convert_to_candle_timestamp(self, timestamp: int) -> int:
        """
        將時間戳轉換為K棒時間戳
        
        Args:
            timestamp: 時間戳
            
        Returns:
            int: K棒時間戳
        """
        # 計算K棒時間戳
        return timestamp - (timestamp % (60 * 60 * 1000))
        
    def can_open_position(self, current_time: int) -> bool:
        """
        檢查是否可以開倉
        
        Returns:
            bool: 是否可以開倉
        """
        
        return all([
            self.check_margin_usage(),
            self.check_daily_pnl(),
            self.check_daily_trades(current_time),
            self.check_cooldown(current_time)
        ])
        
    def can_close_position(self, symbol: str, current_time: int, is_trend: bool) -> bool:
        """
        檢查是否可以平倉
        
        Args:
            symbol: 交易對
            current_time: 當前時間戳（毫秒）
            is_trend: 是否為順勢單
            
        Returns:
            bool: 是否可以平倉
        """
        return not self.check_holding_period(symbol, current_time, is_trend)
    
    def set_stop_loss(self, is_trend: bool, current_price: Decimal, side: str) -> Decimal:
        """
        設置止損
        """
        if is_trend:
            if side == 'BUY':
                return current_price * (Decimal('1') - self.max_loss_percent)
            else:
                return current_price * (Decimal('1') + self.max_loss_percent)
        else:
            if side == 'BUY':
                return current_price * (Decimal('1') - self.mean_reversion_sl)
            else:
                return current_price * (Decimal('1') + self.mean_reversion_sl)
            
    def set_take_profit(self, current_price: Decimal, side: str) -> Decimal:
        """
        設置止盈
        """
        if side == 'BUY':
            return current_price * (Decimal('1') + self.mean_reversion_tp)
        else:
            return current_price * (Decimal('1') - self.mean_reversion_tp)
        
    def set_trailing_activate_price(self, current_price: Decimal, side: str) -> Decimal:
        """
        設置移動止損觸發價格
        """
        if side == 'BUY':
            return current_price * (Decimal('1') + self.activate_price_rate)
        else:
            return current_price * (Decimal('1') - self.activate_price_rate)
        
    def set_trailing_price_rate(self) -> Decimal:
        """
        設置移動止損回調率
        """
        return self.trailing_percent

    def check_stop_loss(self, symbol: str, high_price: Decimal, low_price: Decimal, current_time: int) -> bool:
        """
        檢查是否觸發止損
        
        Args:
            symbol: 交易對
            high_price: 當前K線最高價
            low_price: 當前K線最低價
            current_time: 當前時間戳（毫秒）
            
        Returns:
            bool: 是否觸發止損
        """
        if symbol not in self.positions:
            return False
            
        position = self.positions[symbol]
        if position['stop_loss'] is None:
            return False
            
        side = position['side']
        if side == 'BUY' and low_price <= position['stop_loss']:
            logger.info(f"觸發止損: {symbol} @ {position['stop_loss']}")
            return True
        elif side == 'SELL' and high_price >= position['stop_loss']:
            logger.info(f"觸發止損: {symbol} @ {position['stop_loss']}")
            return True
            
        return False
        
    def check_take_profit(self, symbol: str, high_price: Decimal, low_price: Decimal, current_time: int) -> bool:
        """
        檢查是否觸發止盈
        
        Args:
            symbol: 交易對
            high_price: 當前K線最高價
            low_price: 當前K線最低價
            current_time: 當前時間戳（毫秒）
            
        Returns:
            bool: 是否觸發止盈
        """
        if symbol not in self.positions:
            return False
            
        position = self.positions[symbol]
        if position['take_profit'] is None:
            return False
            
        side = position['side']
        if side == 'BUY' and high_price >= position['take_profit']:
            logger.info(f"觸發止盈: {symbol} @ {position['take_profit']}")
            return True
        elif side == 'SELL' and low_price <= position['take_profit']:
            logger.info(f"觸發止盈: {symbol} @ {position['take_profit']}")
            return True
            
        return False
        
    def check_trailing_stop(self, symbol: str, high_price: Decimal, low_price: Decimal) -> bool:
        """
        檢查並更新移動止損
        
        Args:
            symbol: 交易對
            high_price: 當前K線最高價
            low_price: 當前K線最低價
            
        Returns:
            bool: 是否觸發移動止損
        """
        if symbol not in self.positions:
            return False
            
        position = self.positions[symbol]
        if position['trailing_stop'] is None or position['price_rate'] is None:
            return False
            
        side = position['side']
        trigger = False
        
        if side == 'BUY':
            # 如果價格超過移動止損觸發點
            if high_price > position['trailing_stop']:
                # 計算回調價格
                stop_price = high_price * (Decimal('1') - (position['price_rate'] / Decimal('100')))
                # 如果價格回調到止損點，觸發平倉
                if low_price <= stop_price:
                    trigger = True
                    position['stop_loss'] = stop_price
        else:
            # 如果價格低於移動止損觸發點
            if low_price < position['trailing_stop']:
                # 計算回調價格
                stop_price = low_price * (Decimal('1') + (position['price_rate'] / Decimal('100')))
                # 如果價格回調到止損點，觸發平倉
                if high_price >= stop_price:
                    trigger = True
                    position['stop_loss'] = stop_price
                
        return trigger

    def write_trade_logs(self) -> str:
        """
        寫入交易記錄
        """
        try:
            # 生成日誌文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f'trades_{timestamp}.jsonl'
            log_file = os.path.join(self.trade_log_dir, file_name)
            
            # 確保日誌目錄存在
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            
            # 寫入交易記錄
            with open(log_file, 'w', encoding='utf-8') as f:
                for trade in self.trades:
                    # 將時間戳轉換為字符串
                    trade_copy = trade.copy()
                    trade_copy['open_time'] = datetime.fromtimestamp(trade_copy['open_time'] / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()
                    trade_copy['close_time'] = datetime.fromtimestamp(trade_copy['close_time'] / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()
                    
                    # 將 Decimal 轉換為字符串
                    for key, value in trade_copy.items():
                        if isinstance(value, Decimal):
                            trade_copy[key] = str(value)
                            
                    f.write(json.dumps(trade_copy) + '\n')
                    
            logger.info(f"交易記錄已寫入: {log_file}")
            return file_name
            
        except Exception as e:
            logger.error(f"寫入交易記錄失敗: {str(e)}")
            raise

    def calculate_position_size(self, current_price: Decimal, is_trend: bool, df: pd.DataFrame) -> Decimal:
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
            base_size = (self.account_info['account_equity'] * self.risk_per_trade) / (
                self.max_loss_percent if is_trend else self.mean_reversion_sl
            )

            #計算倉位大小(代幣數量)
            position_size = base_size / current_price

            # 計算 ATR 百分比
            indicators = TechnicalIndicators()
            atr_percentage = indicators.calculate_atr_percentage(df)
            current_atr_percentage = float(atr_percentage.iloc[-2])
            
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
    
    def check_slippage(self, symbol: str) -> bool:
        """
        模擬檢查滑點
        """
        return True
