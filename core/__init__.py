"""
核心模組，包含交易系統的主要組件
"""

from .trader import Trader
from .strategy import Strategy
from .position_manager import PositionManager
from .signals import SignalGenerator
from .risk_control import RiskControl
from .event_logger import EventLogger

__all__ = [
    'Trader',
    'Strategy',
    'PositionManager',
    'SignalGenerator',
    'RiskControl',
    'EventLogger'
]
