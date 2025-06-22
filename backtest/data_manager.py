import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from binance.um_futures import UMFutures
from tqdm import tqdm
import logging
import time

# 添加專案根目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from utils.config import check_config_parameters

logger = logging.getLogger(__name__)

class DataManager:
    """數據管理器，負責處理所有K線數據相關操作"""
    
    def __init__(self):
        """
        初始化數據管理器
        """
        # 從配置文件獲取 API 金鑰和限制參數
        config = check_config_parameters([
            'BINANCE_API_KEY', 
            'BINANCE_API_SECRET',
            'max_weight_per_minute',
            'max_order_per_second',
            'max_order_per_minute',
            'base_endpoint'
        ])
        
        api_key = config.get('BINANCE_API_KEY')
        api_secret = config.get('BINANCE_API_SECRET')
        base_url = config.get('base_endpoint')
        
        if not api_key or not api_secret:
            raise ValueError("未找到 Binance API 金鑰配置")
            
        if not base_url:
            raise ValueError("未找到 Binance API 端點配置")
            
        # 初始化 UMFutures 客戶端
        self.client = UMFutures(
            key=api_key,
            secret=api_secret,
            base_url=base_url
        )
        
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "backtest", "kline_data")
        
        # 設置 API 限制參數
        self.max_weight_per_minute = config.get('max_weight_per_minute', 1200)
        self.max_order_per_second = config.get('max_order_per_second', 50)
        self.max_order_per_minute = config.get('max_order_per_minute', 100)
        
        # 初始化請求計數器
        self.weight_used = 0
        self.weight_reset_time = time.time()
        self.order_per_second = 0
        self.order_per_second_reset_time = time.time()
        self.order_per_minute = 0
        
        # 確保數據目錄存在
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            logger.info(f"創建數據目錄: {self.data_dir}")
        
    def _get_timezone_offset(self) -> int:
        """
        獲取當前系統時區與 UTC 的時差（小時）
        
        Returns:
            int: 時區偏移小時數
        """
        import time
        
        # 獲取當前時間戳
        timestamp = time.time()
        # 獲取本地時間結構
        local_time = time.localtime(timestamp)
        # 獲取時區偏移（秒）
        offset_seconds = local_time.tm_gmtoff
        # 轉換為小時
        offset_hours = offset_seconds // 3600
        return offset_hours

    def _convert_to_utc(self, date_str: str) -> pd.Timestamp:
        """
        將日期字符串轉換為 UTC 時間戳
        
        Args:
            date_str: 日期字符串 (YYYY-MM-DD)
            
        Returns:
            pd.Timestamp: UTC 時間戳
        """
        try:
            # 解析日期字符串
            date = pd.to_datetime(date_str)
            # 獲取時區偏移
            offset_hours = self._get_timezone_offset()
            # 調整為 UTC 時間
            utc_date = date - pd.Timedelta(hours=offset_hours)
            return utc_date
        except Exception as e:
            logger.error(f"日期轉換失敗: {str(e)}")
            raise
        
    def _check_rate_limit(self):
        """
        檢查並處理 API 請求限制
        """
        current_time = time.time()
        elapsed = current_time - self.weight_reset_time
        order_minute_elapsed = current_time - self.weight_reset_time
        order_second_elapsed = current_time - self.order_per_second_reset_time
        
        # 如果已經過了一秒，重置每秒計數器
        if order_second_elapsed >= 1:
            self.order_per_second = 0
            self.order_per_second_reset_time = current_time
        # 如果已經過了一分鐘，重置每分鐘計數器
        if order_minute_elapsed >= 60:
            self.order_per_minute = 0
            self.weight_reset_time = current_time
            self.weight_used = 0
            
        # 如果達到每秒限制，等待到下一秒
        if self.order_per_second >= self.max_order_per_second - 10:
            sleep_time = 1 - order_second_elapsed
            if sleep_time > 0:
                logger.info(f"達到每秒 API 請求限制，等待 {sleep_time:.2f} 秒...")
                time.sleep(sleep_time)
            self.order_per_second = 0
            self.order_per_second_reset_time = time.time()
            
        # 如果達到每分鐘限制，等待到下一分鐘
        if self.order_per_minute >= self.max_order_per_minute - 10:
            sleep_time = 60 - order_minute_elapsed
            if sleep_time > 0:
                logger.info(f"達到每分鐘 API 請求限制，等待 {sleep_time:.2f} 秒...")
                time.sleep(sleep_time)
            self.order_per_minute = 0
            self.weight_used = 0
            self.weight_reset_time = time.time()
            
        # 如果達到 weight 限制，等待到下一分鐘
        if self.weight_used >= self.max_weight_per_minute - 100: 
            sleep_time = 60 - elapsed
            if sleep_time > 0:
                logger.info(f"達到 API 請求權重限制，等待 {sleep_time:.2f} 秒...")
                time.sleep(sleep_time)
            self.weight_used = 0
            self.weight_reset_time = time.time()

    def _get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int
    ) -> List[Dict]:
        """
        從Binance獲取K線數據
        
        Args:
            symbol: 交易對
            interval: K線間隔
            start_time: 開始時間戳
            end_time: 結束時間戳
            
        Returns:
            List[Dict]: K線數據列表
        """
        try:
            # 檢查並處理 API 限制
            self._check_rate_limit()
            
            # 使用 continuous_klines 方法獲取永續合約K線數據
            klines = self.client.continuous_klines(
                pair=symbol,
                contractType='PERPETUAL',
                interval=interval,
                startTime=start_time,
                endTime=end_time,
                limit=1000
            )
            
            # 更新已使用的 weight 和次數
            self.weight_used += 5
            self.order_per_second += 1
            self.order_per_minute += 1
            
            return klines
            
        except Exception as e:
            logger.error(f"獲取K線數據失敗: {str(e)}")
            return []
            
    def _convert_to_dataframe(self, klines: List[Dict]) -> pd.DataFrame:
        """
        將K線數據轉換為DataFrame
        
        Args:
            klines: K線數據列表
            
        Returns:
            pd.DataFrame: 轉換後的DataFrame
        """
        if not klines:
            return pd.DataFrame()
            
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # 轉換數據類型
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
        
    def _get_filename(self, symbol: str, interval: str, start_date: str, end_date: str) -> str:
        """
        生成文件名
        
        Args:
            symbol: 交易對
            interval: K線間隔
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            str: 文件名
        """
        return f"{symbol}_{interval}_{start_date}_{end_date}.csv"
        
    def _check_data_gaps(
        self,
        df: pd.DataFrame,
        start_date: str,
        end_date: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        檢查數據是否有缺失的時間段
        
        Args:
            df: 現有數據
            start_date: 目標開始日期
            end_date: 目標結束日期
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (缺失的開始日期, 缺失的結束日期)
        """
        if df.empty:
            return start_date, end_date
            
        # 轉換日期字符串為datetime
        target_start = self._convert_to_utc(start_date)
        target_end = self._convert_to_utc(end_date)
        
        # 獲取現有數據的時間範圍
        data_start = df['timestamp'].min()
        data_end = df['timestamp'].max()
        
        # 檢查是否需要更新舊數據
        old_data_start = None
        if target_start < data_start:
            old_data_start = target_start.strftime("%Y-%m-%d")
            
        # 檢查是否需要更新新數據
        new_data_end = None
        if target_end > data_end:
            new_data_end = target_end.strftime("%Y-%m-%d")
            
        return old_data_start, new_data_end
        
    def _validate_data(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        驗證數據的完整性和質量
        
        Args:
            df: 要驗證的數據
            timeframe: K線間隔
        Returns:
            pd.DataFrame: 驗證並清理後的數據
        Raises:
            ValueError: 當發現數據問題時拋出異常
        """
        if df.empty:
            raise ValueError("數據為空")
            
        # 檢查重複的時間戳
        duplicates = df[df.duplicated(subset=['timestamp'], keep=False)]
        if not duplicates.empty:
            logger.warning(f"發現 {len(duplicates)} 個重複的時間戳")
            df = df.drop_duplicates(subset=['timestamp'], keep='first')

            
        # 按時間戳排序
        df = df.sort_values('timestamp')
        
        # 檢查時間間隔
        time_diff = df['timestamp'].diff()
        
        # 根據不同時間框架設定不同的 gap 大小
        if timeframe == '1h':
            max_gap = pd.Timedelta(hours=1)
        elif timeframe == '4h':
            max_gap = pd.Timedelta(hours=4)
        elif timeframe == '1d':
            max_gap = pd.Timedelta(days=1)
        else:
            logger.warning(f"未知的時間框架: {timeframe}")
            return df

            
        # 檢查超過最大間隔的數據
        gaps = time_diff[time_diff > max_gap]
        if not gaps.empty:
            error_msg = f"發現 {len(gaps)} 個大於{max_gap}的時間間隔"
            logger.error(error_msg)
            for idx, gap in gaps.items():
                if idx > 0:  # 確保不是第一個數據點
                    prev_timestamp = df.iloc[idx-1]['timestamp']
                    curr_timestamp = df.iloc[idx]['timestamp']
                    error_msg += f"\n在 {prev_timestamp} 和 {curr_timestamp} 之間有 {gap} 的間隔"
            raise ValueError(error_msg)
                
        logger.info(f"驗證數據完成，數據條數: {len(df)}")
        return df
        
    def _fetch_and_merge_data(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        existing_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        獲取並合併數據
        
        Args:
            symbol: 交易對
            interval: K線間隔
            start_date: 開始日期
            end_date: 結束日期
            existing_df: 現有數據
            
        Returns:
            pd.DataFrame: 合併後的數據
        """
        # 轉換日期為 UTC 時間戳
        start_timestamp = int(self._convert_to_utc(start_date).timestamp() * 1000)
        end_timestamp = int(self._convert_to_utc(end_date).timestamp() * 1000)

        # 如果有現有數據，計算需要獲取的時間範圍
        if existing_df is not None and not existing_df.empty:
            existing_start = int(existing_df['timestamp'].min().timestamp() * 1000)
            existing_end = int(existing_df['timestamp'].max().timestamp() * 1000)
            
            # 如果現有數據完全覆蓋所需範圍，直接返回
            if existing_start <= start_timestamp and existing_end >= end_timestamp:
                return existing_df
                
            # 計算需要獲取的時間範圍
            fetch_start = start_timestamp
            fetch_end = end_timestamp
            
            # 情況1：請求範圍既早於也晚於現有數據
            if start_timestamp < existing_start and end_timestamp > existing_end:
                # 需要獲取兩段數據：早於現有數據的部分和晚於現有數據的部分
                # 將UTC時間戳轉換為本地時間字符串，避免雙重時區轉換
                offset_hours = self._get_timezone_offset()
                
                # 現有數據開始時間（UTC）轉換為本地時間字符串
                existing_start_local = pd.Timestamp(existing_start, unit='ms') + pd.Timedelta(hours=offset_hours)
                early_end_date = existing_start_local.strftime('%Y-%m-%d %H:%M:%S')
                
                # 現有數據結束時間（UTC）轉換為本地時間字符串
                existing_end_local = pd.Timestamp(existing_end, unit='ms') + pd.Timedelta(hours=offset_hours)
                late_start_date = existing_end_local.strftime('%Y-%m-%d %H:%M:%S')
                
                early_df = self._fetch_and_merge_data(symbol, interval, start_date, early_end_date, None)
                late_df = self._fetch_and_merge_data(symbol, interval, late_start_date, end_date, None)
                
                # 合併兩段數據
                combined_df = pd.concat([early_df, late_df])
                combined_df = combined_df.sort_values('timestamp')
                combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')
                return combined_df
            # 情況2：請求範圍早於現有數據
            elif start_timestamp < existing_start:
                fetch_start = start_timestamp
                fetch_end = existing_start
            # 情況3：請求範圍晚於現有數據
            elif end_timestamp > existing_end:
                fetch_start = existing_end
                fetch_end = end_timestamp
            else:
                return existing_df
        else:
            fetch_start = start_timestamp
            fetch_end = end_timestamp
        
        # 計算每個時間框架的毫秒數
        if interval == '1h':
            interval_ms = 60 * 60 * 1000
        elif interval == '4h':
            interval_ms = 4 * 60 * 60 * 1000
        elif interval == '1d':
            interval_ms = 24 * 60 * 60 * 1000
        else:
            raise ValueError(f"不支援的時間框架: {interval}")
            
        # 計算每批次的最大時間範圍（1000根K線）
        batch_ms = interval_ms * 1000
        
        # 計算總請求次數
        total_ms = fetch_end - fetch_start
        total_requests = (total_ms + batch_ms - 1) // batch_ms  # 向上取整
        
        all_klines = []
        current_start = fetch_start
        
        # 使用tqdm顯示進度
        with tqdm(total=total_requests, desc=f"下載 {symbol} {interval} 數據") as pbar:
            while current_start < fetch_end:
                # 計算當前請求的結束時間，不超過1000根K線
                current_end = min(current_start + batch_ms, fetch_end)
                
                # 獲取當前時間段的數據
                klines = self._get_klines(symbol, interval, current_start, current_end)
                if klines:
                    all_klines.extend(klines)
                
                current_start = current_end
                pbar.update(1)
                    
        # 轉換為DataFrame
        new_df = self._convert_to_dataframe(all_klines)
            
        return new_df
        
    def _cleanup_old_files(self, symbol: str, interval: str, current_file: str):
        """
        刪除同一個交易對和時間間隔的所有舊文件
        
        Args:
            symbol: 交易對
            interval: K線間隔
            current_file: 當前保存的文件名
        """
        # 獲取所有相關文件
        files = [f for f in os.listdir(self.data_dir) 
                if f.startswith(f"{symbol}_{interval}_") and f.endswith('.csv')]
        
        # 刪除所有舊文件（除了當前正在保存的文件）
        for file in files:
            if file != current_file:
                try:
                    file_path = os.path.join(self.data_dir, file)
                    os.remove(file_path)
                    logger.info(f"已刪除舊文件: {file}")
                except Exception as e:
                    logger.error(f"刪除文件失敗 {file}: {str(e)}")
                    
    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        force_update: bool = False
    ) -> pd.DataFrame:
        """
        獲取K線數據，如果本地文件存在則直接讀取，否則從Binance下載
        
        Args:
            symbol: 交易對
            interval: K線間隔
            start_date: 開始日期 (YYYY-MM-DD)
            end_date: 結束日期 (YYYY-MM-DD)
            force_update: 是否強制更新數據（True: 強制重新下載所有數據, False: 只下載缺失部分）
            
        Returns:
            pd.DataFrame: K線數據
        """
        try:
            # 檢查是否存在同交易對同時間框架的文件
            existing_files = [f for f in os.listdir(self.data_dir) 
                            if f.startswith(f"{symbol}_{interval}_") and f.endswith('.csv')]
            
            # 獲取舊資料的開始時間和結束時間，並與請求時間比較，選出區間最長的開始和結束時間
            old_start_date = start_date
            old_end_date = end_date
            
            if existing_files:
                # 讀取現有文件獲取時間範圍
                existing_file = existing_files[0]
                existing_path = os.path.join(self.data_dir, existing_file)
                existing_df = pd.read_csv(existing_path, parse_dates=['timestamp'])
                
                # 獲取現有數據的時間範圍
                existing_start = existing_df['timestamp'].min()
                existing_end = existing_df['timestamp'].max()
                
                # 轉換為日期字符串格式
                existing_start_str = existing_start.strftime('%Y-%m-%d')
                existing_end_str = existing_end.strftime('%Y-%m-%d')
                
                # 比較並選擇最早的開始時間和最晚的結束時間
                old_start_date = min(start_date, existing_start_str)
                old_end_date = max(end_date, existing_end_str)
                
            # 構建文件名
            filename = self._get_filename(symbol, interval, old_start_date, old_end_date)
            filepath = os.path.join(self.data_dir, filename)
            
            # 轉換日期為 UTC 時間戳
            start_timestamp = int(self._convert_to_utc(start_date).timestamp() * 1000)
            end_timestamp = int(self._convert_to_utc(end_date).timestamp() * 1000)
            
            if force_update:
                # 強制更新：重新獲取 K 線數據
                df = self._fetch_and_merge_data(symbol, interval, start_date, end_date)

                # 重新構建文件名（使用請求的時間範圍）
                filename = self._get_filename(symbol, interval, start_date, end_date)
                filepath = os.path.join(self.data_dir, filename)
            else:
                if existing_files:
                    # 讀取現有文件
                    existing_file = existing_files[0]
                    existing_path = os.path.join(self.data_dir, existing_file)
                    existing_df = pd.read_csv(existing_path, parse_dates=['timestamp'])
                    
                    # 檢查時間範圍
                    existing_start = int(existing_df['timestamp'].min().timestamp() * 1000)
                    existing_end = int(existing_df['timestamp'].max().timestamp() * 1000)
                    
                    if existing_start <= start_timestamp and existing_end >= end_timestamp:
                        # 完全包含所需時間段，直接讀取並截取
                        logger.info(f"從現有文件讀取數據: {existing_file}")
                        # 使用 UTC 時間戳進行過濾，確保時間範圍正確
                        start_utc = self._convert_to_utc(start_date)
                        end_utc = self._convert_to_utc(end_date) + pd.Timedelta(days=1)
                        mask = (existing_df['timestamp'] >= start_utc) & (existing_df['timestamp'] <= end_utc)
                        df = existing_df[mask].copy()
                        
                        # 驗證過濾後的數據時間範圍
                        df_start = df['timestamp'].min()
                        df_end = df['timestamp'].max()
                        if df_start < start_utc or df_end > end_utc:
                            logger.warning("數據時間範圍不正確，重新獲取數據")
                            df = self._fetch_and_merge_data(symbol, interval, start_date, end_date, existing_df)
                        else:
                            logger.info(f"成功從現有文件讀取並過濾數據，數據條數: {len(df)}")
                            return df
                    else:
                        # 需要獲取缺失的時間段
                        logger.info("檢測到數據缺失，開始更新...")
                        df = self._fetch_and_merge_data(symbol, interval, start_date, end_date, existing_df)

                        # 合併現有數據
                        if not df.empty:
                            combined_df = pd.concat([existing_df, df])
                            combined_df = combined_df.sort_values('timestamp')
                            combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')
                            df = combined_df

                else:
                    # 不存在現有文件，完整獲取
                    logger.info("未找到現有數據文件，開始完整獲取...")
                    df = self._fetch_and_merge_data(symbol, interval, start_date, end_date)
            
            # 驗證數據完整性
            df = self._validate_data(df, interval)
            
            # 清理舊文件並保存新數據
            self._cleanup_old_files(symbol, interval, filename)
            os.makedirs(self.data_dir, exist_ok=True)
            df.to_csv(filepath, index=False)
            logger.info(f"數據已更新並保存到: {filename}")
            
            # 過濾出請求時間範圍內的數據
            start_utc = self._convert_to_utc(start_date)
            end_utc = self._convert_to_utc(end_date) + pd.Timedelta(days=1)
            mask = (df['timestamp'] >= start_utc) & (df['timestamp'] <= end_utc)
            df = df[mask].copy()
            
            return df
            
        except Exception as e:
            logger.error(f"獲取K線數據失敗: {str(e)}")
            raise
        
    def check_data_exists(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str
    ) -> bool:
        """
        檢查指定時間區間的數據是否存在
        
        Args:
            symbol: 交易對
            interval: K線間隔
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            bool: 數據是否存在
        """
        filename = self._get_filename(symbol, interval, start_date, end_date)
        filepath = os.path.join(self.data_dir, filename)
        return os.path.exists(filepath)
