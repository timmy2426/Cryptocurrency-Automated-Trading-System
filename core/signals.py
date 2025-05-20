import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging
from utils.config import check_config_parameters
from data.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

class SignalGenerator:
    """交易信號生成器，用於生成交易信號"""
    
    def __init__(self):
        """初始化信號生成器，加載配置參數"""
        try:
            # 加載信號配置參數
            required_params = [
                'bb_length',
                'bb_price_threshold',
                'bb_change_rate',
                'rsi_overbought',
                'rsi_oversold',
                'rsi_momentum_offset',
                'rsi_reversal_offset'
            ]
            
            self.config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in self.config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
                
            # 初始化技術指標計算器
            self.indicators = TechnicalIndicators()
                
        except Exception as e:
            logger.error(f"初始化信號生成器失敗: {str(e)}")
            raise
            
    def calculate_indicators(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """計算所有需要的技術指標
        
        Args:
            df: 包含K線數據的DataFrame
            
        Returns:
            Dict[str, pd.Series]: 包含各種指標的字典
        """
        try:
            indicators = {}
            
            # 計算布林帶
            middle_band, upper_band, lower_band = self.indicators.calculate_bollinger_bands(df)
            indicators['middle_band'] = middle_band
            indicators['upper_band'] = upper_band
            indicators['lower_band'] = lower_band
            
            # 計算布林帶寬度
            bandwidth = self.indicators.calculate_bollinger_bandwidth(upper_band, lower_band, middle_band)
            indicators['bandwidth'] = bandwidth
            
            # 計算布林帶寬度變化率
            bandwidth_change = self.indicators.calculate_bollinger_bandwidth_change_rate(bandwidth)
            indicators['bandwidth_change'] = bandwidth_change
            
            # 計算RSI
            rsi = self.indicators.calculate_rsi(df)
            indicators['rsi'] = rsi
            
            # 計算平均RSI
            avg_rsi = self.indicators.calculate_average_rsi(rsi)
            indicators['avg_rsi'] = avg_rsi

            # 計算ma_fast斜率
            ma_fast = self.indicators.calculate_sma(df, self.config['bb_length'])
            ma_fast_slope = self.indicators.calculate_ma_slope(ma_fast)
            indicators['ma_fast_slope'] = ma_fast_slope

            return indicators
            
        except Exception as e:
            logger.error(f"計算技術指標失敗: {str(e)}")
            raise
            
    def is_trend_long_entry(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """順勢策略做多(開倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 買入信號序列
        """
        try:
            # 1. 收盤價突破布林帶上軌
            price_break_upper = df['close'] > indicators['upper_band']
            
            # 2. RSI > (rsi_overbought - rsi_momentum_offset) ，尚未超買且呈現上升趨勢
            rsi_condition = (
                (indicators['rsi'] > (self.config['rsi_overbought'] - self.config['rsi_momentum_offset'])) &
                (indicators['rsi'] < self.config['rsi_overbought']) &
                (indicators['rsi'] > indicators['avg_rsi'])
            )
            
            # 3. 布林通道寬度擴大，且變化率超過閾值
            bandwidth_expanding = (
                (indicators['bandwidth_change'] > 0) & 
                (indicators['bandwidth_change'] > self.config['bb_change_rate'])
            )
            
            # 綜合判斷
            entry_signal = price_break_upper & rsi_condition & bandwidth_expanding

            logger.info(f"收盤價突破布林上軌: {price_break_upper.iloc[-2]}, RSI上漲動能: {rsi_condition.iloc[-2]}, 布林帶寬擴張: {bandwidth_expanding.iloc[-2]}")
            logger.info(f"順勢策略做多信號: {entry_signal.iloc[-2]}")
            
            return entry_signal
            
        except Exception as e:
            logger.error(f"生成順勢做多信號失敗: {str(e)}")
            raise
            
    def is_trend_short_entry(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """順勢策略做空(開倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 賣出信號序列
        """
        try:
            # 1. 收盤價跌破布林帶下軌
            price_break_lower = df['close'] < indicators['lower_band']
            
            # 2. RSI < (rsi_oversold + rsi_momentum_offset) ，尚未超賣且呈現下降趨勢
            rsi_condition = (
                (indicators['rsi'] < (self.config['rsi_oversold'] + self.config['rsi_momentum_offset'])) &
                (indicators['rsi'] > self.config['rsi_oversold']) &
                (indicators['rsi'] < indicators['avg_rsi'])
            )
            
            # 3. 布林通道寬度擴大，且變化率超過閾值
            bandwidth_expanding = (
                (indicators['bandwidth_change'] > 0) & 
                (indicators['bandwidth_change'] > self.config['bb_change_rate'])
            )
            
            # 綜合判斷
            entry_signal = price_break_lower & rsi_condition & bandwidth_expanding

            logger.info(f"收盤價突破布林下軌: {price_break_lower.iloc[-2]}, RSI下跌動能: {rsi_condition.iloc[-2]}, 布林帶寬擴張: {bandwidth_expanding.iloc[-2]}")
            logger.info(f"順勢策略做空信號: {entry_signal.iloc[-2]}")

            return entry_signal
            
        except Exception as e:
            logger.error(f"生成順勢做空信號失敗: {str(e)}")
            raise
            
    def is_mean_rev_long_entry(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """逆勢策略做多(開倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 買入信號序列
        """
        try:
            # 1. 價格接近或超過布林帶下軌
            price_near_lower = (
                (abs(df['close'] - indicators['lower_band']) / indicators['lower_band'] <= self.config['bb_price_threshold']) | 
                (df['close'] < indicators['lower_band'])
            )
            
            # 2. RSI < rsi_oversold 且出現反轉訊號
            rsi_condition = (
                (indicators['rsi'].shift(1) < self.config['rsi_oversold']) &
                (indicators['rsi'] > indicators['rsi'].shift(1))
            )
            
            # 綜合判斷
            entry_signal = price_near_lower & rsi_condition

            logger.info(f"收盤價接近布林下軌: {price_near_lower.iloc[-2]}, RSI超賣反轉: {rsi_condition.iloc[-2]}")
            logger.info(f"逆勢策略做多信號: {entry_signal.iloc[-2]}")
            
            return entry_signal
            
        except Exception as e:
            logger.error(f"生成逆勢做多信號失敗: {str(e)}")
            raise
            
    def is_mean_rev_short_entry(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """逆勢策略做空(開倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 賣出信號序列
        """
        try:
            # 1. 價格接近或超過布林帶上軌
            price_near_upper = (
                (abs(df['close'] - indicators['upper_band']) / indicators['upper_band'] <= self.config['bb_price_threshold']) | 
                (df['close'] > indicators['upper_band'])
            )
            
            # 2. RSI > rsi_overbought 且出現反轉訊號
            rsi_condition = (
                (indicators['rsi'].shift(1) > self.config['rsi_overbought']) &
                (indicators['rsi'] < indicators['rsi'].shift(1))
            )
            
            # 綜合判斷
            entry_signal = price_near_upper & rsi_condition

            logger.info(f"收盤價接近布林上軌: {price_near_upper.iloc[-2]}, RSI超買反轉: {rsi_condition.iloc[-2]}")
            logger.info(f"逆勢策略做空信號: {entry_signal.iloc[-2]}")
            
            return entry_signal
            
        except Exception as e:
            logger.error(f"生成逆勢做空信號失敗: {str(e)}")
            raise
            
    def is_trend_long_exit(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """順勢策略做多(平倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 平倉信號序列
        """
        try:
            # 1. RSI 升至 > (rsi_overbought + rsi_reversal_offset) 並出現回落
            rsi_exit = (
                (indicators['rsi'].shift(1) > (self.config['rsi_overbought'] + self.config['rsi_reversal_offset'])) &
                (indicators['rsi'] < indicators['rsi'].shift(1))
            )
            
            # 2. 收盤價回到布林中軌
            price_exit = df['close'] <= indicators['middle_band']
            
            # 綜合判斷
            exit_signal = rsi_exit | price_exit

            logger.info(f"RSI超買反轉: {rsi_exit.iloc[-2]}, 收盤價回到布林中軌: {price_exit.iloc[-2]}")
            logger.info(f"順勢策略做多平倉信號: {exit_signal.iloc[-2]}")
            
            return exit_signal
            
        except Exception as e:
            logger.error(f"生成順勢做多平倉信號失敗: {str(e)}")
            raise
            
    def is_trend_short_exit(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """順勢策略做空(平倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 平倉信號序列
        """
        try:
            # 1. RSI 降至 < (rsi_oversold - rsi_reversal_offset) 並出現回升
            rsi_exit = (
                (indicators['rsi'].shift(1) < (self.config['rsi_oversold'] - self.config['rsi_reversal_offset'])) &
                (indicators['rsi'] > indicators['rsi'].shift(1))
            )
            
            # 2. 收盤價回到布林中軌
            price_exit = df['close'] >= indicators['middle_band']
            
            # 綜合判斷
            exit_signal = rsi_exit | price_exit

            logger.info(f"RSI超賣反轉: {rsi_exit.iloc[-2]}, 收盤價回到布林中軌: {price_exit.iloc[-2]}")
            logger.info(f"順勢策略做空平倉信號: {exit_signal.iloc[-2]}")
            
            return exit_signal
            
        except Exception as e:
            logger.error(f"生成順勢做空平倉信號失敗: {str(e)}")
            raise
            
    def is_mean_rev_long_exit(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """逆勢策略做多(平倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 平倉信號序列
        """
        try:
            # 1. 收盤價接近或大於布林中軌
            price_exit = (
                (abs(df['close'] - indicators['middle_band']) / indicators['middle_band'] <= self.config['bb_price_threshold']) | 
                (df['close'] > indicators['middle_band'])
            )
            
            # 2. RSI 升至 50 之上
            rsi_exit = indicators['rsi'] >= 50
            
            # 綜合判斷
            exit_signal = price_exit | rsi_exit

            logger.info(f"收盤價接近布林中軌: {price_exit.iloc[-2]}, RSI升至50之上: {rsi_exit.iloc[-2]}")
            logger.info(f"逆勢策略做多平倉信號: {exit_signal.iloc[-2]}")
            
            return exit_signal
            
        except Exception as e:
            logger.error(f"生成逆勢做多平倉信號失敗: {str(e)}")
            raise
            
    def is_mean_rev_short_exit(self, df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> pd.Series:
        """逆勢策略做空(平倉)信號
        
        Args:
            df: 包含K線數據的DataFrame
            indicators: 包含各種指標的字典
            
        Returns:
            pd.Series: 平倉信號序列
        """
        try:
            # 1. 收盤價接近或小於布林中軌
            price_exit = (
                (abs(df['close'] - indicators['middle_band']) / indicators['middle_band'] <= self.config['bb_price_threshold']) | 
                (df['close'] < indicators['middle_band'])
            )
            
            # 2. RSI 降至 50 之下
            rsi_exit = indicators['rsi'] <= 50
            
            # 綜合判斷
            exit_signal = price_exit | rsi_exit

            logger.info(f"收盤價接近布林中軌: {price_exit.iloc[-2]}, RSI降至50之下: {rsi_exit.iloc[-2]}")
            logger.info(f"逆勢策略做空平倉信號: {exit_signal.iloc[-2]}")
            
            return exit_signal
            
        except Exception as e:
            logger.error(f"生成逆勢做空平倉信號失敗: {str(e)}")
            raise
