from binance.client import Client
from binance.websockets import BinanceSocketManager
from binance.exceptions import BinanceAPIException
import pandas as pd
from typing import Optional, Union, List, Callable
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

# 加載環境變量
load_dotenv()

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
    
    def __init__(self, testnet: bool = False):
        """
        初始化 Binance API
        
        Args:
            testnet: 是否使用測試網
        """
        api_key = os.getenv('BINANCE_TESTNET_API_KEY' if testnet else 'BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_TESTNET_API_SECRET' if testnet else 'BINANCE_API_SECRET')
        
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.bm = BinanceSocketManager(self.client)
        self.conn_key = None
        self.callback = None
        
    def start_kline_socket(self, 
                          symbol: str, 
                          interval: str, 
                          callback: Callable[[pd.DataFrame], None]) -> None:
        """
        啟動 K 線 WebSocket
        
        Args:
            symbol: 交易對，例如 'BTCUSDT'
            interval: K線時間週期，例如 '1m', '1h', '1d'
            callback: 回調函數，接收 DataFrame 格式的 K 線數據
        """
        try:
            # 驗證時間週期
            if interval not in self.KLINE_INTERVALS:
                raise ValueError(f"無效的時間週期: {interval}。可用的週期: {list(self.KLINE_INTERVALS.keys())}")
            
            def process_message(msg):
                """處理 WebSocket 消息"""
                try:
                    if msg['e'] == 'error':
                        logger.error(f"WebSocket 錯誤: {msg['m']}")
                        return
                        
                    kline = msg['k']
                    df = pd.DataFrame([{
                        'timestamp': pd.to_datetime(kline['t'], unit='ms'),
                        'open': float(kline['o']),
                        'high': float(kline['h']),
                        'low': float(kline['l']),
                        'close': float(kline['c']),
                        'volume': float(kline['v']),
                        'close_time': pd.to_datetime(kline['T'], unit='ms'),
                        'quote_asset_volume': float(kline['q']),
                        'number_of_trades': int(kline['n']),
                        'taker_buy_base_asset_volume': float(kline['V']),
                        'taker_buy_quote_asset_volume': float(kline['Q']),
                        'is_final': kline['x']
                    }])
                    df.set_index('timestamp', inplace=True)
                    callback(df)
                    
                except Exception as e:
                    logger.error(f"處理 K 線數據時發生錯誤: {str(e)}")
            
            # 啟動 WebSocket
            self.conn_key = self.bm.start_kline_socket(symbol, self.KLINE_INTERVALS[interval], process_message)
            self.callback = callback
            self.bm.start()
            logger.info(f"已啟動 {symbol} {interval} K 線 WebSocket")
            
        except Exception as e:
            logger.error(f"啟動 K 線 WebSocket 失敗: {str(e)}")
            raise
            
    def stop_kline_socket(self) -> None:
        """停止 K 線 WebSocket"""
        try:
            if self.conn_key:
                self.bm.stop_socket(self.conn_key)
                self.bm.close()
                self.conn_key = None
                self.callback = None
                logger.info("已停止 K 線 WebSocket")
        except Exception as e:
            logger.error(f"停止 K 線 WebSocket 失敗: {str(e)}")
            raise
            
    def get_historical_klines(self,
                            symbol: str,
                            interval: str,
                            limit: int = 500,
                            start_time: Optional[Union[int, str, datetime]] = None,
                            end_time: Optional[Union[int, str, datetime]] = None) -> pd.DataFrame:
        """
        獲取歷史 K 線數據（使用 REST API）
        
        Args:
            symbol: 交易對，例如 'BTCUSDT'
            interval: K線時間週期，例如 '1m', '1h', '1d'
            limit: 獲取 K 線數量，最大 1000
            start_time: 開始時間（可選）
            end_time: 結束時間（可選）
            
        Returns:
            pd.DataFrame: 包含 K 線數據的 DataFrame
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
            klines = self.client.get_historical_klines(
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
            logger.error(f"獲取歷史 K 線數據失敗: {str(e)}")
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
