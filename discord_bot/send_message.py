from discord_webhook import DiscordWebhook, DiscordEmbed
from .message_format import MessageFormatter
from utils.config import check_config_parameters
import logging
import time

# 設置日誌
logger = logging.getLogger(__name__)

class SendMessage:
    """Discord 訊息發送類"""
    
    def __init__(self):
        """
        初始化訊息發送器
        """
        self._load_config()
        self.message_formatter = MessageFormatter()
        
    def _load_config(self) -> None:
        """加載配置參數"""
        try:
            # 檢查配置參數
            required_params = [
                'DISCORD_WEBHOOK_URL'
            ]
            
            self.config = check_config_parameters(required_params)
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in self.config.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
                
            self.webhook_url = self.config['DISCORD_WEBHOOK_URL']
                
        except Exception as e:
            logger.error(f"加載配置參數失敗: {str(e)}")
            raise
            
    def _send_message(self, embed: DiscordEmbed, message_type: str) -> None:
        """
        發送訊息的內部方法
        
        Args:
            embed: Discord Embed 物件
            message_type: 訊息類型（用於日誌）
        """
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            webhook.add_embed(embed)

            max_retries = 12
            retry_count = 0
            while retry_count < max_retries:
                try:
                    webhook.execute()
                    break
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"發送{message_type}訊息失敗，第 {retry_count} 次重試")
                    if retry_count >= max_retries:
                        logger.error(f"發送{message_type}訊息失敗，已達到最大重試次數")
                        raise
                    time.sleep(5)

        except Exception as e:
            logger.error(f"發送{message_type}訊息失敗: {str(e)}")
        
    def send_close_position_message(self, embed: DiscordEmbed) -> None:
        """
        發送平倉訊息
        
        Args:
            embed: Discord Embed 物件
        """
        self._send_message(embed, "平倉")
            
    def send_open_position_message(self, embed: DiscordEmbed) -> None:
        """
        發送開倉訊息
        
        Args:
            embed: Discord Embed 物件
        """
        self._send_message(embed, "開倉")
            
    def send_heartbeat_message(self, embed: DiscordEmbed) -> None:
        """
        發送心跳訊息
        
        Args:
            embed: Discord Embed 物件
        """
        self._send_message(embed, "心跳")
            
    def send_error_message(self, embed: DiscordEmbed) -> None:
        """
        發送錯誤訊息
        
        Args:
            embed: Discord Embed 物件
        """
        self._send_message(embed, "錯誤")