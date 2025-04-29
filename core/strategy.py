import logging
from typing import Optional
from core.risk_control import RiskControl
from core.signals import SignalGenerator
from core.position_manager import PositionManager
import pandas as pd

logger = logging.getLogger(__name__)

class Strategy:
    """策略選擇器"""
    
    def __init__(self, position_manager: PositionManager):
        """
        初始化策略選擇器
        
        Args:
            position_manager: 倉位管理器實例
        """
        self.position_manager = position_manager
        self.risk_control = RiskControl()
        self.signal_generator = SignalGenerator()
        
    def select(self, symbol: str, df_15min: pd.DataFrame, df_1h: pd.DataFrame, df_4h: pd.DataFrame) -> str:
        """
        根據市場情況選擇交易策略
        
        Args:
            symbol: 交易對
            df_15min: 15分鐘K線數據
            df_1h: 1小時K線數據
            df_4h: 4小時K線數據
            
        Returns:
            str: 策略名稱，若無合適策略則返回 "no_trade"
        """
        try:
            # 1. 使用 risk_control 中的 select_strategy 方法選擇策略
            strategy_type = self.risk_control.select_strategy(df_15min, df_1h, df_4h)

            logger.info(f"策略選擇器：選擇策略: {strategy_type}")
            
            # 若為 "no_trade" 則直接返回
            if strategy_type == "no_trade":
                return "no_trade"

            # 計算技術指標
            indicators = self.signal_generator.calculate_indicators(df_15min)
            
            # 2. 根據策略類型檢查信號
            if strategy_type == "trend":
                # 檢查順勢開倉信號
                long_signal = self.signal_generator.is_trend_long_entry(df_15min, indicators).iloc[-2]
                short_signal = self.signal_generator.is_trend_short_entry(df_15min, indicators).iloc[-2]
                
                if long_signal and self.position_manager.check_slippage(symbol):
                    return "trend_long"
                elif short_signal and self.position_manager.check_slippage(symbol):
                    return "trend_short"
                    
            elif strategy_type == "mean_reversion":
                # 檢查逆勢開倉信號
                long_signal = self.signal_generator.is_mean_rev_long_entry(df_15min, indicators).iloc[-2]
                short_signal = self.signal_generator.is_mean_rev_short_entry(df_15min, indicators).iloc[-2]
                
                if long_signal and self.position_manager.check_slippage(symbol):
                    return "mean_rev_long"
                elif short_signal and self.position_manager.check_slippage(symbol):
                    return "mean_rev_short"
                    
            return "no_trade"

        except Exception as e:
            logger.error(f"選擇策略失敗: {str(e)}")
            return "no_trade"