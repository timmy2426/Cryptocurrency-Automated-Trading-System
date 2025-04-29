import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any
from decimal import Decimal

# 設置日誌
logger = logging.getLogger(__name__)

class EventLogger:
    """事件記錄器，用於記錄交易信息和程式錯誤"""
    
    def __init__(self):
        """
        初始化事件記錄器
        """
        # 獲取專案根目錄
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 構建日誌目錄路徑
        self.trade_log_dir = os.path.join(root_dir, "logs/trade_log")
        self.error_log_dir = os.path.join(root_dir, "logs/error_log")
        self.last_trade_date = None  
        self.last_error_date = None  
        
        # 創建日誌目錄
        os.makedirs(self.trade_log_dir, exist_ok=True)
        os.makedirs(self.error_log_dir, exist_ok=True)
        
    def trade_log(self, position_info: Dict[str, Any]) -> None:
        """
        記錄交易信息
        
        Args:
            position_info: 倉位信息字典
        """
        try:
            # 獲取交易對
            symbol = position_info.get('symbol')
            if not symbol:
                self.error_log("無法獲取交易對信息")
                return
                
            # 獲取當前日期
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # 檢查日期是否與上次記錄的日期不同
            if current_date != self.last_trade_date:
                self.last_trade_date = current_date
                logger.info(f"建立新的交易記錄文件: {current_date}.jsonl")
            
            # 構建日誌文件路徑
            log_file = os.path.join(self.trade_log_dir, f"{current_date}.jsonl")
            
            # 構建倉位信息，將 Decimal 類型轉換為 float
            trade_info = {
                "timestamp": int(time.time() * 1000),  # 毫秒時間戳
                **{k: float(v) if isinstance(v, Decimal) else v for k, v in position_info.items()}  # 轉換 Decimal 為 float
            }
            
            # 寫入日誌文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade_info, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"記錄交易信息失敗: {str(e)}")
            
    def error_log(self, error_message: str) -> None:
        """
        記錄程式錯誤
        
        Args:
            error_message: 錯誤信息
        """
        try:
            # 獲取當前日期
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # 檢查日期是否與上次記錄的日期不同
            if current_date != self.last_error_date:
                self.last_error_date = current_date
                logger.info(f"建立新的錯誤記錄文件: {current_date}.jsonl")
            
            # 構建日誌文件路徑
            log_file = os.path.join(self.error_log_dir, f"{current_date}.jsonl")
            
            # 構建錯誤信息
            error_info = {
                "timestamp": int(time.time() * 1000),  # 毫秒時間戳
                "error": str(error_message)  # 確保錯誤信息是字符串
            }
            
            # 寫入日誌文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(error_info, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"記錄錯誤信息失敗: {str(e)}")