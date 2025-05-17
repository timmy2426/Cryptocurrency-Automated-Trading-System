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
                'ma_slope_trend_threshold',
                'ma_slope_sideway_threshold',
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
            
    def check_trend_filter(self, df_15min: pd.DataFrame, df_1h: pd.DataFrame, df_4h: pd.DataFrame) -> str:
        """多週期趨勢濾網
        
        Args:
            df_15min: 15分鐘K線數據
            df_1h: 1小時K線數據
            df_4h: 4小時K線數據
            
        Returns:
            str: 趨勢狀態，'trend'/'neutral'/'sideway'
        """
        try:
            # 計算各時間框架的趨勢分數
            scores = []
            
            for df in [df_15min, df_1h, df_4h]:
                # 計算 ma_fast 和 ma_slow
                ma_fast = self.indicators.calculate_sma(df, self.config['bb_length'])
                ma_slow = self.indicators.calculate_sma(df, self.config['ma_slow_length'])
                
                # 計算斜率
                ma_fast_slope = self.indicators.calculate_ma_slope(ma_fast)
                ma_slow_slope = self.indicators.calculate_ma_slope(ma_slow)
                
                # 判斷趨勢
                trend_threshold = self.config['ma_slope_trend_threshold']
                sideway_threshold = self.config['ma_slope_sideway_threshold']

                if abs(ma_fast_slope.iloc[-2]) > trend_threshold and abs(ma_slow_slope.iloc[-2]) > sideway_threshold:
                    score = 1
                elif abs(ma_fast_slope.iloc[-2]) < sideway_threshold and abs(ma_slow_slope.iloc[-2]) < trend_threshold:
                    score = -1
                else:
                    score = 0
                    
                scores.append(score)
                
            # 計算加權總分
            total_score = (scores[0] * 3) + (scores[1] * 2) + (scores[2] * 1)
            
            # 判斷趨勢
            if total_score >= 4:
                return 'trend'
            elif total_score <= -4:
                return 'sideway'
            else:
                return 'neutral'
                
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
            
    def select_strategy(self, df_15min: pd.DataFrame, df_1h: pd.DataFrame, df_4h: pd.DataFrame) -> str:
        """策略切換器
        
        Args:
            df_15min: 15分鐘K線數據
            df_1h: 1小時K線數據
            df_4h: 4小時K線數據
            
        Returns:
            str: 選擇的策略，'trend'/'mean_reversion'
        """
        try:
            # 檢查各濾網
            trend = self.check_trend_filter(df_15min, df_1h, df_4h)
            volume_ok = self.check_volume_filter(df_15min)
            bandwidth_ok = self.check_bandwidth_filter(df_15min)

            logger.info(f"風險控制器：趨勢濾網: {trend}, 成交量濾網: {volume_ok}, 布林帶寬濾網: {bandwidth_ok}")
            
            # 判斷策略
            if volume_ok and bandwidth_ok:
                if trend == 'trend':
                    return 'trend'
                elif trend == 'sideway':
                    return 'mean_reversion'
                elif trend == 'neutral':
                    return 'both'
                    
            return 'no_trade'
            
        except Exception as e:
            logger.error(f"選擇策略失敗: {str(e)}")
            raise