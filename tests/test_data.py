"""
測試數據管理器功能
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import logging

# 添加專案根目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from backtest.data_manager import DataManager

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_data_manager():
    """測試數據管理器功能"""
    try:
        # 初始化數據管理器
        data_manager = DataManager()
        
        # 測試場景1：強制更新模式
        logger.info("\n測試場景1：強制更新模式")
        df_force = data_manager.fetch_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_date="2024-01-05",
            end_date="2024-06-10",
            force_update=True
        )
        assert not df_force.empty, "強制更新模式獲取數據為空"
        assert len(df_force) > 0, "強制更新模式獲取數據條數為0"
        logger.info(f"強制更新模式獲取數據成功，數據條數: {len(df_force)}")
        
        # 測試場景2：現有數據完全包含所需時間段
        logger.info("\n測試場景2：現有數據完全包含所需時間段")
        df_subset = data_manager.fetch_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_date="2024-01-07",
            end_date="2024-06-08",
            force_update=False
        )
        assert not df_subset.empty, "子集數據為空"
        assert len(df_subset) > 0, "子集數據條數為0"
        logger.info(f"子集數據獲取成功，數據條數: {len(df_subset)}")
        
        # 驗證子集數據的時間範圍
        subset_min = df_subset['timestamp'].min()
        subset_max = df_subset['timestamp'].max()
        subset_start = pd.Timestamp("2024-01-07")
        subset_end = pd.Timestamp("2024-06-08") + pd.Timedelta(days=1)
        
        # 使用 data_manager 的時區轉換方法
        subset_start_utc = data_manager._convert_to_utc(subset_start)
        subset_end_utc = data_manager._convert_to_utc(subset_end)
        
        logger.info(f"請求時間範圍: {subset_start_utc} 到 {subset_end_utc}")
        logger.info(f"實際數據範圍: {subset_min} 到 {subset_max}")
        
        assert subset_min >= subset_start_utc, "子集數據開始時間早於請求時間"
        assert subset_max <= subset_end_utc, "子集數據結束時間晚於請求時間"
        
        # 測試場景3.1：測試較早時間段
        logger.info("\n測試場景3.1：測試較早時間段")
        df_older = data_manager.fetch_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_date="2024-01-01",
            end_date="2024-06-08",
            force_update=False
        )
        assert not df_older.empty, "較早時間段數據為空"
        assert len(df_older) > 0, "較早時間段數據條數為0"
        logger.info(f"較早時間段數據獲取成功，數據條數: {len(df_older)}")
        
        # 測試場景3.2：測試較晚時間段
        logger.info("\n測試場景3.2：測試較晚時間段")
        df_newer = data_manager.fetch_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_date="2024-01-06",
            end_date="2024-06-15",
            force_update=False
        )
        assert not df_newer.empty, "較晚時間段數據為空"
        assert len(df_newer) > 0, "較晚時間段數據條數為0"
        logger.info(f"較晚時間段數據獲取成功，數據條數: {len(df_newer)}")
        
        # 測試場景4：測試新交易對
        logger.info("\n測試場景4：測試新交易對")
        df_new = data_manager.fetch_klines(
            symbol="ETHUSDT",
            interval="1h",
            start_date="2024-01-01",
            end_date="2024-01-05",
            force_update=False
        )
        assert not df_new.empty, "新交易對數據為空"
        assert len(df_new) > 0, "新交易對數據條數為0"
        logger.info(f"新交易對數據獲取成功，數據條數: {len(df_new)}")
        
        # 驗證所有數據的完整性
        for df in [df_force, df_subset, df_older, df_newer, df_new]:
            # 檢查時間戳順序
            assert df['timestamp'].is_monotonic_increasing, "時間戳不是嚴格遞增的"
            # 檢查重複時間戳
            assert not df['timestamp'].duplicated().any(), "存在重複的時間戳"
            # 檢查數據類型
            assert df['open'].dtype == 'float64', "open 列數據類型不正確"
            assert df['high'].dtype == 'float64', "high 列數據類型不正確"
            assert df['low'].dtype == 'float64', "low 列數據類型不正確"
            assert df['close'].dtype == 'float64', "close 列數據類型不正確"
            assert df['volume'].dtype == 'float64', "volume 列數據類型不正確"
        
        logger.info("\n所有測試場景通過！")
        
    except Exception as e:
        logger.error(f"測試失敗: {str(e)}")
        raise

if __name__ == "__main__":
    test_data_manager()
