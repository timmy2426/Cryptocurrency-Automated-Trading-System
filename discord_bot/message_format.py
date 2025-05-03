from discord_webhook import DiscordWebhook, DiscordEmbed
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime

class MessageFormatter:
    """Discord 消息格式化器"""
    
    # 顏色定義
    COLOR_PROFIT = 0x00FF00  # 綠色
    COLOR_LOSS = 0xFF0000    # 紅色
    COLOR_BREAKEVEN = 0x000000  # 黑色
    COLOR_OPEN = 0x0000FF    # 藍色
    COLOR_HEARTBEAT = 0x808080  # 灰色
    COLOR_ERROR = 0x8B0000   # 深紅色
    
    def _format_timestamp(self, timestamp: int) -> str:
        """格式化時間戳"""
        return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
    
    def _str_content_translate(self, content: str) -> str:
        """將字串內容轉換為適合discord的格式"""
        content_dict = {
        'BUY': '買入',
        'SELL': '賣出',
        'trend_long': '順勢做多',
        'trend_short': '順勢做空',
        'mean_rev_long': '逆勢做多',
        'mean_rev_short': '逆勢做空',
        'STOP_LOSS': '止損出場',
        'TAKE_PROFIT': '止盈出場',
        'TRAILING_STOP': '移動止損出場',
        'MANUAL': '主動出場',
        'LIQUIDATION': '強制平倉',
        'OTHER': '其他'
        }
        return content_dict.get(content, '無')
    
    def create_close_position_message(
        self,
        symbol: str,
        side: str,
        strategy: str,
        open_time: int,
        close_time: int,
        open_price: Decimal,
        close_price: Decimal,
        close_reason: str,
        position_size: Decimal,
        pnl: Decimal,
        pnl_percentage: Decimal
    ) -> DiscordEmbed:
        """創建平倉消息"""
        # 根據盈虧設置顏色
        if pnl > 0:
            color = self.COLOR_PROFIT
        elif pnl < 0:
            color = self.COLOR_LOSS
        else:
            color = self.COLOR_BREAKEVEN
            
        embed = DiscordEmbed(
            title="平倉通知",
            color=color
        )
        
        # 添加字段
        embed.add_embed_field(name="交易對", value=symbol, inline=False)
        embed.add_embed_field(name="交易方向", value=self._str_content_translate(side) if side is not None else "null", inline=False)
        embed.add_embed_field(name="交易策略", value=self._str_content_translate(strategy) if strategy is not None else "手動買賣", inline=False)
        embed.add_embed_field(name="開倉時間", value=self._format_timestamp(open_time) if open_time is not None else "null", inline=False)
        embed.add_embed_field(name="平倉時間", value=self._format_timestamp(close_time) if close_time is not None else "null", inline=False)
        embed.add_embed_field(name="開倉價格", value=f"{open_price} USDT" if open_price is not None else "null", inline=False)
        embed.add_embed_field(name="平倉價格", value=f"{close_price} USDT" if close_price is not None else "null", inline=False)
        embed.add_embed_field(name="平倉原因", value=self._str_content_translate(close_reason) if close_reason is not None else "null", inline=False)
        embed.add_embed_field(name="倉位大小", value=f"{position_size} USDT" if position_size is not None else "null", inline=False)
        embed.add_embed_field(name="盈虧", value=f"{pnl} USDT" if pnl is not None else "null", inline=False)
        embed.add_embed_field(name="盈虧率", value=f"{pnl_percentage} %" if pnl_percentage is not None else "null", inline=False)
        
        return embed
    
    def create_open_position_message(
        self,
        symbol: str,
        side: str,
        strategy: str,
        open_time: int,
        open_price: Decimal,
        position_size: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        trailing_stop: Optional[Decimal] = None,
        price_rate: Optional[Decimal] = None
    ) -> DiscordEmbed:
        """創建開倉消息"""
        embed = DiscordEmbed(
            title="開倉通知",
            color=self.COLOR_OPEN
        )
        
        # 添加基本字段
        embed.add_embed_field(name="交易對", value=symbol, inline=False)
        embed.add_embed_field(name="交易方向", value=self._str_content_translate(side) if side is not None else "null", inline=False)
        embed.add_embed_field(name="交易策略", value=self._str_content_translate(strategy) if strategy is not None else "手動買賣", inline=False)
        embed.add_embed_field(name="開倉時間", value=self._format_timestamp(open_time) if open_time is not None else "null", inline=False)
        embed.add_embed_field(name="開倉價格", value=f"{open_price} USDT" if open_price is not None else "null", inline=False)
        embed.add_embed_field(name="倉位大小(USDT)", value=f"{position_size} USDT" if position_size is not None else "null", inline=False)
        
        # 添加可選字段
        if stop_loss is not None:
            embed.add_embed_field(name="止損價格", value=f"{stop_loss} USDT", inline=False)
        if take_profit is not None:
            embed.add_embed_field(name="止盈價格", value=f"{take_profit} USDT", inline=False)
        if trailing_stop is not None:
            embed.add_embed_field(name="移動止損觸發價格", value=f"{trailing_stop} USDT", inline=False)
        if price_rate is not None:
            embed.add_embed_field(name="回調率", value=f"{price_rate} %", inline=False)
        
        return embed
    
    def create_heartbeat_message(
        self,
        status: str,
        environment: str,
        account_equity: Decimal,
        daily_trades: int,
        daily_pnl: Decimal,
        unrealized_pnl: Decimal,
        unrealized_pnl_percentage: Decimal,
        positions: List[str]
    ) -> DiscordEmbed:
        """創建心跳檢查消息"""
        embed = DiscordEmbed(
            title="狀態通知",
            color=self.COLOR_HEARTBEAT
        )
        
        embed.add_embed_field(name="機器人狀態", value=status, inline=False)
        embed.add_embed_field(name="運行環境", value=environment, inline=False)
        embed.add_embed_field(name="帳戶權益", value=f"{account_equity} USDT" if account_equity is not None else "null", inline=False)
        embed.add_embed_field(name="單日開倉次數", value=f"{daily_trades} 次" if daily_trades is not None else "null", inline=False)
        embed.add_embed_field(name="單日累計盈虧", value=f"{daily_pnl} USDT" if daily_pnl is not None else "null", inline=False)
        embed.add_embed_field(name="未實現盈虧", value=f"{unrealized_pnl} USDT" if unrealized_pnl is not None else "null", inline=False)
        embed.add_embed_field(name="未實現盈虧率", value=f"{unrealized_pnl_percentage} %" if unrealized_pnl_percentage is not None else "null", inline=False)
        embed.add_embed_field(name="目前持倉交易對", value="、".join(positions) if positions else "無", inline=False)
        
        return embed
    
    def create_error_message(self, error_message: str) -> DiscordEmbed:
        """創建錯誤消息"""
        embed = DiscordEmbed(
            title="錯誤通知",
            color=self.COLOR_ERROR
        )
        
        embed.add_embed_field(name="錯誤訊息", value=error_message, inline=False)
        
        return embed