from binance.client import Client
from binance.exceptions import BinanceAPIException
import pandas as pd
from typing import Optional, Union, List
import logging
from datetime import datetime

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceAPI:
    """Binance API 封裝類"""
    
    # K線時間週期映射
    KLINE_INTERVALS = {
        '1m': Client.KLINE_INTERVAL_1MINUTE,
        '3m': Client.KLINE_INTERVAL_3MINUTE,
        '5m': Client.KLINE_INTERVAL_5MINUTE,
        '15m': Client.KLINE_INTERVAL_15MINUTE,
        '30m': Client.KLINE_INTERVAL_30MINUTE,
        '1h': Client.KLINE_INTERVAL_1HOUR,
        '2h': Client.KLINE_INTERVAL_2HOUR,
        '4h': Client.KLINE_INTERVAL_4HOUR,
        '6h': Client.KLINE_INTERVAL_6HOUR,
        '8h': Client.KLINE_INTERVAL_8HOUR,
        '12h': Client.KLINE_INTERVAL_12HOUR,
        '1d': Client.KLINE_INTERVAL_1DAY,
        '3d': Client.KLINE_INTERVAL_3DAY,
        '1w': Client.KLINE_INTERVAL_1WEEK,
        '1M': Client.KLINE_INTERVAL_1MONTH
    }
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        初始化 Binance API
        
        Args:
            api_key: Binance API 密鑰
            api_secret: Binance API 密鑰
        """
        self.client = Client(api_key, api_secret)
        
    def get_klines(self, 
                  symbol: str, 
                  interval: str, 
                  limit: int = 500,
                  start_time: Optional[Union[int, str, datetime]] = None,
                  end_time: Optional[Union[int, str, datetime]] = None) -> pd.DataFrame:
        """
        獲取 K 線數據
        
        Args:
            symbol: 交易對，例如 'BTCUSDT'
            interval: K線時間週期，例如 '1m', '1h', '1d'
            limit: 獲取 K 線數量，最大 1000
            start_time: 開始時間（可選）
            end_time: 結束時間（可選）
            
        Returns:
            pd.DataFrame: 包含 K 線數據的 DataFrame
            
        Raises:
            ValueError: 當參數無效時
            BinanceAPIException: 當 API 調用失敗時
        """
        try:
            # 驗證時間週期
            if interval not in self.KLINE_INTERVALS:
                raise ValueError(f"無效的時間週期: {interval}。可用的週期: {list(self.KLINE_INTERVALS.keys())}")
            
            # 驗證數量限制
            if limit > 1000:
                logger.warning("K線數量超過 1000，將自動限制為 1000")
                limit = 1000
                
            # 獲取 K 線數據
            klines = self.client.get_klines(
                symbol=symbol,
                interval=self.KLINE_INTERVALS[interval],
                limit=limit,
                startTime=start_time,
                endTime=end_time
            )
            
            # 轉換為 DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # 轉換數據類型
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            # 設置時間戳為索引
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except BinanceAPIException as e:
            logger.error(f"獲取 K 線數據失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"發生未知錯誤: {str(e)}")
            raise
            
    def get_available_intervals(self) -> List[str]:
        """
        獲取可用的 K 線時間週期
        
        Returns:
            List[str]: 可用的時間週期列表
        """
        return list(self.KLINE_INTERVALS.keys())
