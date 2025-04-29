import threading
import time
from datetime import datetime, timedelta
import logging
from typing import Callable
from .message_format import MessageFormatter
from .send_message import SendMessage

# 設置日誌
logger = logging.getLogger(__name__)

class HealthCheck:
    """心跳檢查類"""
    
    def __init__(self, update_account_info: Callable[[], None], check_account_info: Callable[[], None]):
        """
        初始化心跳檢查器
        
        Args:
            update_account_info: 更新帳戶信息的方法
        """
        self.update_account_info = update_account_info
        self.check_account_info = check_account_info
        self.message_formatter = MessageFormatter()
        self.send_message = SendMessage()
        self._running = False
        self._thread = None
        self._is_first_check = True
        
    def start(self) -> None:
        """啟動心跳檢查"""
        if self._running:
            logger.warning("心跳檢查已經在運行中")
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        logger.info("心跳檢查已啟動")
        
    def stop(self) -> None:
        """停止心跳檢查"""
        if not self._running:
            logger.warning("心跳檢查未在運行")
            return
        
        # 更新帳戶信息
        self.update_account_info({'status': '已停止'})

        # 檢查帳戶信息
        account_info = self.check_account_info()
            
        # 創建心跳檢查消息
        embed = self.message_formatter.create_heartbeat_message(
            status=account_info['status'],
            environment=account_info['environment'],
            account_equity=account_info['account_equity'],
            unrealized_pnl=account_info['unrealized_pnl'],
            unrealized_pnl_percentage=account_info['unrealized_pnl_percentage'],
            positions=account_info['positions']
        )
            
        # 發送心跳檢查消息
        self.send_message.send_heartbeat_message(embed)
            
        logger.info("心跳檢查完成")
            
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("心跳檢查已停止")
        
    def _check_loop(self) -> None:
        """心跳檢查循環"""
        while self._running:
            try:
                # 執行心跳檢查
                self._perform_check()

                # 獲取當前時間
                now = datetime.now()
                
                # 計算到下一個整點的等待時間
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait_seconds = (next_hour - now).total_seconds()
                
                # 等待到下一個整點
                time.sleep(wait_seconds)
                
            except Exception as e:
                logger.error(f"心跳檢查失敗: {str(e)}")
                time.sleep(60)  # 發生錯誤時等待1分鐘再重試
                
    def _perform_check(self) -> None:
        """執行心跳檢查"""
        try:
            # 更新帳戶信息
            if not self._is_first_check:
                self.update_account_info({'status': '運行中'})
            self._is_first_check = False

            # 檢查帳戶信息
            account_info = self.check_account_info()
            
            # 創建心跳檢查消息
            embed = self.message_formatter.create_heartbeat_message(
                status=account_info['status'],
                environment=account_info['environment'],
                account_equity=account_info['account_equity'],
                unrealized_pnl=account_info['unrealized_pnl'],
                unrealized_pnl_percentage=account_info['unrealized_pnl_percentage'],
                positions=account_info['positions']
            )
            
            # 發送心跳檢查消息
            self.send_message.send_heartbeat_message(embed)
            
            logger.info("心跳檢查完成")
            
        except Exception as e:
            logger.error(f"執行心跳檢查失敗: {str(e)}")
            raise