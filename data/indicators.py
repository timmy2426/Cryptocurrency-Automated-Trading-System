import pandas as pd
import numpy as np
from typing import Tuple, Optional
import logging
from utils.config import check_config_parameters

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """技術指標計算類"""
    
    def __init__(self):
        """初始化技術指標類，加載配置參數"""
        try:
            # 加載指標配置參數
            required_params = [
                'bb_length',
                'bb_mult',
                'bb_change_rate_window',
                'bb_price_threshold',
                'rsi_length',
                'rsi_average_window',
                'ma_slope_window',
                'atr_period',
                'average_volume_window'
            ]
            
            self.config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in self.config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
                
        except Exception as e:
            logger.error(f"初始化技術指標類失敗: {str(e)}")
            raise
    
    def calculate_bollinger_bands(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """計算布林帶
        
        Args:
            df: 包含收盤價的DataFrame
            
        Returns:
            Tuple[pd.Series, pd.Series, pd.Series]: 中軌、上軌、下軌
        """
        try:
            # 計算中軌（移動平均線）
            middle_band = df['close'].rolling(window=self.config['bb_length']).mean()
            
            # 計算標準差
            std = df['close'].rolling(window=self.config['bb_length']).std()
            
            # 計算上軌和下軌
            upper_band = middle_band + (std * self.config['bb_mult'])
            lower_band = middle_band - (std * self.config['bb_mult'])
            
            return middle_band, upper_band, lower_band
            
        except Exception as e:
            logger.error(f"計算布林帶失敗: {str(e)}")
            raise
            
    def calculate_bollinger_bandwidth(self, upper_band: pd.Series, lower_band: pd.Series, 
                                    middle_band: pd.Series) -> pd.Series:
        """計算布林帶寬度
        
        Args:
            upper_band: 布林帶上軌
            lower_band: 布林帶下軌
            middle_band: 布林帶中軌
            
        Returns:
            pd.Series: 布林帶寬度
        """
        try:
            # 布林帶寬度 = (上軌 - 下軌) / 中軌
            bandwidth = (upper_band - lower_band) / middle_band
            return bandwidth
            
        except Exception as e:
            logger.error(f"計算布林帶寬度失敗: {str(e)}")
            raise
            
    def calculate_bollinger_bandwidth_change_rate(self, bandwidth: pd.Series) -> pd.Series:
        """計算布林帶寬度變化率
        
        Args:
            bandwidth: 布林帶寬度
            
        Returns:
            pd.Series: 布林帶寬度變化率
        """
        try:
            # 計算寬度變化率 = (當前寬度 - 前N期寬度) / 前N期寬度
            change_rate = bandwidth.pct_change(periods=self.config['bb_change_rate_window'])
            return change_rate
            
        except Exception as e:
            logger.error(f"計算布林帶寬度變化率失敗: {str(e)}")
            raise
            
    def is_price_near_band(self, price: float, upper_band: float, lower_band: float) -> Tuple[bool, bool]:
        """判斷價格是否靠近布林帶上下軌
        
        Args:
            price: 當前價格
            upper_band: 布林帶上軌
            lower_band: 布林帶下軌
            
        Returns:
            Tuple[bool, bool]: (是否靠近上軌, 是否靠近下軌)
        """
        try:
            # 計算價格與上下軌的距離百分比
            upper_distance = abs(price - upper_band) / upper_band
            lower_distance = abs(price - lower_band) / lower_band
            
            # 判斷是否在閾值範圍內
            near_upper = upper_distance <= self.config['bb_price_threshold']
            near_lower = lower_distance <= self.config['bb_price_threshold']
            
            return near_upper, near_lower
            
        except Exception as e:
            logger.error(f"判斷價格位置失敗: {str(e)}")
            raise
            
    def calculate_rsi(self, df: pd.DataFrame) -> pd.Series:
        """計算RSI
        
        Args:
            df: 包含收盤價的DataFrame
            
        Returns:
            pd.Series: RSI值
        """
        try:
            length = self.config['rsi_length']
            delta = df['close'].diff()

            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)

            # 初始值：只留 NaN
            avg_gain = gain.ewm(alpha=1/length, min_periods=length, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/length, min_periods=length, adjust=False).mean()

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            return rsi

        except Exception as e:
            logger.error(f"計算RSI失敗: {str(e)}")
            raise
            
    def calculate_average_rsi(self, rsi: pd.Series) -> pd.Series:
        """計算平均RSI
        
        Args:
            rsi: RSI序列
            
        Returns:
            pd.Series: 平均RSI
        """
        try:
            # 計算移動平均
            avg_rsi = rsi.rolling(window=self.config['rsi_average_window']).mean()
            return avg_rsi
            
        except Exception as e:
            logger.error(f"計算平均RSI失敗: {str(e)}")
            raise
            
    def calculate_sma(self, df: pd.DataFrame, window: int) -> pd.Series:
        """計算簡單移動平均線
        
        Args:
            df: 包含收盤價的DataFrame
            
        Returns:
            pd.Series: 移動平均線
        """
        try:
            # 計算簡單移動平均
            sma = df['close'].rolling(window=window).mean()
            return sma
            
        except Exception as e:
            logger.error(f"計算移動平均線失敗: {str(e)}")
            raise

    def calculate_ma_slope(self, ma: pd.Series) -> pd.Series:
        """計算移動平均線斜率
        
        Args:
            ma: 移動平均線
            
        Returns:
            pd.Series: 移動平均線斜率
        """
        try:
            # 計算斜率
            slope = ma.pct_change(periods=self.config['ma_slope_window'])
            return slope
    
        except Exception as e:
            logger.error(f"計算移動平均線斜率失敗: {str(e)}")
            raise

    def calculate_average_volume(self, df: pd.DataFrame) -> pd.Series:
        """計算平均成交量
        
        Args:
            df: 包含成交量的DataFrame
            
        Returns:
            pd.Series: 平均成交量
        """
        try:
            # 計算成交量移動平均
            avg_volume = df['volume'].rolling(window=self.config['average_volume_window']).mean()
            return avg_volume
            
        except Exception as e:
            logger.error(f"計算平均成交量失敗: {str(e)}")
            raise

    def calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """計算平均真實波幅(ATR)
        
        Args:
            df: 包含K線數據的DataFrame，需要包含 high, low, close 欄位
            
        Returns:
            pd.Series: ATR序列
        """
        try:
            # 計算真實波幅(TR)
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            length = self.config['atr_period']
            
            # 取三者中的最大值
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            
            # 計算ATR
            atr = tr.ewm(alpha=1/length, min_periods=length, adjust=False).mean()
            
            return atr
            
        except Exception as e:
            logger.error(f"計算ATR失敗: {str(e)}")
            raise
            
    def calculate_atr_percentage(self, df: pd.DataFrame) -> pd.Series:
        """計算ATR占價格百分比
        
        Args:
            df: 包含K線數據的DataFrame，需要包含 high, low, close 欄位
            
        Returns:
            pd.Series: ATR百分比序列
        """
        try:
            # 計算ATR
            atr = self.calculate_atr(df)
            
            # 計算ATR/價格
            atr_percentage = (atr / df['close'])
            
            return atr_percentage
            
        except Exception as e:
            logger.error(f"計算ATR百分比失敗: {str(e)}")
            raise
