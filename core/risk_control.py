import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging
from utils.config import check_config_parameters
from data.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

class RiskControl:
    """風險控制類，用於控制交易風險"""
    
    def __init__(self):
        """初始化風險控制類，加載配置參數"""
        try:
            # 加載風險控制配置參數
            required_params = [
                'bb_length',
                'ma_slow_length',
                'ma_slope_threshold',
                'min_bandwidth_threshold'
            ]
            
            self.config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in self.config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
                
            # 初始化技術指標計算器
            self.indicators = TechnicalIndicators()
                
        except Exception as e:
            logger.error(f"初始化風險控制類失敗: {str(e)}")
            raise
            
    def check_trend_filter(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame, df_1d: pd.DataFrame) -> list[str]:
        """多週期趨勢濾網
        
        Args:
            df_1h: 1小時K線數據
            df_4h: 4小時K線數據
            df_1d: 1天K線數據
            
        Returns:
            str: 趨勢狀態，'long'/'sideway'/'short'
        """
        try:
            # 計算各時間框架的趨勢分數
            status = []
            slope_threshold = self.config['ma_slope_threshold']
            
            for df in [df_1h, df_4h, df_1d]:
                # 計算 ma_fast 和 ma_slow
                ma_fast = self.indicators.calculate_sma(df, self.config['bb_length'])
                ma_slow = self.indicators.calculate_sma(df, self.config['ma_slow_length'])
                
                # 計算斜率
                ma_fast_slope = self.indicators.calculate_ma_slope(ma_fast)
                is_sideway = ma_fast_slope.iloc[-2] < slope_threshold and ma_fast_slope.iloc[-2] > -slope_threshold

                # SMA排列和斜率判斷
                if ma_fast.iloc[-2] > ma_slow.iloc[-2] and ma_fast_slope.iloc[-2] > 0 and not is_sideway:
                    status.append('long')
                elif ma_fast.iloc[-2] < ma_slow.iloc[-2] and ma_fast_slope.iloc[-2] < 0 and not is_sideway:
                    status.append('short')
                else:
                    status.append('sideway')

            return status
                
        except Exception as e:
            logger.error(f"檢查趨勢濾網失敗: {str(e)}")
            raise
            
    def check_volume_filter(self, df: pd.DataFrame) -> bool:
        """成交量濾網
        
        Args:
            df: K線數據
            
        Returns:
            bool: 是否通過濾網
        """
        try:
            # 計算平均成交量
            avg_volume = self.indicators.calculate_average_volume(df)

            # 判斷最新的完整K棒的成交量是否大於平均成交量
            return df['volume'].iloc[-2] > avg_volume.iloc[-2]

        except Exception as e:
            logger.error(f"檢查成交量濾網失敗: {str(e)}")
            raise
            
    def check_bandwidth_filter(self, df: pd.DataFrame) -> bool:
        """BB帶寬濾網
        
        Args:
            df: K線數據
            
        Returns:
            bool: 是否通過濾網
        """
        try:
            # 計算布林帶
            middle_band, upper_band, lower_band = self.indicators.calculate_bollinger_bands(df)
            
            # 計算布林帶寬度
            bandwidth = self.indicators.calculate_bollinger_bandwidth(upper_band, lower_band, middle_band)

            # 判斷帶寬是否大於閾值
            return bandwidth.iloc[-2] > self.config['min_bandwidth_threshold']
            
        except Exception as e:
            logger.error(f"檢查BB帶寬濾網失敗: {str(e)}")
            raise
            
    def select_strategy(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame, df_1d: pd.DataFrame) -> str:
        """策略切換器
        
        Args:
            df_1h: 1小時K線數據
            df_4h: 4小時K線數據
            df_1d: 1天K線數據
            
        Returns:
            str: 選擇的策略，'trend'/'mean_reversion'
        """
        try:
            # 檢查各濾網
            trend = self.check_trend_filter(df_1h, df_4h, df_1d)
            volume_ok = self.check_volume_filter(df_1h)
            bandwidth_ok = self.check_bandwidth_filter(df_1h)

            logger.info(f"風險控制器：趨勢濾網: {trend}, 成交量濾網: {volume_ok}, 布林帶寬濾網: {bandwidth_ok}")
            
            # 判斷策略
            strategy = []
            if volume_ok and bandwidth_ok:
                # 使用元組作為鍵來映射策略
                strategy_map = {
                    # 列出完整108種盤勢組合
                    # 免責聲明：使用者須自行利用回測引擎進行盤勢組合篩選與參數調整，若因直接使用此處的策略組合而導致虧損，作者不負任何責任。
                    ('long', 'long', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'long', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'long', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'short', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'short', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'short', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'sideway', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'sideway', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('long', 'sideway', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'long', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'long', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'long', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'short', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'short', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'short', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'sideway', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'sideway', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('short', 'sideway', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'long', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'long', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'long', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'short', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'short', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'short', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'sideway', 'long'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'sideway', 'short'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                    ('sideway', 'sideway', 'sideway'): ['trend_long', 'trend_short', 'mean_rev_long', 'mean_rev_short'],
                }
                
                # 獲取對應的策略
                trend_key = (trend[0], trend[1], trend[2])
                if trend_key in strategy_map:
                    strategy.extend(strategy_map[trend_key])
                else:
                    strategy.append('no_trade')
            else:
                strategy.append('no_trade')

            return strategy
            
        except Exception as e:
            logger.error(f"選擇策略失敗: {str(e)}")
            raise
