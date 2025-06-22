import logging
import pandas as pd
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from broker import Broker
from metrics import PerformanceMetrics
from data_manager import DataManager
from core.strategy import Strategy
from core.signals import SignalGenerator
from utils.config import check_config_parameters

logger = logging.getLogger(__name__)

class BacktestEngine:
    """回測引擎"""
    
    def __init__(self, config: Dict):
        """
        初始化回測引擎
        
        Args:
            config: 配置參數
        """
        self.config = config
        self.broker = Broker(config)
        self.strategy = Strategy(self.broker)
        self.signal_generator = SignalGenerator()
        
        # 載入參數
        self.params = check_config_parameters([
            'bb_length',
            'bb_change_rate_window',
            'rsi_length',
            'rsi_average_window',
            'ma_slow_length',
            'ma_slope_window',
            'atr_period',
            'average_volume_window'
        ])
        
        # 初始化數據
        self.data = {}
        self.symbol_list = config.get('symbol', [])
        
    def load_data(self) -> None:
        """加載數據"""
        try:
            # 初始化DataManager
            data_manager = DataManager()
            
            # 加載每個交易對的數據
            for symbol in self.symbol_list:
                # 加載不同時間框架的K線數據
                timeframes = ['1h', '4h', '1d']
                for timeframe in timeframes:
                    try:
                        # 使用DataManager獲取K線數據
                        df = data_manager.fetch_klines(
                            symbol=symbol,
                            interval=timeframe,
                            start_date=self.config['start_date'],
                            end_date=self.config['end_date'],
                            force_update=self.config['force_update']
                        )
                        
                        if df.empty:
                            logger.error(f"無法加載數據: {symbol} {timeframe}")
                            break
                        
                        # 初始化數據字典
                        if symbol not in self.data:
                            self.data[symbol] = {}
                            
                        # 存儲數據
                        self.data[symbol][timeframe] = df
                        logger.info(f"成功加載 {symbol} {timeframe} 的數據")
                    except Exception as e:
                        logger.error(f"加載數據文件失敗 {symbol} {timeframe}: {str(e)}")
                        continue
                    
                logger.info(f"完成加載 {symbol} 的所有數據")
                
        except Exception as e:
            logger.error(f"加載數據失敗: {str(e)}")
            raise
            
    def run(self) -> None:
        """執行回測"""
        try:
            # 加載數據
            self.load_data()
            main_symbol = self.symbol_list[0]
            df_1h = self.data[main_symbol]['1h']

            # 預留K線(使所有指標都有足夠的計算數據)
            all_numeric = all(isinstance(v, (int, float)) and v is not None for v in self.params.values())
            if all_numeric:
                reserved_klines = (max(self.params.values()) * 24) + 1
            else:
                raise ValueError("參數中包含非數值或None值")

            # 從第reserved_klines根K線開始
            for i in range(reserved_klines, len(df_1h)-1):
                # 檢查帳戶資金
                account_info = self.broker.get_account_info()
                if account_info['account_equity'] <= Decimal('0'):
                    logger.error(f"帳戶資金不足，跳過回測 {symbol}")
                    break
                
                # 每個交易對依序回測
                for symbol in self.symbol_list:
                    position = self.broker.get_position(symbol)
                    df_1h = self.data[symbol]['1h']
                    df_4h = self.data[symbol]['4h']
                    df_1d = self.data[symbol]['1d']

                    # 取得當前時間和價格
                    current_time = df_1h['timestamp'].iloc[i]
                    current_price = Decimal(str(df_1h['open'].iloc[i]))
                    logger.info(f"開盤時間: {current_time}, {symbol} 價格: {current_price}")
                    
                    # 使用時間戳對齊不同時間框架的數據
                    df_4h_until_now = df_4h[df_4h['timestamp'] < current_time]
                    df_1d_until_now = df_1d[df_1d['timestamp'] < current_time]

                    # 將時間戳轉換為毫秒
                    if isinstance(current_time, datetime):
                        current_time = int(current_time.timestamp() * 1000)
                    
                    # 處理現有倉位
                    if symbol in self.broker.positions:
                        
                        # 檢查被動出場
                        high_price = Decimal(str(df_1h['high'].iloc[i-1]))
                        low_price = Decimal(str(df_1h['low'].iloc[i-1]))
                        
                        # 檢查止損
                        if position and position['stop_loss'] is not None:
                            if self.broker.check_stop_loss(symbol, high_price, low_price, current_time):
                                price = position['stop_loss']
                                self.broker.close_position(symbol, price, current_time, "STOP_LOSS")
                                continue
                                
                        # 檢查止盈
                        if position and position['take_profit'] is not None:
                            if self.broker.check_take_profit(symbol, high_price, low_price, current_time):
                                price = position['take_profit']
                                self.broker.close_position(symbol, price, current_time, "TAKE_PROFIT")
                                continue
                                
                        # 檢查移動止損
                        if position and position['trailing_stop'] is not None:
                            if self.broker.check_trailing_stop(symbol, high_price, low_price):
                                price = position['stop_loss']
                                self.broker.close_position(symbol, price, current_time, "TRAILING_STOP")
                                continue
                            
                        # 計算指標
                        indicators = self.signal_generator.calculate_indicators(df_1h.iloc[:i])
                        
                        # 檢查主動出場信號
                        should_close = False
                        is_trend = position['strategy'].startswith("trend")
                        if is_trend:
                            if position['side'] == "BUY":
                                should_close = self.signal_generator.is_trend_long_exit(df_1h.iloc[:i], indicators).iloc[-1]
                            else:
                                should_close = self.signal_generator.is_trend_short_exit(df_1h.iloc[:i], indicators).iloc[-1]
                        else:  # mean_reversion
                            if position['side'] == "BUY":
                                should_close = self.signal_generator.is_mean_rev_long_exit(df_1h.iloc[:i], indicators).iloc[-1]
                            else:
                                should_close = self.signal_generator.is_mean_rev_short_exit(df_1h.iloc[:i], indicators).iloc[-1]

                        close_position = self.broker.can_close_position(symbol, current_time, is_trend)
                                
                        if should_close or close_position:
                            self.broker.close_position(symbol, current_price, current_time, "MANUAL")
                            continue
                            
                    # 檢查是否可以開新倉
                    if not self.broker.can_open_position(current_time):
                        logger.info(f"帳號風險控制檢查未通過，跳過本輪交易檢查")
                        continue

                    # 處理開倉邏輯
                    if symbol not in self.broker.positions:
                        
                        # 計算指標
                        indicators = self.signal_generator.calculate_indicators(df_1h.iloc[:i])
                        
                        # 選擇策略
                        selected_strategy = self.strategy.select(
                            symbol,
                            df_1h.iloc[:i+1],
                            df_4h_until_now,
                            df_1d_until_now
                        )
                        
                        if selected_strategy == "no_trade":
                            continue
                            
                        # 根據策略開倉
                        if selected_strategy.endswith("long"):
                            side = "BUY"
                        else:
                            side = "SELL"
                            
                        # 計算倉位大小
                        is_trend = selected_strategy.startswith("trend")
                        amount = self.broker.calculate_position_size(
                            current_price=current_price,
                            is_trend=is_trend,
                            df=df_1h.iloc[:i+1]
                        )
                        
                        # 開倉
                        if is_trend:
                            self.broker.open_position(
                                symbol=symbol,
                                side=side,
                                amount=amount,
                                price=current_price,
                                timestamp=current_time,
                                strategy=selected_strategy,
                                stop_loss=self.broker.set_stop_loss(is_trend, current_price, side),
                                trailing_stop=self.broker.set_trailing_activate_price(current_price, side),
                                price_rate=self.broker.set_trailing_price_rate()
                            )
                        else:
                            self.broker.open_position(
                                symbol=symbol,
                                side=side,
                                amount=amount,
                                price=current_price,
                                timestamp=current_time,
                                strategy=selected_strategy,
                                stop_loss=self.broker.set_stop_loss(is_trend, current_price, side),
                                take_profit=self.broker.set_take_profit(current_price, side)
                            )
                        
                        # 記錄市場條件
                        self.broker.record_market_condition(symbol, current_time, df_1h.iloc[:i+1], df_4h_until_now, df_1d_until_now)
                        
                        # 檢查被動出場
                        high_price = Decimal(str(df_1h['high'].iloc[i-1]))
                        low_price = Decimal(str(df_1h['low'].iloc[i-1]))
                        
                        # 檢查止損
                        if position and position['stop_loss'] is not None:
                            if self.broker.check_stop_loss(symbol, high_price, low_price, current_time):
                                price = position['stop_loss']
                                self.broker.close_position(symbol, price, current_time, "STOP_LOSS")
                                continue
                                
                        # 檢查止盈
                        if position and position['take_profit'] is not None:
                            if self.broker.check_take_profit(symbol, high_price, low_price, current_time):
                                price = position['take_profit']
                                self.broker.close_position(symbol, price, current_time, "TAKE_PROFIT")
                                continue
                                
                        # 檢查移動止損
                        if position and position['trailing_stop'] is not None:
                            if self.broker.check_trailing_stop(symbol, high_price, low_price):
                                price = position['stop_loss']
                                self.broker.close_position(symbol, price, current_time, "TRAILING_STOP")
                                continue
                        
                # 更新權益曲線
                self.broker.equity_curve.append({
                    'timestamp': current_time,
                    'equity': float(self.broker.account_info['account_equity'])
                })
            
            # 寫入交易記錄
            file_name = self.broker.write_trade_logs()

            # 生成績效分析報告
            self.generate_performance_report(file_name)
            
        except Exception as e:
            logger.error(f"執行回測失敗: {str(e)}")
            raise
    
    def generate_performance_report(self, file_name: str) -> None:
        """生成績效分析報告"""
        try:
            logger.info("開始生成績效分析報告...")
            
            # 準備參數配置
            config = {
                'risk_free_rate': self.config['risk_free_rate'],
                'initial_balance': self.config['initial_balance']
            }
            
            # 初始化績效分析
            performance_metrics = PerformanceMetrics(config, file_name)
            
            # 執行績效分析
            performance_metrics.run()
            
            logger.info("績效分析報告生成完成")
            
        except Exception as e:
            logger.error(f"生成績效分析報告失敗: {str(e)}")