from binance.um_futures import UMFutures
from binance.error import ClientError
import pandas as pd
from typing import Optional, Union, List, Callable, Dict, Tuple, Any
import logging
from datetime import datetime
import os
import yaml
import json
import time
from decimal import Decimal
from dotenv import load_dotenv
import threading
import websocket
import ssl

from .enums import OrderSide, PositionStatus, CloseReason, OrderType, OrderStatus, WorkingType, TimeInForce, PriceMatch, SelfTradePreventionMode, PositionSide
from .data_models import PositionInfo, AccountInfo, Order, OrderResult
from .converter import BinanceConverter
from utils.config import check_config_parameters

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceAPI:
    """Binance API 封裝類"""
    
    def __init__(self):
        """
        初始化 Binance API
        """
        try:
            # 使用 check_config_parameters 獲取配置參數
            config_params = check_config_parameters([
                'testnet',
                'base_endpoint',
                'testnet_rest_api_url',
                'webSocket_base_endpoint',
                'webSocket_base_endpoint_for_testnet',
                'recv_window',
                'BINANCE_API_KEY',
                'BINANCE_API_SECRET',
                'BINANCE_TESTNET_API_KEY',
                'BINANCE_TESTNET_API_SECRET',
                'ping_interval',
                'pong_timeout',
                'reconnect_attempts',
                'symbol_list',
                'leverage'
            ])
            
            # 檢查是否有未設定的參數
            missing_params = [param for param, value in config_params.items() if value is None]
            if missing_params:
                raise ValueError(f"以下參數未設定: {', '.join(missing_params)}")
            
            # 根據 testnet 設定選擇 API 金鑰和端點
            self.api_key = config_params['BINANCE_TESTNET_API_KEY'] if config_params['testnet'] else config_params['BINANCE_API_KEY']
            self.api_secret = config_params['BINANCE_TESTNET_API_SECRET'] if config_params['testnet'] else config_params['BINANCE_API_SECRET']
            self.ws_base_url = config_params['webSocket_base_endpoint_for_testnet'] if config_params['testnet'] else config_params['webSocket_base_endpoint']
            
            # 設置 WebSocket 配置
            self.websocket_ping_interval = config_params['ping_interval']
            self.websocket_ping_timeout = config_params['pong_timeout']
            self.websocket_reconnect_attempts = config_params['reconnect_attempts']
            
            # 設置交易參數
            self.symbol_list = config_params['symbol_list']
            self.leverage = config_params['leverage']

            # 初始化 REST API 客戶端
            base_url = config_params['testnet_rest_api_url'] if config_params['testnet'] else config_params['base_endpoint']
            self.client = UMFutures(
                key=self.api_key,
                secret=self.api_secret,
                base_url=base_url
            )
            self.client.timeout = config_params['recv_window']
            
            # 初始化 WebSocket 相關屬性
            self.order_callback = None
            self._keepalive_running = False
            self._keepalive_thread = None
            self.ws_client = None
            self.listen_key = None
            self._reconnecting = False
            self._listen_key_attempts = 0
            self._reconnect_attempts = 0
            
            # 啟用 WebSocket 調試日誌
            websocket.enableTrace(True)
            websocket_logger = logging.getLogger('websocket')
            websocket_logger.setLevel(logging.DEBUG)
            
            logger.info(f"已初始化 Binance API（{'測試網' if config_params['testnet'] else '主網'}）")
            logger.info(f"WebSocket 基礎 URL: {self.ws_base_url}")
            logger.info(f"WebSocket 配置: ping_interval={self.websocket_ping_interval}, ping_timeout={self.websocket_ping_timeout}")
            logger.info(f"交易對列表: {self.symbol_list}")
            
        except Exception as e:
            logger.error(f"初始化 Binance API 失敗: {str(e)}")
            raise
            
    def _get_listen_key(self) -> str:
        """獲取 listenKey"""
        try:
            response = self.client.new_listen_key()
            if isinstance(response, dict) and 'listenKey' in response:
                return response['listenKey']
            return response
        except Exception as e:
            logger.error(f"獲取 listenKey 失敗: {str(e)}")
            raise

    def _extend_listen_key(self) -> None:
        """延長 listenKey 的有效期"""
        try:
            if not self.listen_key:
                logger.warning("沒有有效的 listenKey 可以延長")
                return
                
            self.client.renew_listen_key(listenKey=self.listen_key)
            logger.info("已延長 listenKey 的有效期")
        except Exception as e:
            logger.error(f"延長 listenKey 有效期失敗: {str(e)}")
            # 如果延長失敗，嘗試重新獲取
            try:
                self.listen_key = self._get_listen_key()
                logger.info("已重新獲取 listenKey")
            except Exception as e2:
                logger.error(f"重新獲取 listenKey 失敗: {str(e2)}")
                raise

    def _start_listen_key_keepalive(self) -> None:
        """啟動定期更新 listenKey 的後台任務"""
        def keepalive():
            while self._keepalive_running:
                try:
                    self._extend_listen_key()
                    time.sleep(30 * 60)  # 每30分鐘更新一次
                except Exception as e:
                    logger.error(f"更新 listenKey 失敗: {str(e)}")
                    time.sleep(60)  # 失敗後等待1分鐘再重試

        self._keepalive_running = True
        self._keepalive_thread = threading.Thread(target=keepalive, daemon=True)
        self._keepalive_thread.start()
        logger.info("已啟動 listenKey 保活任務")

    def start_position_listener(self, order_callback: Callable[[Order], None]) -> None:
        """啟動倉位監聽器"""
        try:
            # 檢查 WebSocket 客戶端狀態
            if self.ws_client and self.ws_client.sock and self.ws_client.sock.connected:
                logger.warning("WebSocket 已經在運行中")
                return
                
            # 檢查回調函數
            if not callable(order_callback):
                raise ValueError("回調函數必須是可調用的")
                
            self.order_callback = order_callback
            
            # 先獲取 listenKey
            try:
                self.listen_key = self._get_listen_key()
                if not self.listen_key:
                    raise ValueError("獲取 listenKey 失敗")
                logger.info(f"成功獲取 listenKey: {self.listen_key}")
            except Exception as e:
                logger.error(f"獲取 listenKey 失敗: {str(e)}")
                raise
            
            # 啟動 listenKey 保活任務
            self._start_listen_key_keepalive()
            
            def on_message(ws, message):
                try:
                    msg = json.loads(message)
                    self._handle_user_message(msg)
                except json.JSONDecodeError as e:
                    logger.error(f"解析 WebSocket 消息失敗: {str(e)}")
                except Exception as e:
                    logger.error(f"處理 WebSocket 消息時發生錯誤: {str(e)}")
            
            def on_error(ws, error):
                logger.error(f"WebSocket 錯誤: {str(error)}")
            
            def on_close(ws, close_status_code, close_msg):
                logger.warning(f"WebSocket 連接關閉: {close_status_code} - {close_msg}")
                if self._reconnecting:
                    logger.warning("已經在重連過程中，忽略新的重連請求")
                    return
                # 在新線程中執行重連
                reconnect_thread = threading.Thread(target=self._reconnect_websocket, daemon=True)
                reconnect_thread.start()
            
            def on_open(ws):
                logger.info("WebSocket 連接已建立")
            
            # 構建 WebSocket URL，確保以 wss:// 開頭且不以 /ws 結尾
            ws_url = self.ws_base_url.rstrip('/ws')
            if not ws_url.startswith('wss://'):
                ws_url = 'wss://' + ws_url.lstrip('ws://')
            ws_url = f"{ws_url}/ws/{self.listen_key}"
            
            logger.info(f"正在連接到 WebSocket: {ws_url}")
            
            # 創建 WebSocket 客戶端
            self.ws_client = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            # 設置 WebSocket 配置
            websocket.setdefaulttimeout(self.websocket_ping_timeout)
            
            # 在單獨的線程中運行 WebSocket 客戶端
            self.ws_thread = threading.Thread(
                target=self.ws_client.run_forever,
                kwargs={
                    'ping_interval': self.websocket_ping_interval,
                    'ping_timeout': self.websocket_ping_timeout,
                    'sslopt': {'cert_reqs': ssl.CERT_NONE}
                },
                daemon=True
            )
            self.ws_thread.start()
            
            # 等待連接建立
            for _ in range(5):  # 最多等待 5 秒
                if self.ws_client.sock and self.ws_client.sock.connected:
                    logger.info("持倉監聽器啟動成功")
                    return
                time.sleep(1)
            
            raise ConnectionError("WebSocket 連接建立超時")
            
        except Exception as e:
            logger.error(f"啟動持倉監聽器失敗: {str(e)}")
            self.stop_position_listener()
            raise

    def _reconnect_listen_key(self) -> bool:
        """重新獲取 listenKey
        
        Returns:
            bool: 是否成功獲取 listenKey
        """
        try:
            if not hasattr(self, '_listen_key_attempts'):
                self._listen_key_attempts = 0
            
            self._listen_key_attempts += 1
            logger.warning(f"嘗試重新獲取 ListenKey (第 {self._listen_key_attempts} 次)")
            
            # 等待一段時間再重試
            wait_time = 2 ** self._listen_key_attempts  # 指數退避
            logger.info(f"等待 {wait_time} 秒後重試...")
            time.sleep(wait_time)
            
            # 嘗試獲取新的 listenKey
            try:
                self.listen_key = self._get_listen_key()
                if self.listen_key:
                    logger.info(f"成功獲取新的 ListenKey: {self.listen_key}")
                    self._listen_key_attempts = 0  # 重置重試計數器
                    return True
            except Exception as e:
                logger.error(f"獲取 ListenKey 失敗: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"重新獲取 ListenKey 過程中發生錯誤: {str(e)}")
            return False

    def _reconnect_websocket(self):
        """重新連接 WebSocket"""
        try:
            self._reconnecting = True
            
            if self._reconnect_attempts >= self.websocket_reconnect_attempts:
                logger.error("WebSocket 重連次數已達上限，請檢查網絡連接或重啟程序")
                return
                
            self._reconnect_attempts += 1
            logger.warning(f"嘗試重新連接 WebSocket (第 {self._reconnect_attempts} 次)")
            
            # 保存當前的回調函數
            current_callbacks = {
                'on_message': self.ws_client.on_message if self.ws_client else None,
                'on_error': self.ws_client.on_error if self.ws_client else None,
                'on_close': self.ws_client.on_close if self.ws_client else None,
                'on_open': self.ws_client.on_open if self.ws_client else None
            }
            
            # 關閉現有連接
            if self.ws_client:
                try:
                    self.ws_client.close()
                except:
                    pass
            
            # 等待一段時間再重連
            wait_time = 2 ** self._reconnect_attempts  # 指數退避
            logger.info(f"等待 {wait_time} 秒後重試...")
            time.sleep(wait_time)
            
            # 獲取新的 listenKey
            while not self._reconnect_listen_key():
                logger.error("重連：無法獲取 ListenKey，將繼續重試")
                if self._listen_key_attempts >= self.websocket_reconnect_attempts:
                    logger.error("ListenKey 重試次數已達上限，請檢查網絡連接或重啟程序")
                    return
            
            # 構建新的 WebSocket URL
            ws_url = self.ws_base_url.rstrip('/ws')
            if not ws_url.startswith('wss://'):
                ws_url = 'wss://' + ws_url.lstrip('ws://')
            ws_url = f"{ws_url}/ws/{self.listen_key}"
            
            logger.info(f"重連：正在連接到 WebSocket: {ws_url}")
            
            # 重新創建 WebSocket 客戶端
            self.ws_client = websocket.WebSocketApp(
                ws_url,
                on_message=current_callbacks['on_message'],
                on_error=current_callbacks['on_error'],
                on_close=current_callbacks['on_close'],
                on_open=current_callbacks['on_open']
            )
            
            # 在新線程中運行
            self.ws_thread = threading.Thread(
                target=self.ws_client.run_forever,
                kwargs={
                    'ping_interval': self.websocket_ping_interval,
                    'ping_timeout': self.websocket_ping_timeout,
                    'sslopt': {'cert_reqs': ssl.CERT_NONE}
                },
                daemon=True
            )
            self.ws_thread.start()
            
            # 等待連接建立
            for _ in range(5):  # 最多等待 5 秒
                if self.ws_client.sock and self.ws_client.sock.connected:
                    logger.info("重連：WebSocket 連接成功")
                    self._reconnect_attempts = 0  # 重置重連計數器
                    self._reconnecting = False # 重置重連狀態
                    return
                time.sleep(1)

            self._reconnecting = False
            
            logger.error("重連：無法連接 WebSocket，將繼續重試")
            
        except Exception as e:
            logger.error(f"重連：WebSocket 重連過程中發生錯誤: {str(e)}")

    def _handle_user_message(self, msg: Dict):
        """處理用戶數據流消息"""
        try:
            # 確保 msg 是字典類型
            if not isinstance(msg, dict):
                logger.error(f"收到非字典類型的消息: {msg}")
                return
                
            event_type = msg.get('e')
            
            if event_type == 'ACCOUNT_UPDATE':
                # 處理帳戶更新事件
                positions = msg.get('a', {}).get('P', [])
                for position in positions:
                    if position and isinstance(position, dict):
                        logger.info(f"倉位更新: {position}")
                        # 這裡可以添加倉位更新的處理邏輯

            elif event_type == 'ORDER_TRADE_UPDATE':
                # 處理訂單交易更新事件
                order = msg.get('o', {})
                if order and isinstance(order, dict):
                    try:
                        # 使用 BinanceConverter 轉換訂單數據
                        order_info = BinanceConverter.to_order({
                            'e': 'ORDER_TRADE_UPDATE',
                            'T': msg.get('T', time.time()), 
                            'o': order
                        })

                        # 調用回調函數
                        if self.order_callback:
                            self.order_callback(order_info)
                        logger.info(f"訂單更新: {order_info}")

                    except Exception as e:
                        logger.error(f"轉換訂單數據失敗: {str(e)}")
                    
            elif event_type == 'TRADE_LITE':
                # 處理簡化交易事件
                trade = msg.get('o', {})
                if trade and isinstance(trade, dict):
                    logger.info(f"簡化交易更新: {trade}")
                    # 這裡可以添加交易更新的處理邏輯
                    
            elif event_type == 'MARGIN_CALL':
                # 處理保證金通知事件
                positions = msg.get('p', [])
                for position in positions:
                    if position and isinstance(position, dict):
                        logger.warning(f"保證金通知: {position}")
                        # 這裡可以添加保證金通知的處理邏輯
                    
            elif event_type == 'ACCOUNT_CONFIG_UPDATE':
                # 處理帳戶配置更新事件
                config = msg.get('ac', {})
                if config and isinstance(config, dict):
                    logger.info(f"帳戶配置更新: {config}")
                    # 這裡可以添加帳戶配置更新的處理邏輯
                    
            else:
                logger.warning(f"未知的事件類型: {event_type}")
                
        except Exception as e:
            logger.error(f"處理用戶消息失敗: {str(e)}")
            raise
            
    def stop_position_listener(self) -> None:
        """停止倉位監聽器"""
        try:
            # 停止 listenKey 保活任務
            self._keepalive_running = False
            if self._keepalive_thread:
                self._keepalive_thread.join(timeout=5)
            
            # 停止 WebSocket 連接
            if self.ws_client:
                self.ws_client.close()
                self.ws_client = None
            
            # 清除回調函數和 listenKey
            self.order_callback = None
            self.listen_key = None
            
            logger.info("倉位監聽器已停止")
            
        except Exception as e:
            logger.error(f"停止倉位監聽器失敗: {str(e)}")
            raise
            
    def get_position_risk(self, symbol: Optional[str] = None) -> Union[PositionInfo, List[PositionInfo]]:
        """
        獲取倉位風險信息
        
        Args:
            symbol: 交易對，如果為 None 則獲取 symbol_list 中的所有倉位
            
        Returns:
            PositionInfo 對象或 PositionInfo 列表，如果沒有持倉則返回 None
        """
        try:
            # 獲取倉位風險信息
            if symbol:
                # 檢查交易對是否在 symbol_list 中
                if symbol not in self.symbol_list:
                    raise ValueError(f"交易對 {symbol} 不在配置的 symbol_list 中")
                    
                response = self.client.get_position_risk(symbol=symbol)
                
                if not response:
                    logger.info(f"沒有找到 {symbol} 的持倉信息")
                    return None
                    
                position = response[0]
                
                # 如果倉位數量為 0，返回 None
                if Decimal(position['positionAmt']) == 0:
                    logger.info(f"{symbol} 沒有持倉")
                    return None
                    
                return BinanceConverter.to_position(position)
            else:
                # 獲取 symbol_list 中的所有倉位
                positions = []
                for symbol in self.symbol_list:
                    try:
                        response = self.client.get_position_risk(symbol=symbol)
                        
                        if response and Decimal(response[0]['positionAmt']) != 0:  # 只返回有倉位的
                            position = response[0]
                            positions.append(BinanceConverter.to_position(position))
                    except Exception as e:
                        logger.error(f"獲取 {symbol} 倉位風險信息失敗: {str(e)}")
                        continue
                return positions if positions else None
                
        except Exception as e:
            logger.error(f"獲取倉位風險信息失敗: {str(e)}")
            raise
            
    def get_account_info(self) -> AccountInfo:
        """獲取帳戶信息
        
        Returns:
            AccountInfo: 帳戶信息對象
        """
        try:
            # 獲取帳戶信息
            account_data = self.client.account()
            
            # 使用轉換器轉換數據
            return BinanceConverter.to_account_info(account_data)
            
        except Exception as e:
            logger.error(f"獲取帳戶信息失敗: {str(e)}")
            raise
            
    def get_exchange_info(self) -> Dict:
        """
        獲取交易所信息
        
        Returns:
            Dict: 交易所信息
        """
        try:
            return self.client.exchange_info()
        except Exception as e:
            logger.error(f"獲取交易所信息失敗: {str(e)}")
            raise
            
    def get_symbol_info(self, symbol: str) -> Dict:
        """獲取交易對信息"""
        try:
            exchange_info = self.client.exchange_info()
            symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
            if not symbol_info:
                raise ValueError(f"找不到交易對 {symbol} 的信息")
            return symbol_info
        except Exception as e:
            logger.error(f"獲取交易對信息失敗: {str(e)}")
            raise
            
    def get_current_price(self, symbol: str) -> Decimal:
        """獲取當前價格"""
        try:
            ticker = self.client.ticker_price(symbol=symbol)
            return Decimal(ticker['price'])
        except Exception as e:
            logger.error(f"獲取當前價格失敗: {str(e)}")
            raise
            
    def get_symbol_filters(self, symbol: str) -> Dict[str, Dict]:
        """獲取交易對的過濾器信息"""
        try:
            symbol_info = self.get_symbol_info(symbol)
            filters = symbol_info.get('filters', [])
            return {f['filterType']: f for f in filters}
        except Exception as e:
            logger.error(f"獲取交易對過濾器失敗: {str(e)}")
            raise
            
    def get_min_notional(self, symbol: str) -> Decimal:
        """獲取交易對的最小名義價值要求"""
        try:
            filters = self.get_symbol_filters(symbol)
            min_notional_filter = filters.get('MIN_NOTIONAL')
            if not min_notional_filter:
                raise ValueError(f"找不到交易對 {symbol} 的最小名義價值要求")
            return Decimal(min_notional_filter['notional'])
        except Exception as e:
            logger.error(f"獲取最小名義價值要求失敗: {str(e)}")
            raise
            
    def get_lot_size_info(self, symbol: str) -> Dict[str, Decimal]:
        """獲取交易對的數量限制信息"""
        try:
            filters = self.get_symbol_filters(symbol)
            lot_size_filter = filters.get('LOT_SIZE')
            if not lot_size_filter:
                raise ValueError(f"找不到交易對 {symbol} 的數量限制")
            return {
                'min_qty': Decimal(lot_size_filter['minQty']),
                'max_qty': Decimal(lot_size_filter['maxQty']),
                'step_size': Decimal(lot_size_filter['stepSize'])
            }
        except Exception as e:
            logger.error(f"獲取數量限制信息失敗: {str(e)}")
            raise
            
    def get_price_filter_info(self, symbol: str) -> Dict[str, Decimal]:
        """獲取交易對的價格限制信息"""
        try:
            filters = self.get_symbol_filters(symbol)
            price_filter = filters.get('PRICE_FILTER')
            if not price_filter:
                raise ValueError(f"找不到交易對 {symbol} 的價格限制")
            return {
                'min_price': Decimal(price_filter['minPrice']),
                'max_price': Decimal(price_filter['maxPrice']),
                'tick_size': Decimal(price_filter['tickSize'])
            }
        except Exception as e:
            logger.error(f"獲取價格限制信息失敗: {str(e)}")
            raise
            
    def get_server_time(self) -> int:
        """
        獲取服務器時間
        
        Returns:
            int: 服務器時間（毫秒）
        """
        try:
            return self.client.time()['serverTime']
        except Exception as e:
            logger.error(f"獲取服務器時間失敗: {str(e)}")
            raise
            
    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> List[Dict]:
        """
        獲取K線數據
        
        Args:
            symbol: 交易對
            interval: K線間隔
            limit: 獲取數量
            
        Returns:
            List[Dict]: K線數據
        """
        try:
            return self.client.klines(symbol=symbol, interval=interval, limit=limit)
        except Exception as e:
            logger.error(f"獲取K線數據失敗: {str(e)}")
            raise
            
    def get_ticker_price(self, symbol: str) -> Dict:
        """
        獲取最新價格
        
        Args:
            symbol: 交易對
            
        Returns:
            Dict: 價格信息
        """
        try:
            return self.client.ticker_price(symbol=symbol)
        except Exception as e:
            logger.error(f"獲取最新價格失敗: {str(e)}")
            raise
            
    def get_order_book(self, symbol: str, limit: int = 100) -> Dict:
        """
        獲取訂單簿
        
        Args:
            symbol: 交易對
            limit: 返回的深度
            
        Returns:
            Dict: 訂單簿數據
        """
        try:
            return self.client.depth(symbol=symbol, limit=limit)
        except Exception as e:
            logger.error(f"獲取訂單簿失敗: {str(e)}")
            raise
            
    def get_recent_trades(self, symbol: str, limit: int = 500) -> List[Dict]:
        """
        獲取最近成交
        
        Args:
            symbol: 交易對
            limit: 返回的成交數量
            
        Returns:
            List[Dict]: 成交數據列表
        """
        try:
            return self.client.trades(symbol=symbol, limit=limit)
        except Exception as e:
            logger.error(f"獲取最近成交失敗: {str(e)}")
            raise
            
    def get_trades(self, symbol: str, limit: int = 500) -> List[Dict]:
        """
        獲取最近的成交記錄
        
        Args:
            symbol: 交易對
            limit: 返回的成交記錄數量，最大 1000
            
        Returns:
            List[Dict]: 成交記錄列表，每個記錄包含以下字段：
                - id: 成交ID
                - price: 成交價格
                - qty: 成交數量
                - quote_qty: 成交金額
                - time: 成交時間
                - is_buyer_maker: 是否為買方做市商
                - is_best_match: 是否為最佳匹配
        """
        try:
            trades = self.client.trades(symbol=symbol, limit=limit)
            return trades
        except Exception as e:
            logger.error(f"獲取成交記錄失敗: {str(e)}")
            raise
            
    def change_leverage(self, symbol: str, leverage: int) -> Dict:
        """
        修改交易對的槓桿倍數
        
        Args:
            symbol: 交易對
            leverage: 槓桿倍數
            
        Returns:
            Dict: API 響應結果
            
        Raises:
            Exception: 當 API 調用失敗時
        """
        try:
            response = self.client.change_leverage(
                symbol=symbol,
                leverage=leverage
            )
            logger.info(f"修改槓桿倍數成功: {symbol} {leverage}x")
            return response
        except Exception as e:
            logger.error(f"修改槓桿倍數失敗: {str(e)}")
            raise

    def get_all_orders(self, symbol: Optional[str] = None, limit: int = 500) -> List[Order]:
        """查詢所有訂單（只返回未完全成交的訂單）
        
        Args:
            symbol: 交易對，如果為 None 則查詢 symbol_list 中的所有交易對
            limit: 返回的訂單數量限制
            
        Returns:
            List[Order]: 訂單列表
        """
        try:
            if symbol:
                # 檢查交易對是否在 symbol_list 中
                if symbol not in self.symbol_list:
                    raise ValueError(f"交易對 {symbol} 不在配置的 symbol_list 中")
                    
                # 查詢指定交易對的訂單
                orders = self.client.get_orders(symbol=symbol, limit=limit)
                # 只返回未完全成交的訂單
                return [BinanceConverter.to_order(order) for order in orders 
                       if order['status'] in ['NEW', 'PARTIALLY_FILLED']]
            else:
                # 查詢 symbol_list 中的所有交易對的訂單
                all_orders = []
                for symbol in self.symbol_list:
                    try:
                        orders = self.client.get_orders(symbol=symbol, limit=limit)
                        # 只返回未完全成交的訂單
                        unfilled_orders = [BinanceConverter.to_order(order) for order in orders 
                                         if order['status'] in ['NEW', 'PARTIALLY_FILLED']]
                        all_orders.extend(unfilled_orders)
                    except Exception as e:
                        logger.error(f"查詢 {symbol} 訂單失敗: {str(e)}")
                        continue
                return all_orders
        except Exception as e:
            logger.error(f"查詢訂單失敗: {str(e)}")
            raise

    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                    client_order_id: Optional[str] = None) -> Order:
        """取消訂單
        
        Args:
            symbol: 交易對
            order_id: 訂單ID
            client_order_id: 客戶訂單ID
            
        Returns:
            Order: 被取消的訂單
        """
        try:
            params = {'symbol': symbol}
            if order_id:
                params['orderId'] = order_id
            if client_order_id:
                params['origClientOrderId'] = client_order_id
                
            response = self.client.cancel_order(**params)
            logger.info(f"取消訂單成功: {response}")
            
            # 使用 BinanceConverter 轉換訂單結果
            return BinanceConverter.to_order(response)
            
        except Exception as e:
            logger.error(f"取消訂單失敗: {str(e)}")
            raise

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """取消所有訂單"""
        try:
            if symbol:
                if symbol not in self.symbol_list:
                    raise ValueError(f"交易對 {symbol} 不在配置的 symbol_list 中")
                    
                # 先獲取當前未完成的訂單
                open_orders = self.client.get_orders(symbol=symbol, limit=100)
                orders_to_cancel = [order for order in open_orders 
                                  if order['status'] in ['NEW', 'PARTIALLY_FILLED']]
                
                if not orders_to_cancel:
                    logger.info(f"沒有找到 {symbol} 的未完成訂單")
                    return []
                    
                # 執行取消操作
                response = self.client.cancel_open_orders(symbol=symbol)
                logger.info(f"取消訂單響應: {response}")
                
                if not response or response.get('code') != 200:
                    logger.warning(f"取消 {symbol} 訂單失敗: {response}")
                    return []
                    
                # 返回被取消的訂單信息
                return [BinanceConverter.to_order(order) for order in orders_to_cancel]
            else:
                # 取消所有交易對的訂單
                cancelled_orders = []
                for symbol in self.symbol_list:
                    try:
                        # 先獲取當前未完成的訂單
                        open_orders = self.client.get_orders(symbol=symbol, limit=100)
                        orders_to_cancel = [order for order in open_orders 
                                          if order['status'] in ['NEW', 'PARTIALLY_FILLED']]
                        
                        if not orders_to_cancel:
                            continue
                            
                        # 執行取消操作
                        response = self.client.cancel_open_orders(symbol=symbol)
                        logger.info(f"取消 {symbol} 訂單響應: {response}")
                        
                        if response and response.get('code') == 200:
                            # 返回被取消的訂單信息
                            cancelled_orders.extend([BinanceConverter.to_order(order) 
                                                  for order in orders_to_cancel])
                    except Exception as e:
                        logger.error(f"取消 {symbol} 所有訂單失敗: {str(e)}")
                        continue
                return cancelled_orders
        except Exception as e:
            logger.error(f"取消所有訂單失敗: {str(e)}")
            raise

    def get_order_status(self, symbol: str, order_id: Optional[int] = None, client_order_id: Optional[str] = None) -> OrderResult:
        """
        查詢訂單信息
        
        Args:
            symbol: 交易對
            order_id: 訂單ID
            client_order_id: 客戶訂單ID
            
        Returns:
            OrderResult: 訂單結果對象
        """
        try:
            params = {'symbol': symbol}
            if order_id:
                params['orderId'] = order_id
            if client_order_id:
                params['origClientOrderId'] = client_order_id
                
            response = self.client.query_order(**params)
            logger.info(f"查詢訂單成功: {response}")
            
            # 使用 BinanceConverter 轉換訂單結果
            return BinanceConverter.to_order_result(response)
            
        except Exception as e:
            logger.error(f"查詢訂單失敗: {str(e)}")
            raise

    def new_order(self, **params) -> OrderResult:
        """下單
        
        Args:
            symbol: 交易對
            side: 買賣方向
            type: 訂單類型
            quantity: 數量
            price: 價格
            stopPrice: 止損價格
            timeInForce: 訂單有效期
            reduceOnly: 是否只減倉
            closePosition: 是否平倉
            workingType: 價格類型
            priceProtect: 是否開啟價格保護
            newClientOrderId: 客戶訂單ID
            activationPrice: 移動止損激活價格
            callbackRate: 移動止損回調率
            
        Returns:
            OrderResult: 訂單結果
        """
        try:
            # 檢查必要參數
            required_params = ['symbol', 'side', 'type']
            for param in required_params:
                if param not in params:
                    raise ValueError(f"缺少必要參數: {param}")
            
            # 根據訂單類型檢查其他必要參數
            order_type = params['type']
            
            # 檢查 reduce_only 和 close_position
            if 'reduceOnly' in params and 'closePosition' in params:
                raise ValueError("不能同時設置 reduceOnly 和 closePosition")
            
            # 檢查數量相關參數
            if 'closePosition' not in params and 'reduceOnly' not in params and 'quantity' not in params:
                raise ValueError("必須指定數量或設置 closePosition 或 reduceOnly")
            
            # 限價單、止損限價單、止盈限價單需要價格
            if order_type in [OrderType.LIMIT, OrderType.STOP, OrderType.TAKE_PROFIT]:
                if 'price' not in params:
                    raise ValueError(f"{order_type} 訂單必須指定價格")
                if not params['price'] or float(params['price']) <= 0:
                    raise ValueError(f"{order_type} 訂單價格必須大於0")
            
            # 止損單、止損市價單、止盈單、止盈市價單需要止損價格
            if order_type in [OrderType.STOP, OrderType.STOP_MARKET, OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET]:
                if 'stopPrice' not in params:
                    raise ValueError(f"{order_type} 訂單必須指定止損價格")
                if not params['stopPrice'] or float(params['stopPrice']) <= 0:
                    raise ValueError(f"{order_type} 訂單止損價格必須大於0")
            
            # 移動止損市價單需要激活價格和回調率
            if order_type == OrderType.TRAILING_STOP_MARKET:
                if 'activationPrice' not in params:
                    raise ValueError("移動止損訂單必須指定激活價格")
                if not params['activationPrice'] or float(params['activationPrice']) <= 0:
                    raise ValueError("移動止損訂單激活價格必須大於0")
                if 'callbackRate' not in params:
                    raise ValueError("移動止損訂單必須指定回調率")
                if not params['callbackRate'] or float(params['callbackRate']) <= 0:
                    raise ValueError("移動止損訂單回調率必須大於0")
            
            # 檢查 timeInForce
            if order_type in [OrderType.LIMIT, OrderType.STOP, OrderType.TAKE_PROFIT]:
                if 'timeInForce' not in params:
                    raise ValueError(f"{order_type} 訂單必須指定訂單有效期")
            
            # 檢查 workingType
            if order_type in [OrderType.STOP, OrderType.STOP_MARKET, OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET, OrderType.TRAILING_STOP_MARKET]:
                if 'workingType' not in params:
                    raise ValueError(f"{order_type} 訂單必須指定價格類型")
            
            # 下單
            response = self.client.new_order(**params)
            
            # 使用 BinanceConverter 轉換訂單結果
            return BinanceConverter.to_order_result(response)
            
        except Exception as e:
            logger.error(f"下單失敗: {str(e)}")
            raise
        
    def close(self):
        """關閉 API 連接"""
        try:
            if self.ws_client:
                self.ws_client.close()
                self.ws_client = None
                logger.info("WebSocket 連接已關閉")
            
            if self.listen_key:
                try:
                    self.client.close_listen_key(listenKey=self.listen_key)
                    logger.info("ListenKey 已關閉")
                except Exception as e:
                    logger.warning(f"關閉 ListenKey 失敗: {str(e)}")
            
            self.listen_key = None
            
            if self._keepalive_thread:
                self._keepalive_thread.join(timeout=5)
                self._keepalive_thread = None
                logger.info("ListenKey 保活任務已停止")
        except Exception as e:
            logger.error(f"關閉 API 連接時發生錯誤: {str(e)}")
            raise
