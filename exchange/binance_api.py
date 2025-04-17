from binance.client import Client
from binance.exceptions import BinanceAPIException
import pandas as pd
from typing import Optional, Union, List, Callable, Dict, Tuple
import logging
from datetime import datetime
import os
import yaml
import json
import time
import uuid
import base64
from websocket import create_connection, WebSocketApp
from dotenv import load_dotenv
from enum import Enum
from dataclasses import dataclass
from decimal import Decimal
import hmac
import hashlib
import websocket
import threading

from .enums import OrderSide, PositionStatus, CloseReason
from .data_models import PositionInfo, AccountInfo
from .config import load_config

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceAPI:
    """Binance API 封裝類"""
    
    # K線時間週期映射
    KLINE_INTERVALS = {
        '1m': Client.KLINE_INTERVAL_1MINUTE,
        '3m': Client.KLINE_INTERVAL_3MINUTE,
        '5m': Client.KLINE_INTERVAL_5MINUTE,
        '15m': Client.KLINE_INTERVAL_15MINUTE,
        '30m': Client.KLINE_INTERVAL_30MINUTE,
        '1h': Client.KLINE_INTERVAL_1HOUR,
        '2h': Client.KLINE_INTERVAL_2HOUR,
        '4h': Client.KLINE_INTERVAL_4HOUR,
        '6h': Client.KLINE_INTERVAL_6HOUR,
        '8h': Client.KLINE_INTERVAL_8HOUR,
        '12h': Client.KLINE_INTERVAL_12HOUR,
        '1d': Client.KLINE_INTERVAL_1DAY,
        '3d': Client.KLINE_INTERVAL_3DAY,
        '1w': Client.KLINE_INTERVAL_1WEEK,
        '1M': Client.KLINE_INTERVAL_1MONTH
    }
    
    # 訂單簿限制映射
    ORDERBOOK_LIMITS = {
        5: 2,
        10: 2,
        20: 2,
        50: 2,
        100: 5,
        500: 10,
        1000: 20
    }
    
    def __init__(self):
        """
        初始化 Binance API
        """
        try:
            # 加載配置
            self.config = load_config()
            
            # 檢查是否使用測試網
            self.testnet = self.config['control']['testnet']
            
            # 加載環境變量
            load_dotenv(dotenv_path='config/api_keys.env')
            
            # 獲取 API 密鑰
            if self.testnet:
                self.api_key = os.getenv('BINANCE_TESTNET_API_KEY')
                self.api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
            else:
                self.api_key = os.getenv('BINANCE_API_KEY')
                self.api_secret = os.getenv('BINANCE_API_SECRET')
                
            if not self.api_key or not self.api_secret:
                raise ValueError(f"請在 config/api_keys.env 文件中設置{'測試網' if self.testnet else '主網'} API 密鑰")
                
            # 初始化客戶端
            self.client = Client(self.api_key, self.api_secret)
            
            # 如果使用測試網，設置測試網 API 端點
            if self.testnet:
                self.client.API_URL = self.config['binance_api']['testnet_rest_api_url']
                
            # 初始化 WebSocket 相關變量
            self.ws = None
            self.ws_thread = None
            self.position_callback = None
            
            logger.info(f"已初始化 Binance API（{'測試網' if self.testnet else '主網'}）")
            
        except Exception as e:
            logger.error(f"初始化 Binance API 失敗: {str(e)}")
            raise
            
    def _generate_signature(self, params: Dict) -> str:
        """生成簽名"""
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
    def _authenticate_websocket(self) -> None:
        """認證 WebSocket 連接"""
        try:
            timestamp = int(time.time() * 1000)
            params = {
                'apiKey': self.api_key,
                'timestamp': timestamp
            }
            params['signature'] = self._generate_signature(params)
            
            auth_request = {
                'method': 'user.auth',
                'params': params,
                'id': str(uuid.uuid4())
            }
            
            self.ws.send(json.dumps(auth_request))
            response = json.loads(self.ws.recv())
            
            if response.get('result') is None:
                self.authenticated = True
                logger.info("WebSocket 認證成功")
            else:
                raise Exception(f"WebSocket 認證失敗: {response.get('error', {}).get('msg', '未知錯誤')}")
                
        except Exception as e:
            logger.error(f"WebSocket 認證失敗: {str(e)}")
            raise
            
    def _on_message(self, ws, message):
        """處理 WebSocket 消息"""
        try:
            data = json.loads(message)
            
            # 處理 ping 消息
            if 'ping' in data:
                pong = {'pong': data['ping']}
                ws.send(json.dumps(pong))
                return
                
            # 處理倉位更新
            if data.get('e') == 'ACCOUNT_UPDATE':
                position = data.get('a', {}).get('P', [{}])[0]
                if position:
                    position_info = PositionInfo(
                        status=PositionStatus.OPEN if float(position.get('pa', 0)) != 0 else PositionStatus.CLOSE,
                        symbol=position.get('s', ''),
                        leverage=int(position.get('l', 1)),
                        size=float(position.get('pa', 0)),
                        margin=float(position.get('m', 0)),
                        entry_price=float(position.get('ep', 0)),
                        stop_loss=float(position.get('sl', 0)) if position.get('sl') else None,
                        take_profit=float(position.get('tp', 0)) if position.get('tp') else None,
                        close_reason=self._get_close_reason(position),
                        close_price=float(position.get('cp', 0)) if position.get('cp') else None,
                        pnl_usdt=float(position.get('up', 0)),
                        pnl_percent=float(position.get('cr', 0))
                    )
                    
                    if self.position_callback:
                        self.position_callback(position_info)
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {str(e)}")
        except Exception as e:
            logger.error(f"處理 WebSocket 消息失敗: {str(e)}")
            
    def _on_error(self, ws, error):
        """處理 WebSocket 錯誤"""
        logger.error(f"WebSocket 錯誤: {str(error)}")
        # 嘗試重連
        self._reconnect()
        
    def _on_close(self, ws, close_status_code, close_msg):
        """處理 WebSocket 關閉"""
        logger.info(f"WebSocket 連接已關閉，狀態碼: {close_status_code}, 消息: {close_msg}")
        # 嘗試重連
        self._reconnect()
        
    def _on_open(self, ws):
        """處理 WebSocket 打開"""
        logger.info("WebSocket 連接已建立")
        # 認證 WebSocket 連接
        self._authenticate_websocket()
        
    def _reconnect(self):
        """重連 WebSocket"""
        try:
            if self.ws:
                logger.info("正在嘗試重新連接 WebSocket...")
                time.sleep(5)  # 等待 5 秒後重連
                self.ws.close()
                self.ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    ping_payload='{"method": "ping"}'
                )
        except Exception as e:
            logger.error(f"WebSocket 重連失敗: {str(e)}")
            
    def start_position_listener(self, callback: Callable[[PositionInfo], None]) -> None:
        """
        啟動倉位監聽器
        
        Args:
            callback: 回調函數，接收 PositionInfo 對象
        """
        try:
            # 如果已有連接，先關閉
            if self.ws:
                self.stop_position_listener()
                
            # 設置回調函數
            self.position_callback = callback
            
            # 構建 WebSocket URL
            ws_url = f"{self.config['binance_api']['webSocket_base_endpoint_for_testnet' if self.testnet else 'webSocket_base_endpoint']}/ws"
            logger.info(f"正在連接倉位監聽 WebSocket: {ws_url}")
            
            # 設置 WebSocket 參數
            websocket.enableTrace(True)
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            # 設置 WebSocket 選項
            websocket.setdefaulttimeout(30)  # 設置超時時間為 30 秒
            
            # 啟動 WebSocket 線程
            self.ws_thread = threading.Thread(target=self.ws.run_forever, kwargs={
                'ping_interval': 20,  # 每 20 秒發送一次 ping
                'ping_timeout': 10,   # ping 超時時間為 10 秒
                'ping_payload': '{"method": "ping"}',  # ping 消息格式
            })
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # 等待連接建立
            time.sleep(1)
            
            if not self.ws.sock or not self.ws.sock.connected:
                raise Exception("WebSocket 連接失敗")
                
            logger.info(f"已啟動倉位監聽器（{'測試網' if self.testnet else '主網'}）")
            
        except Exception as e:
            logger.error(f"啟動倉位監聽器失敗: {str(e)}")
            self.stop_position_listener()
            raise
            
    def stop_position_listener(self):
        """停止倉位監聽器"""
        try:
            if self.ws:
                self.ws.close()
                self.ws = None
            if self.ws_thread:
                self.ws_thread.join()
                self.ws_thread = None
            self.position_callback = None
            logger.info("倉位監聽器已停止")
        except Exception as e:
            logger.error(f"停止倉位監聽器失敗: {str(e)}")
            
    def _get_close_reason(self, position: Dict) -> CloseReason:
        """獲取平倉原因"""
        try:
            # 檢查是否為爆倉
            if position.get('lq', 0) > 0:
                return CloseReason.LIQUIDATION
                
            # 檢查是否為止損
            if position.get('sl', 0) > 0 and float(position['cp']) <= float(position['sl']):
                return CloseReason.STOP_LOSS
                
            # 檢查是否為止盈
            if position.get('tp', 0) > 0 and float(position['cp']) >= float(position['tp']):
                return CloseReason.TAKE_PROFIT
                
            # 檢查是否為移動止損
            if position.get('ts', 0) > 0:
                return CloseReason.TRAILING_STOP
                
            # 默認為手動平倉
            return CloseReason.MANUAL
            
        except Exception as e:
            logger.error(f"獲取平倉原因時發生錯誤: {str(e)}")
            return CloseReason.MANUAL
            
    def get_position_info(self, symbol: Optional[str] = None) -> Union[PositionInfo, List[PositionInfo]]:
        """
        獲取倉位信息
        
        Args:
            symbol: 交易對，如果為 None 則返回所有倉位
            
        Returns:
            Union[PositionInfo, List[PositionInfo]]: 倉位信息
        """
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            
            if symbol:
                position = positions[0]
                return PositionInfo(
                    status=PositionStatus.OPEN if float(position['positionAmt']) > 0 else PositionStatus.CLOSE,
                    symbol=position['symbol'],
                    leverage=int(position['leverage']),
                    size=float(position['positionAmt']),
                    margin=float(position['marginBalance']),
                    entry_price=float(position['entryPrice']),
                    stop_loss=float(position['sl']) if position['sl'] else None,
                    take_profit=float(position['tp']) if position['tp'] else None,
                    close_reason=None,
                    close_price=float(position['cp']) if float(position['positionAmt']) != 0 else None,
                    pnl_usdt=float(position['unRealizedProfit']) if float(position['positionAmt']) > 0 else None,
                    pnl_percent=float(position['cr']) if float(position['positionAmt']) > 0 else None
                )
            else:
                return [
                    PositionInfo(
                        status=PositionStatus.OPEN if float(p['positionAmt']) > 0 else PositionStatus.CLOSE,
                        symbol=p['symbol'],
                        leverage=int(p['leverage']),
                        size=float(p['positionAmt']),
                        margin=float(p['marginBalance']),
                        entry_price=float(p['entryPrice']),
                        stop_loss=float(p['sl']) if p['sl'] else None,
                        take_profit=float(p['tp']) if p['tp'] else None,
                        close_reason=None,
                        close_price=float(p['cp']) if float(p['positionAmt']) != 0 else None,
                        pnl_usdt=float(p['unRealizedProfit']) if float(p['positionAmt']) > 0 else None,
                        pnl_percent=float(p['cr']) if float(p['positionAmt']) > 0 else None
                    )
                    for p in positions
                ]
                
        except Exception as e:
            logger.error(f"獲取倉位信息失敗: {str(e)}")
            raise
            
    def get_account_info(self) -> AccountInfo:
        """
        獲取賬戶信息
        
        Returns:
            AccountInfo: 賬戶信息
        """
        try:
            account = self.client.futures_account()
            
            # 獲取所有倉位信息
            positions = self.get_position_info()
            
            return AccountInfo(
                total_wallet_balance=float(account['totalWalletBalance']),
                total_unrealized_profit=float(account['totalUnrealizedProfit']),
                total_margin_balance=float(account['totalMarginBalance']),
                available_balance=float(account['availableBalance']),
                max_withdraw_amount=float(account['maxWithdrawAmount']),
                assets=account['assets'],
                positions=positions,
                update_time=int(account['updateTime'])
            )
            
        except Exception as e:
            logger.error(f"獲取賬戶信息失敗: {str(e)}")
            raise

    def execute_order(self, symbol: str, side: OrderSide, quantity: float, price: float = None) -> Dict:
        """
        執行訂單
        :param symbol: 交易對
        :param side: 訂單方向
        :param quantity: 數量
        :param price: 價格（如果為 None，則為市價單）
        :return: 訂單信息
        """
        try:
            # 檢查訂單數量是否滿足最小名義價值要求
            current_price = float(self.client.get_symbol_price(symbol=symbol)['price'])
            notional_value = quantity * current_price
            
            if notional_value < 100:
                logging.error(f"訂單名義價值 ({notional_value} USDT) 小於最小要求 (100 USDT)")
                raise ValueError(f"訂單名義價值必須大於等於 100 USDT，當前: {notional_value:.2f} USDT")

            order_type = 'LIMIT' if price else 'MARKET'
            params = {
                'symbol': symbol,
                'side': side.value,
                'type': order_type,
                'quantity': quantity,
            }
            
            if price:
                params['price'] = price
                params['timeInForce'] = 'GTC'
            
            order = self.client.futures_create_order(**params)
            logging.info(f"訂單執行成功: {order}")
            return order
        except Exception as e:
            logging.error(f"執行訂單時發生錯誤: {str(e)}")
            raise
