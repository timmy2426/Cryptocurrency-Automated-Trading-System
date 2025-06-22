import os
import sys
import unittest
import pandas as pd

# 添加專案根目錄到 Python 路徑
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from backtest.metrics import PerformanceMetrics

class TestPerformanceMetrics(unittest.TestCase):
    """測試績效計算類別"""
    
    def setUp(self):
        """測試前的準備工作"""
        # 設定測試用的配置
        self.config = {
            'risk_free_rate': 0.025,  # 2.5% 無風險利率
            'initial_balance': 10000  # 初始資金
        }
        
        # 初始化績效計算類別
        self.metrics = PerformanceMetrics(self.config)
        
    def test_run_with_specific_file(self):
        """測試使用指定檔案執行績效分析"""
        
        # 使用指定檔案初始化績效計算類別
        file_name = 'trades_20250622_082040.jsonl'
        metrics = PerformanceMetrics(self.config, file_name)
        
        # 執行績效分析
        metrics.run()
        
        # 確認報表已建立
        expected_filename = f"回測績效分析報告_{file_name}.xlsx"
        self.assertTrue(os.path.exists(expected_filename))
        
        # 讀取報表確認內容
        with pd.ExcelFile(expected_filename) as xls:
            # 確認所有工作表都存在
            self.assertIn("總體摘要", xls.sheet_names)
            self.assertIn("每日績效", xls.sheet_names)
            self.assertIn("交易對績效", xls.sheet_names)
            self.assertIn("策略分析", xls.sheet_names)
            self.assertIn("盤勢分析", xls.sheet_names)
            
            # 讀取總體摘要確認關鍵指標
            summary_df = pd.read_excel(xls, "總體摘要")
            self.assertIn("總交易次數 (筆)", summary_df["指標"].values)
            self.assertIn("年化報酬率 (%)", summary_df["指標"].values)
            self.assertIn("夏普比率", summary_df["指標"].values)
            
            # 讀取每日績效確認欄位（已移除策略和盤勢欄位）
            daily_df = pd.read_excel(xls, "每日績效")
            self.assertIn("日期", daily_df.columns)
            self.assertIn("當日損益 (USDT)", daily_df.columns)
            self.assertIn("交易次數 (筆)", daily_df.columns)
            self.assertIn("平均損益 (USDT)", daily_df.columns)
            self.assertIn("累計損益 (USDT)", daily_df.columns)
            
            # 讀取交易對績效確認欄位（包含完整的共同績效指標）
            symbol_df = pd.read_excel(xls, "交易對績效")
            self.assertIn("交易對", symbol_df.columns)
            self.assertIn("交易次數 (筆)", symbol_df.columns)
            self.assertIn("總盈虧 (USDT)", symbol_df.columns)
            self.assertIn("勝率 (%)", symbol_df.columns)
            self.assertIn("年化報酬率 (%)", symbol_df.columns)
            self.assertIn("平均獲利 (USDT)", symbol_df.columns)
            self.assertIn("平均虧損 (USDT)", symbol_df.columns)
            self.assertIn("盈虧比", symbol_df.columns)
            self.assertIn("最大回撤 (USDT)", symbol_df.columns)
            self.assertIn("最大回撤 (%)", symbol_df.columns)
            self.assertIn("獲利因子", symbol_df.columns)
            self.assertIn("夏普比率", symbol_df.columns)
            self.assertIn("卡瑪比率", symbol_df.columns)
            self.assertIn("平均持倉時間 (分鐘)", symbol_df.columns)
            
            # 讀取策略分析確認欄位（包含完整的共同績效指標）
            strategy_df = pd.read_excel(xls, "策略分析")
            self.assertIn("策略", strategy_df.columns)
            self.assertIn("交易次數 (筆)", strategy_df.columns)
            self.assertIn("總盈虧 (USDT)", strategy_df.columns)
            self.assertIn("勝率 (%)", strategy_df.columns)
            self.assertIn("年化報酬率 (%)", strategy_df.columns)
            self.assertIn("平均獲利 (USDT)", strategy_df.columns)
            self.assertIn("平均虧損 (USDT)", strategy_df.columns)
            self.assertIn("盈虧比", strategy_df.columns)
            self.assertIn("最大回撤 (USDT)", strategy_df.columns)
            self.assertIn("最大回撤 (%)", strategy_df.columns)
            self.assertIn("獲利因子", strategy_df.columns)
            self.assertIn("夏普比率", strategy_df.columns)
            self.assertIn("卡瑪比率", strategy_df.columns)
            self.assertIn("平均持倉時間 (分鐘)", strategy_df.columns)
            
            # 讀取盤勢分析確認欄位（包含完整的共同績效指標）
            market_df = pd.read_excel(xls, "盤勢分析")
            self.assertIn("盤勢組合", market_df.columns)
            self.assertIn("策略", market_df.columns)
            self.assertIn("交易次數 (筆)", market_df.columns)
            self.assertIn("總盈虧 (USDT)", market_df.columns)
            self.assertIn("勝率 (%)", market_df.columns)
            self.assertIn("年化報酬率 (%)", market_df.columns)
            self.assertIn("平均獲利 (USDT)", market_df.columns)
            self.assertIn("平均虧損 (USDT)", market_df.columns)
            self.assertIn("盈虧比", market_df.columns)
            self.assertIn("最大回撤 (USDT)", market_df.columns)
            self.assertIn("最大回撤 (%)", market_df.columns)
            self.assertIn("獲利因子", market_df.columns)
            self.assertIn("夏普比率", market_df.columns)
            self.assertIn("卡瑪比率", market_df.columns)
            self.assertIn("平均持倉時間 (分鐘)", market_df.columns)

if __name__ == '__main__':
    unittest.main()
