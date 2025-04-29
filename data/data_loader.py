import pandas as pd
import numpy as np
from typing import Optional, Union
from datetime import datetime, timedelta
import logging
from exchange.binance_api import BinanceAPI

logger = logging.getLogger(__name__)

class DataLoader:
    """數據加載器，用於處理K線數據"""
    
    def __init__(self, api: Optional[BinanceAPI] = None):
        """初始化數據加載器
        
        Args:
            api: BinanceAPI實例，如果為None則創建新實例
        """
        self.api = api or BinanceAPI()
        
    def load_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """載入歷史K線數據
        
        Args:
            symbol: 交易對
            interval: 時間週期（如：'1m', '5m', '1h', '1d'等）
            limit: 獲取的K線數量，默認為500
            
        Returns:
            pd.DataFrame: 包含K線數據的DataFrame
        """
        try:
            # 獲取K線數據
            klines = self.api.get_klines(symbol, interval, limit)
            
            # 轉換為DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # 轉換數據類型
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)
                
            # 設置時間戳為索引
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"載入K線數據失敗: {str(e)}")
            raise
            
    def fetch_complete_klines(self, symbol: str, interval: str, 
                            start_time: Optional[Union[int, datetime]] = None,
                            end_time: Optional[Union[int, datetime]] = None,
                            limit: int = 1000) -> pd.DataFrame:
        """抓取完整K線數據
        
        Args:
            symbol: 交易對
            interval: 時間週期
            start_time: 開始時間，可以是時間戳或datetime對象
            end_time: 結束時間，可以是時間戳或datetime對象
            limit: 每次請求的K線數量，默認為1000
            
        Returns:
            pd.DataFrame: 完整的K線數據
        """
        try:
            # 轉換時間格式
            if isinstance(start_time, datetime):
                start_time = int(start_time.timestamp() * 1000)
            if isinstance(end_time, datetime):
                end_time = int(end_time.timestamp() * 1000)
                
            all_klines = []
            current_end = end_time
            
            while True:
                # 獲取一批K線數據
                klines = self.api.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit,
                    end_time=current_end
                )
                
                if not klines:
                    break
                    
                all_klines.extend(klines)
                
                # 更新結束時間為上一批數據的最早時間
                current_end = klines[0][0] - 1
                
                # 如果已經到達開始時間，則停止
                if start_time and current_end < start_time:
                    break
                    
            # 轉換為DataFrame
            df = pd.DataFrame(all_klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # 轉換數據類型
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)
                
            # 設置時間戳為索引
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"抓取完整K線數據失敗: {str(e)}")
            raise
            
    def save_klines_to_csv(self, df: pd.DataFrame, symbol: str, interval: str) -> None:
        """保存K線數據到CSV文件
        
        Args:
            df: K線數據DataFrame
            symbol: 交易對
            interval: 時間週期
        """
        try:
            filename = f"{symbol}_{interval}.csv"
            df.to_csv(filename)
            logger.info(f"K線數據已保存到 {filename}")
        except Exception as e:
            logger.error(f"保存K線數據失敗: {str(e)}")
            raise
            
    def load_klines_from_csv(self, symbol: str, interval: str) -> pd.DataFrame:
        """從CSV文件讀取K線數據
        
        Args:
            symbol: 交易對
            interval: 時間週期
            
        Returns:
            pd.DataFrame: K線數據
        """
        try:
            filename = f"{symbol}_{interval}.csv"
            df = pd.read_csv(filename, index_col='timestamp', parse_dates=True)
            return df
        except Exception as e:
            logger.error(f"讀取K線數據失敗: {str(e)}")
            raise
            
    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """預處理K線數據
        
        Args:
            df: 原始K線數據
            
        Returns:
            pd.DataFrame: 預處理後的數據
        """
        try:
            # 複製數據以避免修改原始數據
            df = df.copy()
            
            # 處理缺失值
            df = df.fillna(method='ffill')  # 前向填充
            
            return df
            
        except Exception as e:
            logger.error(f"預處理數據失敗: {str(e)}")
            raise



