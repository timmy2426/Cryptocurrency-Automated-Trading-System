from binance.client import Client
from binance.websockets import BinanceSocketManager
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
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from websocket import create_connection, WebSocketApp
from dotenv import load_dotenv
from enum import Enum
from dataclasses import dataclass
from decimal import Decimal

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderSide(Enum):
    """訂單方向枚舉"""
    BUY = "BUY"
    SELL = "SELL"

class PositionStatus(Enum):
    """倉位狀態枚舉"""
    OPEN = "OPEN"  # 開倉
    CLOSE = "CLOSE"  # 平倉

class CloseReason(Enum):
    """平倉原因枚舉"""
    STOP_LOSS = "STOP_LOSS"  # 止損
    TAKE_PROFIT = "TAKE_PROFIT"  # 止盈
    TRAILING_STOP = "TRAILING_STOP"  # 移動止損
    LIQUIDATION = "LIQUIDATION"  # 爆倉
    MANUAL = "MANUAL"  # 手動平倉

@dataclass
class PositionInfo:
    """倉位信息數據類"""
    status: PositionStatus  # 倉位狀態
    symbol: str  # 交易對
    leverage: int  # 槓桿
    size: float  # 倉位大小
    margin: float  # 保證金
    entry_price: float  # 開倉價格
    stop_loss: Optional[float]  # 止損價格
    take_profit: Optional[float]  # 止盈價格
    close_reason: Optional[CloseReason]  # 平倉原因
    close_price: Optional[float]  # 平倉價格
    pnl_usdt: Optional[float]  # 盈虧金額(USDT)
    pnl_percent: Optional[float]  # 盈虧比率(%)

