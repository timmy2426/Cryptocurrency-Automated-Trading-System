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
from core import check_config_parameters

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
                'symbol_list'
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
            
            # 設置交易對列表
            self.symbol_list = config_params['symbol_list']
            
            # 初始化 REST API 客戶端
            base_url = config_params['testnet_rest_api_url'] if config_params['testnet'] else config_params['base_endpoint']
            self.client = UMFutures(
                key=self.api_key,
                secret=self.api_secret,
                base_url=base_url
            )
            self.client.timeout = config_params['recv_window']
            
            # 初始化 WebSocket 相關屬性
            self.position_callback = None
            self._keepalive_running = False
            self._keepalive_thread = None
            self.ws_client = None
            self.listen_key = None
            self._reconnect_attempts = 0
            
            # 啟用 WebSocket 調試日誌
            websocket.enableTrace(True)
            
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

    def start_position_listener(self, callback: Callable[[PositionInfo], None]) -> None:
        """啟動倉位監聽器"""
        try:
            # 檢查 WebSocket 客戶端狀態
            if self.ws_client and self.ws_client.sock and self.ws_client.sock.connected:
                logger.warning("WebSocket 已經在運行中")
                return
                
            # 檢查回調函數
            if not callable(callback):
                raise ValueError("回調函數必須是可調用的")
                
            self.position_callback = callback
            
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
                time.sleep(1)
                self._reconnect_websocket()
            
            def on_close(ws, close_status_code, close_msg):
                logger.warning(f"WebSocket 連接關閉: {close_status_code} - {close_msg}")
                time.sleep(1)
                self._reconnect_websocket()
            
            def on_open(ws):
                logger.info("WebSocket 連接已建立")
                self._reconnect_attempts = 0
            
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

    def _reconnect_websocket(self):
        """重新連接 WebSocket"""
        try:
            if not hasattr(self, '_reconnect_attempts'):
                self._reconnect_attempts = 0
                
            if self._reconnect_attempts >= self.websocket_reconnect_attempts:
                logger.error("WebSocket 重連次數已達上限，請檢查網絡連接或重啟程序")
                self._reconnect_attempts = 0
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
            time.sleep(2 ** self._reconnect_attempts)  # 指數退避
                
            # 獲取新的 listenKey
            try:
                self.listen_key = self._get_listen_key()
                if not self.listen_key:
                    raise ValueError("獲取 listenKey 失敗")
                logger.info(f"重連：成功獲取新的 listenKey: {self.listen_key}")
            except Exception as e:
                logger.error(f"重連：獲取 listenKey 失敗: {str(e)}")
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
                    return
                time.sleep(1)
            
            logger.error("重連：WebSocket 連接建立超時")
            
        except Exception as e:
            logger.error(f"重連：WebSocket 重連過程中發生錯誤: {str(e)}")
            # 不在這裡拋出異常，讓重連機制繼續工作

    def _handle_user_message(self, msg: Dict):
        """處理用戶數據流消息"""
        try:
            event_type = msg.get('e')
            
            if event_type == 'ACCOUNT_UPDATE':
                # 處理帳戶更新事件
                positions = msg.get('a', {}).get('P', [])
                for position in positions:
                    if position:
                        position_info = PositionInfo(
                            symbol=position.get('s', ''),
                            position_amt=Decimal(str(position.get('pa', 0))),
                            entry_price=Decimal(str(position.get('ep', 0))),
                            mark_price=Decimal(str(position.get('mp', 0))),
                            un_realized_profit=Decimal(str(position.get('up', 0))),
                            liquidation_price=Decimal(str(position.get('lp', 0))),
                            leverage=int(position.get('l', 1)),
                            max_notional_value=Decimal(str(position.get('mnv', 0))),
                            margin_type=position.get('mt', 'isolated'),
                            isolated_margin=Decimal(str(position.get('im', 0))),
                            is_auto_add_margin=position.get('iam', False),
                            status=PositionStatus.OPEN if float(position.get('pa', 0)) != 0 else PositionStatus.CLOSED,
                            stop_loss=float(position.get('sl', 0)) if position.get('sl') else None,
                            take_profit=float(position.get('tp', 0)) if position.get('tp') else None,
                            close_reason=self._get_close_reason(position),
                            close_price=float(position.get('cp', 0)) if position.get('cp') else None,
                            pnl_usdt=float(position.get('up', 0)),
                            pnl_percent=float(position.get('cr', 0)),
                            position_balance=Decimal(str(position.get('pb', 0))),
                            margin_ratio=Decimal(str(position.get('mr', 0))) if position.get('mr') else None,
                            margin_ratio_level=position.get('mrl', ''),
                            update_time=datetime.fromtimestamp(position.get('t', 0) / 1000)
                        )
                        
                        # 調用回調函數
                        if self.position_callback:
                            self.position_callback(position_info)
                            
            elif event_type == 'ORDER_TRADE_UPDATE':
                # 處理訂單交易更新事件
                order = msg.get('o', {})
                if order:
                    logger.info(f"訂單更新: {order}")
                    # 這裡可以添加訂單狀態變更的處理邏輯
                    
            elif event_type == 'TRADE_LITE':
                # 處理簡化交易事件
                trade = msg.get('o', {})
                if trade:
                    logger.info(f"簡化交易更新: {trade}")
                    # 這裡可以添加交易更新的處理邏輯
                    
            elif event_type == 'MARGIN_CALL':
                # 處理保證金通知事件
                positions = msg.get('p', [])
                for position in positions:
                    logger.warning(f"保證金通知: {position}")
                    # 這裡可以添加保證金通知的處理邏輯
                    
            elif event_type == 'ACCOUNT_CONFIG_UPDATE':
                # 處理帳戶配置更新事件
                config = msg.get('ac', {})
                if config:
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
            self.position_callback = None
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
                    
                return PositionInfo(
                    symbol=position['symbol'],
                    position_amt=Decimal(position['positionAmt']),
                    entry_price=Decimal(position['entryPrice']),
                    mark_price=Decimal(position['markPrice']),
                    un_realized_profit=Decimal(position['unRealizedProfit']),
                    liquidation_price=Decimal(position['liquidationPrice']),
                    leverage=int(position['leverage']),
                    max_notional_value=Decimal(position['maxNotionalValue']),
                    margin_type=position['marginType'],
                    isolated_margin=Decimal(position['isolatedMargin']),
                    is_auto_add_margin=position['isAutoAddMargin']
                )
            else:
                # 獲取 symbol_list 中的所有倉位
                positions = []
                for symbol in self.symbol_list:
                    try:
                        response = self.client.get_position_risk(symbol=symbol)
                        if response and Decimal(response[0]['positionAmt']) != 0:  # 只返回有倉位的
                            position = response[0]
                            positions.append(PositionInfo(
                                symbol=position['symbol'],
                                position_amt=Decimal(position['positionAmt']),
                                entry_price=Decimal(position['entryPrice']),
                                mark_price=Decimal(position['markPrice']),
                                un_realized_profit=Decimal(position['unRealizedProfit']),
                                liquidation_price=Decimal(position['liquidationPrice']),
                                leverage=int(position['leverage']),
                                max_notional_value=Decimal(position['maxNotionalValue']),
                                margin_type=position['marginType'],
                                isolated_margin=Decimal(position['isolatedMargin']),
                                is_auto_add_margin=position['isAutoAddMargin']
                            ))
                    except Exception as e:
                        logger.error(f"獲取 {symbol} 倉位風險信息失敗: {str(e)}")
                        continue
                return positions if positions else None
                
        except Exception as e:
            logger.error(f"獲取倉位風險信息失敗: {str(e)}")
            raise
            
    def get_account_info(self) -> AccountInfo:
        """
        獲取賬戶信息
        
        Returns:
            AccountInfo: 賬戶信息
        """
        try:
            account = self.client.account()
            
            return AccountInfo(
                total_wallet_balance=float(account.get('totalWalletBalance', 0)),
                total_unrealized_profit=float(account.get('totalUnrealizedProfit', 0)),
                total_margin_balance=float(account.get('totalMarginBalance', 0)),
                total_position_initial_margin=float(account.get('totalPositionInitialMargin', 0)),
                total_open_order_initial_margin=float(account.get('totalOpenOrderInitialMargin', 0)),
                total_cross_wallet_balance=float(account.get('totalCrossWalletBalance', 0)),
                available_balance=float(account.get('availableBalance', 0)),
                max_withdraw_amount=float(account.get('maxWithdrawAmount', 0)),
                total_initial_margin=float(account.get('totalInitialMargin', 0)),
                total_maint_margin=float(account.get('totalMaintMargin', 0)),
                total_cross_un_pnl=float(account.get('totalCrossUnPnl', 0)),
                assets=[{
                    'asset': asset.get('asset', ''),
                    'wallet_balance': float(asset.get('walletBalance', 0)),
                    'unrealized_profit': float(asset.get('unrealizedProfit', 0)),
                    'margin_balance': float(asset.get('marginBalance', 0)),
                    'maint_margin': float(asset.get('maintMargin', 0)),
                    'initial_margin': float(asset.get('initialMargin', 0)),
                    'position_initial_margin': float(asset.get('positionInitialMargin', 0)),
                    'open_order_initial_margin': float(asset.get('openOrderInitialMargin', 0)),
                    'cross_wallet_balance': float(asset.get('crossWalletBalance', 0)),
                    'cross_un_pnl': float(asset.get('crossUnPnl', 0)),
                    'available_balance': float(asset.get('availableBalance', 0)),
                    'max_withdraw_amount': float(asset.get('maxWithdrawAmount', 0)),
                    'margin_available': bool(asset.get('marginAvailable', False)),
                    'update_time': int(time.time() * 1000)
                } for asset in account.get('assets', [])],
                positions=[{
                    'symbol': position.get('symbol', ''),
                    'initial_margin': float(position.get('initialMargin', 0)),
                    'maint_margin': float(position.get('maintMargin', 0)),
                    'unrealized_profit': float(position.get('unrealizedProfit', 0)),
                    'position_initial_margin': float(position.get('positionInitialMargin', 0)),
                    'open_order_initial_margin': float(position.get('openOrderInitialMargin', 0)),
                    'leverage': int(position.get('leverage', 1)),
                    'isolated': bool(position.get('isolated', False)),
                    'entry_price': float(position.get('entryPrice', 0)),
                    'max_notional': float(position.get('maxNotional', 0)),
                    'position_side': position.get('positionSide', 'BOTH'),
                    'position_amt': float(position.get('positionAmt', 0)),
                    'notional': float(position.get('notional', 0)),
                    'isolated_wallet': float(position.get('isolatedWallet', 0)),
                    'update_time': int(time.time() * 1000)
                } for position in account.get('positions', [])],
                update_time=int(time.time() * 1000)
            )
            
        except Exception as e:
            logger.error(f"獲取賬戶信息失敗: {str(e)}")
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

    def _convert_to_order_result(self, response: Dict) -> OrderResult:
        """將 Binance API 返回的訂單數據轉換為 OrderResult 對象
        
        Args:
            response: Binance API 返回的訂單數據
            
        Returns:
            OrderResult: 轉換後的 OrderResult 對象
        """
        try:
            return OrderResult(
                symbol=response['symbol'],
                side=OrderSide[response['side']],
                type=OrderType[response['type']],
                quantity=Decimal(str(response['origQty'])),
                transact_time=response.get('time', response['updateTime']),
                time_in_force=TimeInForce[response['timeInForce']],
                order_id=response['orderId'],
                client_order_id=response['clientOrderId'],
                price=Decimal(str(response['price'])) if response['price'] != '0' else None,
                orig_qty=Decimal(str(response['origQty'])),
                executed_qty=Decimal(str(response['executedQty'])),
                cummulative_quote_qty=Decimal(str(response['cumQuote'])),
                status=OrderStatus[response['status']],
                iceberg_qty=Decimal(str(response.get('icebergQty', '0'))) if response.get('icebergQty') else None,
                time=response.get('time', response['updateTime']),
                update_time=response['updateTime'],
                is_working=response.get('isWorking', False),
                orig_quote_order_qty=Decimal(str(response.get('origQuoteOrderQty', '0'))) if response.get('origQuoteOrderQty') else None
            )
        except Exception as e:
            logger.error(f"轉換訂單結果失敗: {str(e)}")
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
            required_params = ['symbol', 'side', 'type', 'quantity']
            for param in required_params:
                if param not in params:
                    raise ValueError(f"缺少必要參數: {param}")
            
            # 根據訂單類型檢查其他必要參數
            order_type = params['type']
            
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
            
            # 檢查數量
            if not params['quantity'] or float(params['quantity']) <= 0:
                raise ValueError("訂單數量必須大於0")
            
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
            
            # 使用公共方法轉換訂單結果
            return self._convert_to_order_result(response)
            
        except Exception as e:
            logger.error(f"下單失敗: {str(e)}")
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
            
            # 使用公共方法轉換訂單結果
            return self._convert_to_order_result(response)
            
        except Exception as e:
            logger.error(f"查詢訂單失敗: {str(e)}")
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

    def _convert_to_order(self, order_data: Dict) -> Order:
        """將 Binance API 返回的訂單數據轉換為 Order 對象
        
        Args:
            order_data: Binance API 返回的訂單數據，可以是 REST API 或 WebSocket 格式
            
        Returns:
            Order: 轉換後的 Order 對象
        """
        try:
            # 處理 WebSocket 訂單更新事件的數據格式
            if 'o' in order_data:
                order_data = order_data['o']
                
            # 判斷數據格式並提取字段
            if 'symbol' in order_data:  # REST API 格式
                symbol = order_data['symbol']
                side = order_data['side']
                type_ = order_data['type']
                quantity = order_data['origQty']
                price = order_data['price']
                stop_price = order_data.get('stopPrice')
                time_in_force = order_data.get('timeInForce')
                reduce_only = order_data.get('reduceOnly', False)
                close_position = order_data.get('closePosition', False)
                working_type = order_data.get('workingType')
                price_protect = order_data.get('priceProtect', False)
                client_order_id = order_data.get('clientOrderId')
                order_id = order_data['orderId']
                orig_qty = order_data['origQty']
                executed_qty = order_data['executedQty']
                cummulative_quote_qty = order_data['cumQuote']
                status = order_data['status']
                time = order_data.get('time')
                update_time = order_data.get('updateTime')
                position_side = order_data.get('positionSide')
                price_match = order_data.get('priceMatch')
                self_trade_prevention_mode = order_data.get('selfTradePreventionMode')
                good_till_date = order_data.get('goodTillDate')
                activate_price = order_data.get('activatePrice')
                price_rate = order_data.get('priceRate')
                orig_type = order_data.get('origType')
                avg_price = order_data.get('avgPrice')
            else:  # WebSocket 格式
                symbol = order_data['s']
                side = order_data['S']
                type_ = order_data['o']
                quantity = order_data['q']
                price = order_data['p']
                stop_price = order_data.get('sp')
                time_in_force = order_data.get('f')
                reduce_only = order_data.get('R', False)
                close_position = order_data.get('cp', False)
                working_type = order_data.get('wt')
                price_protect = order_data.get('pP', False)
                client_order_id = order_data.get('c')
                order_id = order_data['i']
                orig_qty = order_data['q']
                executed_qty = order_data['z']
                cummulative_quote_qty = order_data.get('Z', '0')
                status = order_data['X']
                time = order_data.get('T')
                update_time = order_data.get('T')
                position_side = order_data.get('ps')
                price_match = order_data.get('pm')
                self_trade_prevention_mode = order_data.get('V')
                good_till_date = order_data.get('gtd')
                activate_price = order_data.get('ap')
                price_rate = order_data.get('rp')
                orig_type = order_data.get('ot')
                avg_price = order_data.get('ap')
                
            return Order(
                symbol=symbol,
                side=OrderSide[side],
                type=OrderType[type_],
                quantity=Decimal(str(quantity)),
                price=Decimal(str(price)) if price != '0' else None,
                stop_price=Decimal(str(stop_price)) if stop_price and type_ != 'TRAILING_STOP_MARKET' else None,
                time_in_force=TimeInForce[time_in_force] if time_in_force else None,
                reduce_only=reduce_only,
                close_position=close_position,
                working_type=WorkingType[working_type] if working_type else None,
                price_protect=price_protect,
                new_client_order_id=client_order_id,
                order_id=order_id,
                client_order_id=client_order_id,
                orig_qty=Decimal(str(orig_qty)),
                executed_qty=Decimal(str(executed_qty)),
                cummulative_quote_qty=Decimal(str(cummulative_quote_qty)),
                status=OrderStatus[status],
                time=time,
                update_time=update_time,
                is_working=status in ['NEW', 'PARTIALLY_FILLED'],
                position_side=PositionSide[position_side] if position_side else None,
                price_match=PriceMatch[price_match] if price_match else None,
                self_trade_prevention_mode=SelfTradePreventionMode[self_trade_prevention_mode] if self_trade_prevention_mode else None,
                good_till_date=good_till_date,
                activate_price=Decimal(str(activate_price)) if activate_price else None,
                price_rate=Decimal(str(price_rate)) if price_rate else None,
                orig_type=OrderType[orig_type] if orig_type else None,
                avg_price=Decimal(str(avg_price)) if avg_price else None
            )
        except Exception as e:
            logger.error(f"轉換訂單數據失敗: {str(e)}")
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
                return [self._convert_to_order(order) for order in orders 
                       if order['status'] in ['NEW', 'PARTIALLY_FILLED']]
            else:
                # 查詢 symbol_list 中的所有交易對的訂單
                all_orders = []
                for symbol in self.symbol_list:
                    try:
                        orders = self.client.get_orders(symbol=symbol, limit=limit)
                        # 只返回未完全成交的訂單
                        unfilled_orders = [self._convert_to_order(order) for order in orders 
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
            
            # 使用公共方法轉換訂單結果
            return self._convert_to_order(response)
            
        except Exception as e:
            logger.error(f"取消訂單失敗: {str(e)}")
            raise

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """取消所有訂單（只取消未完全成交的訂單）
        
        Args:
            symbol: 交易對，如果為 None 則取消 symbol_list 中的所有交易對的訂單
            
        Returns:
            List[Order]: 被取消的訂單列表
        """
        try:
            if symbol:
                # 檢查交易對是否在 symbol_list 中
                if symbol not in self.symbol_list:
                    raise ValueError(f"交易對 {symbol} 不在配置的 symbol_list 中")
                    
                # 取消指定交易對的所有訂單
                response = self.client.cancel_open_orders(symbol=symbol)
                return [self._convert_to_order(order) for order in response]
            else:
                # 取消 symbol_list 中所有交易對的訂單
                cancelled_orders = []
                for symbol in self.symbol_list:
                    try:
                        response = self.client.cancel_open_orders(symbol=symbol)
                        cancelled_orders.extend([self._convert_to_order(order) for order in response])
                    except Exception as e:
                        logger.error(f"取消 {symbol} 所有訂單失敗: {str(e)}")
                        continue
                return cancelled_orders
                
        except Exception as e:
            logger.error(f"取消所有訂單失敗: {str(e)}")
            raise