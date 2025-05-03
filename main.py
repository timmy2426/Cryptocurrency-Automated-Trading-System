import logging
import signal
import sys
from typing import Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta
import time

from exchange import (
    BinanceAPI,
    OrderExecutor,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionStatus,
    CloseReason,
    PositionInfo,
    Order,
    OrderResult,
    AccountInfo
)
from core.trader import Trader
from core.position_manager import PositionManager
from core.event_logger import EventLogger
from discord_bot import (
    MessageFormatter,
    SendMessage,
    HealthCheck
)
from utils.config import check_config_parameters
from data.data_loader import DataLoader

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        """初始化交易機器人"""
        try:
            # 加載配置
            self._load_config()
            
            # 初始化組件
            self._init_components()
            
            # 設置信號處理
            self._setup_signal_handlers()
            
            logger.info("交易機器人初始化完成")
            
        except Exception as e:
            logger.error(f"初始化失敗: {str(e)}")
            raise
            
    def _load_config(self) -> None:
        """加載配置參數"""
        try:
            # 檢查必要的配置參數
            required_params = [
                'testnet',
                'base_endpoint',
                'testnet_rest_api_url',
                'webSocket_base_endpoint',
                'recv_window',
                'BINANCE_API_KEY',
                'BINANCE_API_SECRET',
                'BINANCE_TESTNET_API_KEY',
                'BINANCE_TESTNET_API_SECRET',
                'DISCORD_WEBHOOK_URL',
                'symbol_list'
            ]
            
            self.config = check_config_parameters(required_params)
            logger.info("配置加載成功")
            
        except Exception as e:
            logger.error(f"加載配置失敗: {str(e)}")
            raise
            
    def _init_components(self) -> None:
        """初始化各個組件"""
        try:
            # 初始化 Binance API
            self.api = BinanceAPI()

            # 初始化數據加載器
            self.data_loader = DataLoader(self.api)
            
            # 初始化訂單執行器
            self.order_executor = OrderExecutor(self.api)
            
            # 初始化消息格式化器和發送器
            self.message_formatter = MessageFormatter()
            self.send_message = SendMessage()
            
            # 初始化倉位管理器
            self.position_manager = PositionManager(
                order_executor=self.order_executor,
                message_formatter=self.message_formatter,
                send_message=self.send_message
            )
            
            # 初始心跳檢查
            self.health_check = HealthCheck( 
                self.position_manager.update_account_info, 
                self.position_manager.check_account_info
            )

            # 初始化交易者
            self.trader = Trader(
                order_executor=self.order_executor,
                symbol_list=self.config['symbol_list'],
                position_manager=self.position_manager,
                data_loader=self.data_loader
            )

            # 初始化事件日誌
            self.event_logger = EventLogger()
            
            logger.info("組件初始化成功")
            
        except Exception as e:
            logger.error(f"初始化組件失敗: {str(e)}")
            raise
            
    def _setup_signal_handlers(self) -> None:
        """設置信號處理器"""
        def signal_handler(signum, frame):
            logger.info("收到關閉信號，開始關閉程序...")
            self.stop()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def initial_run(self) -> None:
        """初始化運行"""
        try:
            # 啟動倉位監聽
            self.api.start_position_listener(
                order_callback=self.position_manager.update_position_info
            )
            logger.info("倉位監聽已啟動")
            
            # 更新初始帳戶信息
            self.position_manager.update_account_info({
                'status': '已啟動',
                'environment': '測試網' if self.config['testnet'] else '主網'
            })
            logger.info("初始帳戶信息已更新")

            # 啟動心跳檢查
            self.health_check.start()
            logger.info("心跳檢查已啟動")
            
            logger.info("交易機器人已初始化")
            
        except Exception as e:
            logger.error(f"初始化失敗: {str(e)}")
            self.stop()
            raise
        
    def start(self) -> None:
        """啟動交易機器人"""
        try:
            
            self.trader.run()
            
        except Exception as e:
            logger.error(f"交易機器人啟動失敗: {str(e)}")
            raise
            
    def stop(self) -> None:
        """停止交易機器人"""
        try:
            # 停止心跳檢查
            self.health_check.stop()
            logger.info("心跳檢查已停止")
            
            # 停止倉位監聽
            self.api.stop_position_listener()
            logger.info("倉位監聽已停止")
            
            # 更新帳戶狀態
            self.position_manager.update_account_info({
                'status': '已停止'
            })
            logger.info("帳戶狀態已更新")
            
            logger.info("交易機器人已停止")
            
        except Exception as e:
            logger.error(f"交易機器人停止失敗: {str(e)}")
            raise

def main():
    """主函數"""
    try:
        # 創建交易機器人
        bot = TradingBot()
        
        # 初始化運行
        bot.initial_run()

        # 保持程序運行
        while True:
            try:
                # 獲取當前時間
                now = datetime.now()
                
                # 計算到下一個15分鐘的等待時間
                next_time = now.replace(
                    minute=((now.minute // 15 + 1) * 15) % 60, 
                    second=0,
                    microsecond=0
                )
                
                # 如果計算出的時間已經過去，加15分鐘
                while next_time <= now:
                    next_time += timedelta(minutes=15)
                    
                wait_seconds = (next_time - now).total_seconds()
                
                # 等待到下一個15分鐘
                time.sleep(wait_seconds)
                
                # 記錄執行時間
                logger.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 執行交易檢查")
                
                # 執行交易機器人
                bot.start()
                
            except Exception as e:
                logger.error(f"交易機器人執行失敗: {str(e)}")
                time.sleep(60)  # 發生錯誤時等待1分鐘再重試
                
    except KeyboardInterrupt:
        logger.info("收到鍵盤中斷信號")
    except Exception as e:
        embed = bot.message_formatter.create_error_message(str(e))
        bot.send_message.send_error_message(embed)
        bot.event_logger.error_log(str(e))
        logger.error(f"程序異常: {str(e)}")
    finally:
        if 'bot' in locals():
            bot.stop()

if __name__ == "__main__":
    main()