@dataclass
class AccountInfo:
    """賬戶信息數據類"""
    total_wallet_balance: float
    total_unrealized_profit: float
    total_margin_balance: float
    available_balance: float
    max_withdraw_amount: float
    assets: List[Dict]
    positions: List[PositionInfo]
    update_time: int

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
        # 加載環境變量
        load_dotenv(dotenv_path='config/api_keys.env')
        
        # 讀取設置文件
        with open('config/settings.yaml', 'r', encoding='utf-8') as f:
            self.settings = yaml.safe_load(f)
            
        # 根據設置決定是否使用測試網
        self.testnet = self.settings['control']['testnet']
        
        # 獲取 API 密鑰
        self.api_key = os.getenv('BINANCE_TESTNET_API_KEY' if self.testnet else 'BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_TESTNET_API_SECRET' if self.testnet else 'BINANCE_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            raise ValueError(f"未找到{'測試網' if self.testnet else '主網'} API 密鑰，請檢查 config/api_keys.env 文件")
        
        # 初始化客戶端
        self.client = Client(self.api_key, self.api_secret, testnet=self.testnet)
        
        # 設置 API 端點
        if self.testnet:
            self.client.API_URL = self.settings['binance_api']['testnet_rest_api_url']
            
        # 初始化 WebSocket 相關變量
        self.ws = None
        self.conn_key = None
        self.callback = None
        self.last_ping_time = None
        self.authenticated = False
        
        logger.info(f"已初始化 Binance API，使用{'測試網' if self.testnet else '主網'}")
        
    def _generate_signature(self, params: Dict) -> str:
        """生成簽名"""
        payload = '&'.join([f'{param}={value}' for param, value in sorted(params.items())])
        signature = self.client._get_signature(payload)
        return signature
        
    def _authenticate_websocket(self) -> None:
        """認證 WebSocket 連接"""
        try:
            timestamp = int(time.time() * 1000)
            params = {
                'apiKey': self.api_key,
                'timestamp': timestamp
            }
            params['signature'] = self._generate_signature(params)
            
            request = {
                'id': str(uuid.uuid4()),
                'method': 'session.logon',
                'params': params
            }
            
            self.ws.send(json.dumps(request))
            response = json.loads(self.ws.recv())
            
            if response['status'] == 200:
                self.authenticated = True
                logger.info("WebSocket 認證成功")
            else:
                raise Exception(f"WebSocket 認證失敗: {response['error']['msg']}")
                
        except Exception as e:
            logger.error(f"WebSocket 認證時發生錯誤: {str(e)}")
            raise
            
    def _on_message(self, ws, message):
        """處理 WebSocket 消息"""
        try:
            data = json.loads(message)
            
            # 處理 ping 消息
            if 'ping' in data:
                pong = {'pong': data['ping']}
                ws.send(json.dumps(pong))
                self.last_ping_time = time.time()
                return
                
            # 處理錯誤消息
            if 'error' in data:
                logger.error(f"WebSocket 錯誤: {data['error']['msg']}")
                return
                
            # 處理 K 線數據
            if 'k' in data:
                kline = data['k']
                df = pd.DataFrame([{
                    'timestamp': pd.to_datetime(kline['t'], unit='ms'),
                    'open': float(kline['o']),
                    'high': float(kline['h']),
                    'low': float(kline['l']),
                    'close': float(kline['c']),
                    'volume': float(kline['v']),
                    'close_time': pd.to_datetime(kline['T'], unit='ms'),
                    'quote_asset_volume': float(kline['q']),
                    'number_of_trades': int(kline['n']),
                    'taker_buy_base_asset_volume': float(kline['V']),
                    'taker_buy_quote_asset_volume': float(kline['Q']),
                    'is_final': kline['x']
                }])
                df.set_index('timestamp', inplace=True)
                if self.callback:
                    self.callback(df)
                    
        except Exception as e:
            logger.error(f"處理 WebSocket 消息時發生錯誤: {str(e)}")
            
    def _on_error(self, ws, error):
        """處理 WebSocket 錯誤"""
        logger.error(f"WebSocket 錯誤: {str(error)}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        """處理 WebSocket 關閉"""
        logger.info("WebSocket 連接已關閉")
        self.authenticated = False
        
    def _on_open(self, ws):
        """處理 WebSocket 打開"""
        logger.info("WebSocket 連接已建立")
        self._authenticate_websocket()
        
    def start_kline_socket(self, 
                          symbol: str, 
                          interval: str, 
                          callback: Callable[[pd.DataFrame], None]) -> None:
        """
        啟動 K 線 WebSocket
        
        Args:
            symbol: 交易對，例如 'BTCUSDT'
            interval: K線時間週期，例如 '1m', '1h', '1d'
            callback: 回調函數，接收 DataFrame 格式的 K 線數據
        """
        try:
            # 驗證時間週期
            if interval not in self.KLINE_INTERVALS:
                raise ValueError(f"無效的時間週期: {interval}。可用的週期: {list(self.KLINE_INTERVALS.keys())}")
            
            # 設置回調函數
            self.callback = callback
            
            # 獲取 WebSocket 端點
            ws_endpoint = self.settings['binance_api']['webSocket_base_endpoint_for_testnet' if self.testnet else 'webSocket_base_endpoint']
            
            # 創建 WebSocket 連接
            self.ws = WebSocketApp(
                ws_endpoint,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            # 啟動 WebSocket 連接
            self.ws.run_forever()
            
            logger.info(f"已啟動 {symbol} {interval} K 線 WebSocket（{'測試網' if self.testnet else '主網'}）")
            
        except Exception as e:
            logger.error(f"啟動 K 線 WebSocket 失敗: {str(e)}")
            raise
            
    def stop_kline_socket(self) -> None:
        """停止 K 線 WebSocket"""
        try:
            if self.ws:
                self.ws.close()
                self.ws = None
                self.authenticated = False
                self.callback = None
                logger.info("已停止 K 線 WebSocket")
        except Exception as e:
            logger.error(f"停止 K 線 WebSocket 失敗: {str(e)}")
            raise
            
    def get_historical_klines(self,
                            symbol: str,
                            interval: str,
                            limit: int = 500,
                            start_time: Optional[Union[int, str, datetime]] = None,
                            end_time: Optional[Union[int, str, datetime]] = None) -> pd.DataFrame:
        """
        獲取歷史 K 線數據（使用 REST API）
        
        Args:
            symbol: 交易對，例如 'BTCUSDT'
            interval: K線時間週期，例如 '1m', '1h', '1d'
            limit: 獲取 K 線數量，最大 1000
            start_time: 開始時間（可選）
            end_time: 結束時間（可選）
            
        Returns:
            pd.DataFrame: 包含 K 線數據的 DataFrame
        """
        try:
            # 驗證時間週期
            if interval not in self.KLINE_INTERVALS:
                raise ValueError(f"無效的時間週期: {interval}。可用的週期: {list(self.KLINE_INTERVALS.keys())}")
            
            # 驗證數量限制
            if limit > 1000:
                logger.warning("K線數量超過 1000，將自動限制為 1000")
                limit = 1000
                
            # 獲取 K 線數據
            klines = self.client.get_historical_klines(
                symbol=symbol,
                interval=self.KLINE_INTERVALS[interval],
                limit=limit,
                startTime=start_time,
                endTime=end_time
            )
            
            # 轉換為 DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # 轉換數據類型
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            # 設置時間戳為索引
            df.set_index('timestamp', inplace=True)
            
            logger.info(f"已獲取 {symbol} {interval} 歷史 K 線數據（{'測試網' if self.testnet else '主網'}）")
            return df
            
        except BinanceAPIException as e:
            logger.error(f"獲取歷史 K 線數據失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"發生未知錯誤: {str(e)}")
            raise
            
    def get_available_intervals(self) -> List[str]:
        """
        獲取可用的 K 線時間週期
        
        Returns:
            List[str]: 可用的時間週期列表
        """
        return list(self.KLINE_INTERVALS.keys())

    def get_order_book(self, 
                      symbol: str, 
                      side: OrderSide, 
                      quantity: float, 
                      limit: int = 100) -> Tuple[float, float]:
        """
        獲取訂單簿信息
        
        Args:
            symbol: 交易對，例如 'BTCUSDT'
            side: 訂單方向，OrderSide.BUY 或 OrderSide.SELL
            quantity: 需要的數量
            limit: 訂單簿深度，可選值：[5, 10, 20, 50, 100, 500, 1000]，默認 100
            
        Returns:
            Tuple[float, float]: (平均價格, 可成交數量)
            
        Raises:
            ValueError: 當參數無效時
            BinanceAPIException: 當 API 調用失敗時
        """
        try:
            # 驗證 limit 參數
            if limit not in self.ORDERBOOK_LIMITS:
                raise ValueError(f"無效的訂單簿深度: {limit}。可用的深度: {list(self.ORDERBOOK_LIMITS.keys())}")
            
            # 獲取訂單簿
            depth = self.client.futures_order_book(symbol=symbol, limit=limit)
            
            # 根據方向選擇訂單簿
            orders = depth['bids'] if side == OrderSide.BUY else depth['asks']
            
            # 計算可成交的數量和平均價格
            total_quantity = 0.0
            total_value = 0.0
            
            for price, qty in orders:
                price = float(price)
                qty = float(qty)
                
                if total_quantity + qty >= quantity:
                    # 最後一部分
                    remaining = quantity - total_quantity
                    total_value += remaining * price
                    total_quantity = quantity
                    break
                else:
                    # 全部成交
                    total_value += qty * price
                    total_quantity += qty
            
            if total_quantity == 0:
                logger.warning(f"訂單簿中沒有足夠的流動性來滿足 {quantity} {symbol} 的 {side.value} 訂單")
                return 0.0, 0.0
                
            average_price = total_value / total_quantity
            
            logger.info(f"訂單簿分析完成: {symbol} {side.value} {quantity}")
            logger.info(f"平均價格: {average_price}, 可成交數量: {total_quantity}")
            
            return average_price, total_quantity
            
        except BinanceAPIException as e:
            logger.error(f"獲取訂單簿失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"發生未知錯誤: {str(e)}")
            raise

    def start_position_listener(self, callback: Callable[[PositionInfo], None]) -> None:
        """
        啟動倉位監聽器
        
        Args:
            callback: 回調函數，接收 PositionInfo 對象
        """
        try:
            # 生成監聽 key
            self.position_listen_key = self.client.futures_stream_get_listen_key()
            
            # 設置 WebSocket 端點
            ws_endpoint = f"{self.settings['binance_api']['webSocket_base_endpoint_for_testnet' if self.testnet else 'webSocket_base_endpoint']}/ws/{self.position_listen_key}"
            
            # 創建 WebSocket 連接
            self.position_ws = WebSocketApp(
                ws_endpoint,
                on_message=lambda ws, msg: self._on_position_message(ws, msg, callback),
                on_error=self._on_position_error,
                on_close=self._on_position_close,
                on_open=self._on_position_open
            )
            
            # 啟動 WebSocket 連接
            self.position_ws.run_forever()
            
            logger.info("倉位監聽器已啟動")
            
        except Exception as e:
            logger.error(f"啟動倉位監聽器失敗: {str(e)}")
            raise
            
    def stop_position_listener(self) -> None:
        """停止倉位監聽器"""
        try:
            if self.position_ws:
                self.position_ws.close()
                self.position_ws = None
                logger.info("倉位監聽器已停止")
        except Exception as e:
            logger.error(f"停止倉位監聽器失敗: {str(e)}")
            raise
            
    def _on_position_message(self, ws, message, callback):
        """處理倉位消息"""
        try:
            data = json.loads(message)
            
            # 處理 ping 消息
            if 'ping' in data:
                pong = {'pong': data['ping']}
                ws.send(json.dumps(pong))
                return
                
            # 處理倉位更新
            if data['e'] == 'ACCOUNT_UPDATE':
                for position in data['a']['P']:
                    # 檢查倉位是否為 0（平倉）
                    if float(position['pa']) == 0:
                        # 獲取平倉原因
                        close_reason = self._get_close_reason(position)
                        
                        # 創建 PositionInfo 對象
                        position_info = PositionInfo(
                            status=PositionStatus.CLOSE,
                            symbol=position['s'],
                            leverage=int(position['l']),
                            size=float(position['pa']),
                            margin=float(position['m']),
                            entry_price=float(position['ep']),
                            stop_loss=float(position['sl']) if position['sl'] else None,
                            take_profit=float(position['tp']) if position['tp'] else None,
                            close_reason=close_reason,
                            close_price=float(position['cp']),
                            pnl_usdt=float(position['rp']),
                            pnl_percent=float(position['cr'])
                        )
                    else:
                        # 開倉或更新倉位
                        position_info = PositionInfo(
                            status=PositionStatus.OPEN,
                            symbol=position['s'],
                            leverage=int(position['l']),
                            size=float(position['pa']),
                            margin=float(position['m']),
                            entry_price=float(position['ep']),
                            stop_loss=float(position['sl']) if position['sl'] else None,
                            take_profit=float(position['tp']) if position['tp'] else None,
                            close_reason=None,
                            close_price=None,
                            pnl_usdt=None,
                            pnl_percent=None
                        )
                    
                    # 調用回調函數
                    callback(position_info)
                    
        except Exception as e:
            logger.error(f"處理倉位消息時發生錯誤: {str(e)}")
            
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
            
    def _on_position_error(self, ws, error):
        """處理倉位監聽器錯誤"""
        logger.error(f"倉位監聽器錯誤: {str(error)}")
        
    def _on_position_close(self, ws, close_status_code, close_msg):
        """處理倉位監聽器關閉"""
        logger.info("倉位監聽器連接已關閉")
        
    def _on_position_open(self, ws):
        """處理倉位監聽器打開"""
        logger.info("倉位監聽器連接已建立")

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
