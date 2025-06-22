"""
測試回測引擎的功能
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
import os
import sys
import shutil
from typing import Dict
import logging

# 添加專案根目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from backtest.engine import BacktestEngine

# 創建日誌器
logger = logging.getLogger(__name__)

class TestBacktestEngine(unittest.TestCase):
    """測試回測引擎"""
    
    def setUp(self):
        """測試前的準備工作"""
        # 創建測試用的配置
        self.config = {
            'symbol': ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'BNBUSDT', 'SOLUSDT', 'DOGEUSDT', 'TRXUSDT', 'ADAUSDT'],
            'start_date': '2022-01-01',
            'end_date': '2024-12-30',
            'initial_balance': 10000,
            'leverage': 5,
            'fee': 0.0005,
            'slippage': 0.0005
        }
        
        # 初始化回測引擎
        self.engine = BacktestEngine(self.config)
        
    def test_run(self):
        """測試回測執行"""
        # 執行回測
        self.engine.run()
        
        # 檢查權益曲線
        self.assertGreater(len(self.engine.broker.equity_curve), 0)
        
        # 檢查賬戶信息
        account_info = self.engine.broker.get_account_info()
        self.assertIsInstance(account_info['account_equity'], Decimal)
        self.assertIsInstance(account_info['total_trades'], int)
        
        # 計算績效指標
        equity_curve = self.engine.broker.equity_curve
        initial_equity = equity_curve[0]['equity']
        final_equity = equity_curve[-1]['equity']
        
        # 計算總收益率
        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        # 計算最大回撤
        max_drawdown = 0
        peak = initial_equity
        for point in equity_curve:
            equity = point['equity']
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)
        
        # 計算勝率
        total_trades = account_info['total_trades']
        winning_trades = sum(1 for trade in self.engine.broker.trades if trade['pnl'] > 0)
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
        
        # 計算平均獲利和虧損
        winning_pnls = [trade['pnl'] for trade in self.engine.broker.trades if trade['pnl'] > 0]
        losing_pnls = [trade['pnl'] for trade in self.engine.broker.trades if trade['pnl'] < 0]
        avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0
        
        # 計算獲利因子
        total_profit = sum(winning_pnls) if winning_pnls else 0
        total_loss = abs(sum(losing_pnls)) if losing_pnls else 0
        profit_factor = total_profit / total_loss if total_loss != 0 else float('inf')
        
        # 計算最大連續獲利和虧損
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_consecutive_wins = 0
        current_consecutive_losses = 0
        
        for trade in self.engine.broker.trades:
            if trade['pnl'] > 0:
                current_consecutive_wins += 1
                current_consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_consecutive_wins)
            else:
                current_consecutive_losses += 1
                current_consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
        
        # 計算夏普值
        # 1. 計算每日報酬率
        daily_returns = []
        prev_equity = equity_curve[0]['equity']
        prev_date = datetime.fromtimestamp(equity_curve[0]['timestamp']/1000).date()
        
        for point in equity_curve[1:]:
            current_equity = point['equity']
            current_date = datetime.fromtimestamp(point['timestamp']/1000).date()
            
            # 如果日期改變，計算日報酬率
            if current_date != prev_date:
                daily_return = (current_equity - prev_equity) / prev_equity
                daily_returns.append(daily_return)
                prev_equity = current_equity
                prev_date = current_date
        
        # 2. 計算年化報酬率和標準差
        if daily_returns:
            avg_daily_return = sum(daily_returns) / len(daily_returns)
            daily_std = (sum((r - avg_daily_return) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
            
            # 年化報酬率 (假設一年252個交易日)
            annual_return = avg_daily_return * 365
            annual_std = daily_std * (365 ** 0.5)
            
            # 無風險利率 (假設為2%)
            risk_free_rate = 0.025
            
            # 計算夏普值
            sharpe_ratio = (annual_return - risk_free_rate) / annual_std if annual_std != 0 else 0
        else:
            sharpe_ratio = 0
        
        # 輸出績效報告
        logger.info("\n=== 回測績效報告 ===")
        logger.info(f"初始資金: {initial_equity:.2f} USDT")
        logger.info(f"最終資金: {final_equity:.2f} USDT")
        logger.info(f"總收益率: {total_return:.2f}%")
        logger.info(f"最大回撤: {max_drawdown:.2f}%")
        logger.info(f"總交易次數: {total_trades}")
        logger.info(f"勝率: {win_rate:.2f}%")
        logger.info(f"平均獲利: {avg_win:.2f} USDT")
        logger.info(f"平均虧損: {avg_loss:.2f} USDT")
        logger.info(f"獲利因子: {profit_factor:.2f}")
        logger.info(f"最大連續獲利: {max_consecutive_wins}")
        logger.info(f"最大連續虧損: {max_consecutive_losses}")
        logger.info(f"夏普值: {sharpe_ratio:.2f}")
        logger.info("===================")

if __name__ == '__main__':
    unittest.main()
