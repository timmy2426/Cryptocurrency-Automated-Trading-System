import pytest
from decimal import Decimal
from types import SimpleNamespace
import time
import uuid
import sys
import os
from typing import Dict, Any, Optional

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.position_manager import PositionManager
from exchange import OrderExecutor, PositionInfo, Order, OrderSide, OrderType, OrderStatus

class MockOrderExecutor:
    """模擬訂單執行器"""
    def __init__(self):
        self.positions: Dict[str, PositionInfo] = {}
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.orderbook = {
            'bids': [[100, 1]],  # [價格, 數量]
            'asks': [[101, 1]]
        }
        self.account_info = {
            'totalWalletBalance': '10000',
            'totalUnrealizedProfit': '0',
            'totalMarginBalance': '10000',
            'totalInitialMargin': '0',
            'totalMaintMargin': '0',
            'totalPositionInitialMargin': '0',
            'totalOpenOrderInitialMargin': '0',
            'totalCrossWalletBalance': '10000',
            'availableBalance': '10000',
            'maxWithdrawAmount': '10000',
            'total_position_initial_margin': '0',
            'total_open_order_initial_margin': '0',
            'total_position_initial_margin': Decimal('0'),
            'total_wallet_balance': Decimal('10000'),
            'max_margin_usage': Decimal('0.8')
        }
        
    def get_order_book(self, symbol: str) -> Dict[str, list]:
        """獲取訂單簿"""
        return self.orderbook
        
    def get_position_risk(self, symbol: str) -> Optional[PositionInfo]:
        """獲取倉位風險信息"""
        return self.positions.get(symbol)
        
    def get_account_info(self) -> SimpleNamespace:
        """獲取帳戶信息"""
        return SimpleNamespace(**self.account_info)
        
    def new_order(self, **params) -> Dict[str, Any]:
        """模擬下單"""
        order_id = str(uuid.uuid4())
        self.orders[order_id] = params
        return {
            'orderId': order_id,
            'status': 'FILLED',
            **params
        }

class MockMessageFormatter:
    """模擬消息格式化器"""
    def create_open_position_message(self, **kwargs):
        """創建開倉消息"""
        return {}
        
    def create_close_position_message(self, **kwargs):
        """創建平倉消息"""
        return {}

@pytest.fixture
def mock_executor():
    """創建模擬訂單執行器"""
    return MockOrderExecutor()

@pytest.fixture
def mock_message_formatter():
    """創建模擬消息格式化器"""
    return MockMessageFormatter()

@pytest.fixture
def position_manager(mock_executor, mock_message_formatter):
    """創建倉位管理器"""
    return PositionManager(mock_executor, mock_message_formatter)

def test_check_margin_usage(position_manager, mock_executor):
    """測試檢查保證金使用率"""
    # 測試正常情況
    mock_executor.account_info['total_wallet_balance'] = Decimal('10000')
    mock_executor.account_info['total_position_initial_margin'] = Decimal('1000')
    position_manager.config['max_margin_usage'] = Decimal('0.8')
    assert position_manager.check_margin_usage() == True
    
    # 測試保證金使用率過高
    mock_executor.account_info['total_wallet_balance'] = Decimal('1000')
    mock_executor.account_info['total_position_initial_margin'] = Decimal('900')
    position_manager.config['max_margin_usage'] = Decimal('0.8')
    assert position_manager.check_margin_usage() == False

def test_check_daily_pnl(position_manager):
    """測試檢查日虧損"""
    # 測試正常情況
    position_manager.daily_loss = Decimal('0')
    position_manager.config['max_daily_loss'] = Decimal('1000')
    assert position_manager.check_daily_pnl() == True
    
    # 測試日虧損超過限制
    position_manager.daily_loss = Decimal('-2000')
    position_manager.config['max_daily_loss'] = Decimal('1000')
    assert position_manager.check_daily_pnl() == False

def test_check_daily_trades(position_manager):
    """測試檢查日交易次數"""
    # 測試正常情況
    position_manager.config['max_daily_trades'] = Decimal('5')
    position_manager.daily_trades = 3
    assert position_manager.check_daily_trades() == True
    
    # 測試日交易次數超過限制
    position_manager.daily_trades = 11
    assert position_manager.check_daily_trades() == False

def test_check_cooldown(position_manager):
    """測試檢查冷卻期"""
    # 測試正常情況
    assert position_manager.check_cooldown() == True
    
    # 測試冷卻期
    position_manager.is_cooldown_activate = True
    position_manager.cooldown_start_time = int(time.time() * 1000)
    assert position_manager.check_cooldown() == False

def test_can_close_position(position_manager):
    """測試是否可以平倉"""
    # 測試持倉時間超過限制
    position_manager.config['max_holding_bars'] = 6
    position_manager.positions['BTCUSDT'] = {
        'open_time': int(time.time() * 1000) - 7200000,  # 2小時前
        'close_time': None,
        'close_price': Decimal('0'),
        'close_reason': None,
        'pnl': Decimal('0')
    }
    assert position_manager.can_close_position('BTCUSDT') == True
    
    # 測試持倉時間不足
    position_manager.positions['BTCUSDT']['open_time'] = int(time.time() * 1000) - 1800000  # 30分鐘前
    assert position_manager.can_close_position('BTCUSDT') == False

def test_check_slippage(position_manager, mock_executor):
    """測試滑價檢查"""
    # 測試正常情況
    position_manager.config['slippage_percent'] = Decimal('1')
    mock_executor.orderbook = {
        'bids': [[100, 1]],
        'asks': [[100.5, 1]]  # 0.5% 滑價
    }
    assert position_manager.check_slippage('BTCUSDT') == True
    
    # 測試滑價過高
    mock_executor.orderbook = {
        'bids': [[100, 1]],
        'asks': [[110, 1]]  # 10% 滑價
    }
    assert position_manager.check_slippage('BTCUSDT') == False
    


