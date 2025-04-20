import sys
import os
import logging
from datetime import datetime
from decimal import Decimal
import signal
import asyncio
import time
import threading
from typing import List, Dict, Any

# 添加項目根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange import (
    # API 類
    BinanceAPI,
    OrderExecutor,
    
    # 枚舉類
    OrderSide,
    OrderType,
    OrderStatus,
    PositionStatus,
    CloseReason,
    WorkingType,
    TimeInForce,
    
    # 數據模型類
    PositionInfo,
    OrderResult,
    AccountInfo,
    Order
)

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局變量用於控制程序運行
running = True

# 測試配置
# BTCUSDT 配置
TEST_SYMBOL_BTC = "BTCUSDT"
TEST_QUANTITY_BTC = Decimal("0.005")  
TEST_PRICE_BTC = Decimal("84000")
TEST_TAKE_PROFIT_BTC = Decimal("90000")
TEST_STOP_LOSS_BTC = Decimal("70000")
TEST_ACTIVATE_PRICE_BTC = Decimal("90000")  # BTC 追蹤止損激活價格
TEST_PRICE_RATE_BTC = Decimal("3")  # BTC 追蹤止損回調率

# ETHUSDT 配置
TEST_SYMBOL_ETH = "ETHUSDT"
TEST_QUANTITY_ETH = Decimal("0.05")
TEST_PRICE_ETH = Decimal("1700")
TEST_TAKE_PROFIT_ETH = Decimal("1200")
TEST_STOP_LOSS_ETH = Decimal("1800")
TEST_ACTIVATE_PRICE_ETH = Decimal("1200")  # ETH 追蹤止損激活價格
TEST_PRICE_RATE_ETH = Decimal("3")  # ETH 追蹤止損回調率

# 全局變量用於存儲 WebSocket 接收到的消息
received_messages = []
position_updates = []
order_updates = []

# 測試開關
TEST_MARKET_DATA = True  # 是否測試市場數據功能
TEST_ACCOUNT_INFO = True  # 是否測試賬戶信息功能
TEST_ORDER_OPERATIONS = True  # 是否測試訂單操作功能
TEST_POSITION_OPERATIONS = True  # 是否測試倉位操作功能

def signal_handler(signum, frame):
    """處理 Ctrl+C 信號"""
    global running
    logger.info("收到退出信號，正在清理資源...")
    running = False

def check_testnet(api: BinanceAPI) -> bool:
    """檢查是否在測試網環境"""
    try:
        # 獲取服務器時間來檢查環境
        server_time = api.get_server_time()
        logger.info(f"服務器時間: {datetime.fromtimestamp(server_time/1000)}")
        
        # 檢查 API 端點
        if "testnet" in api.client.base_url:
            logger.info("當前在測試網環境運行")
            return True
        else:
            logger.warning("警告：當前在主網環境運行！")
            return False
    except Exception as e:
        logger.error(f"檢查測試網環境時發生錯誤: {str(e)}")
        return False

async def test_market_data(api: BinanceAPI):
    """測試市場數據相關功能"""
    if not TEST_MARKET_DATA:
        logger.info("跳過市場數據測試")
        return
        
    logger.info("開始測試市場數據相關功能...")
    
    try:
        # 獲取交易所信息
        logger.info("測試獲取交易所信息...")
        exchange_info = api.get_exchange_info()
        logger.info(f"交易所信息: {exchange_info}")
        
        # 獲取交易對信息
        logger.info("測試獲取交易對信息...")
        symbol_info = api.get_symbol_info("BTCUSDT")
        logger.info(f"BTCUSDT 交易對信息: {symbol_info}")
        
        # 獲取服務器時間
        logger.info("測試獲取服務器時間...")
        server_time = api.get_server_time()
        logger.info(f"服務器時間: {datetime.fromtimestamp(server_time/1000)}")
        
        # 獲取K線數據
        logger.info("測試獲取K線數據...")
        klines = api.get_klines("BTCUSDT", "15m", limit=10)
        logger.info(f"BTCUSDT 15分鐘K線數據: {klines}")
        
        # 獲取最新價格
        logger.info("測試獲取最新價格...")
        ticker_price = api.get_ticker_price("BTCUSDT")
        logger.info(f"BTCUSDT 最新價格: {ticker_price}")
        
        # 獲取訂單簿
        logger.info("測試獲取訂單簿...")
        order_book = api.get_order_book("BTCUSDT", limit=5)
        logger.info(f"BTCUSDT 訂單簿: {order_book}")
        
        # 獲取最近成交
        logger.info("測試獲取最近成交...")
        trades = api.get_trades("BTCUSDT", limit=5)
        logger.info(f"BTCUSDT 最近成交: {trades}")
        
        logger.info("市場數據相關功能測試完成")
        
    except Exception as e:
        logger.error(f"測試市場數據時發生錯誤: {str(e)}")
        raise

async def test_account_info(api: BinanceAPI):
    """測試賬戶信息相關功能"""
    if not TEST_ACCOUNT_INFO:
        logger.info("跳過賬戶信息測試")
        return
        
    try:
        # 測試獲取賬戶信息
        logger.info("測試獲取賬戶信息...")
        account_info = api.get_account_info()
        logger.info(f"賬戶信息: {account_info}")
        
        # 測試獲取倉位信息
        logger.info("測試獲取倉位信息...")
        position_info = api.get_position_risk("BTCUSDT")
        if position_info:
            logger.info(f"BTCUSDT 倉位信息: {position_info}")
        else:
            logger.info("沒有 BTCUSDT 倉位")
            
        # 測試獲取所有倉位
        all_positions = api.get_position_risk()
        if all_positions:
            logger.info(f"所有倉位信息: {all_positions}")
        else:
            logger.info("沒有持倉")

        logger.info("賬戶信息相關功能測試完成")
            
    except Exception as e:
        logger.error(f"測試賬戶信息時發生錯誤: {str(e)}")
        raise

async def test_order_operations():
    """測試訂單操作功能"""
    try:
        # 初始化 API 和執行器
        api = BinanceAPI()
        order_executor = OrderExecutor(api)
        
        logger.info("開始測試訂單操作功能...")
        
        # 1. 開BTC限價買單
        logger.info("1. 開BTC限價買單...")
        btc_buy_order = Order(
            symbol=TEST_SYMBOL_BTC,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=TEST_QUANTITY_BTC,
            price=TEST_PRICE_BTC,
            time_in_force=TimeInForce.GTC
        )
        btc_buy_result = order_executor.open_position_limit(btc_buy_order)
        logger.info(f"BTC限價買單創建成功: {btc_buy_result}")
        
        # 2. 開ETH限價賣單
        logger.info("2. 開ETH限價賣單...")
        eth_sell_order = Order(
            symbol=TEST_SYMBOL_ETH,
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=TEST_QUANTITY_ETH,
            price=TEST_PRICE_ETH,
            time_in_force=TimeInForce.GTC
        )
        eth_sell_result = order_executor.open_position_limit(eth_sell_order)
        logger.info(f"ETH限價賣單創建成功: {eth_sell_result}")
        
        # 3. 查詢BTC訂單狀態
        logger.info("3. 查詢BTC訂單狀態...")
        btc_order_status = order_executor.get_order_status(
            symbol=TEST_SYMBOL_BTC,
            order_id=btc_buy_result.order_id
        )
        logger.info(f"BTC訂單狀態: {btc_order_status}")
        
        # 4. 查詢ETH訂單狀態
        logger.info("4. 查詢ETH訂單狀態...")
        eth_order_status = order_executor.get_order_status(
            symbol=TEST_SYMBOL_ETH,
            order_id=eth_sell_result.order_id
        )
        logger.info(f"ETH訂單狀態: {eth_order_status}")
        
        # 5. 查詢BTC所有訂單
        logger.info("5. 查詢BTC所有訂單...")
        btc_all_orders = order_executor.get_all_orders(TEST_SYMBOL_BTC)
        logger.info(f"BTC所有訂單: {btc_all_orders}")
        
        # 6. 查詢所有訂單
        logger.info("6. 查詢所有訂單...")
        all_orders = order_executor.get_all_orders()
        logger.info(f"所有訂單數量: {len(all_orders)}")
        
        # 7. 取消BTC訂單
        logger.info("7. 取消BTC訂單...")
        canceled_btc_order = order_executor.cancel_order(
            symbol=TEST_SYMBOL_BTC,
            order_id=btc_buy_result.order_id
        )
        logger.info(f"BTC訂單已取消: {canceled_btc_order}")
        
        # 8. 再開一次BTC限價買單
        logger.info("8. 再開一次BTC限價買單...")
        btc_buy_order2 = Order(
            symbol=TEST_SYMBOL_BTC,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=TEST_QUANTITY_BTC,
            price=TEST_PRICE_BTC,
            time_in_force=TimeInForce.GTC
        )
        btc_buy_result2 = order_executor.open_position_limit(btc_buy_order2)
        logger.info(f"BTC限價買單創建成功: {btc_buy_result2}")
        
        # 9. 取消BTC所有訂單
        logger.info("9. 取消BTC所有訂單...")
        canceled_btc_orders = order_executor.cancel_all_orders(TEST_SYMBOL_BTC)
        logger.info(f"已取消的BTC訂單數量: {len(canceled_btc_orders)}")
        
        # 10. 再開一次BTC限價買單
        logger.info("10. 再開一次BTC限價買單...")
        btc_buy_order3 = Order(
            symbol=TEST_SYMBOL_BTC,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=TEST_QUANTITY_BTC,
            price=TEST_PRICE_BTC,
            time_in_force=TimeInForce.GTC
        )
        btc_buy_result3 = order_executor.open_position_limit(btc_buy_order3)
        logger.info(f"BTC限價買單創建成功: {btc_buy_result3}")
        
        # 11. 取消所有訂單
        logger.info("11. 取消所有訂單...")
        all_canceled_orders = order_executor.cancel_all_orders()
        logger.info(f"已取消的所有訂單數量: {len(all_canceled_orders)}")
        
        # 清理資源
        api.close()
        
        logger.info("訂單操作功能測試完成")
        return True
        
    except Exception as e:
        logger.error(f"訂單操作功能測試失敗: {str(e)}")
        return False

async def test_position_operations(executor: OrderExecutor):
    """測試倉位操作"""
    try:
        # 初始化 API 和執行器
        api = BinanceAPI()
        order_executor = OrderExecutor(api)
        
        # 1. 開BTC市價買單
        logger.info("1. 開BTC市價買單...")
        btc_market_order = Order(
            symbol=TEST_SYMBOL_BTC,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=TEST_QUANTITY_BTC
        )
        btc_market_result = executor.open_position_market(btc_market_order)
        logger.info(f"BTC市價買單結果: {btc_market_result}")
        
        # 2. 開ETH市價賣單
        logger.info("2. 開ETH市價賣單...")
        eth_market_order = Order(
            symbol=TEST_SYMBOL_ETH,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=TEST_QUANTITY_ETH
        )
        eth_market_result = executor.open_position_market(eth_market_order)
        logger.info(f"ETH市價賣單結果: {eth_market_result}")
        
        # 等待3秒
        logger.info("等待3秒...")
        time.sleep(3)
        
        # 3. 設置BTC止損、止盈、移動止損單(全倉)
        logger.info("3. 設置BTC止損、止盈、移動止損單(全倉)...")
        btc_position = executor.get_position(TEST_SYMBOL_BTC)
        if btc_position and btc_position.position_amt > 0:
            # 設置止損單
            btc_stop_loss = Order(
                symbol=TEST_SYMBOL_BTC,
                side=OrderSide.SELL,
                type=OrderType.STOP_MARKET,
                stop_price=TEST_STOP_LOSS_BTC,
                close_position=True
            )
            btc_stop_loss_result = executor.open_position_stop_loss(btc_stop_loss)
            logger.info(f"BTC止損單結果: {btc_stop_loss_result}")
            
            # 設置止盈單
            btc_take_profit = Order(
                symbol=TEST_SYMBOL_BTC,
                side=OrderSide.SELL,
                type=OrderType.TAKE_PROFIT_MARKET,
                stop_price=TEST_TAKE_PROFIT_BTC,
                close_position=True
            )
            btc_take_profit_result = executor.open_position_take_profit(btc_take_profit)
            logger.info(f"BTC止盈單結果: {btc_take_profit_result}")
            
            # 設置 BTC 追蹤止損訂單
            btc_trailing_stop = Order(
                symbol=TEST_SYMBOL_BTC,
                side=OrderSide.SELL,
                type=OrderType.TRAILING_STOP_MARKET,
                activate_price=TEST_ACTIVATE_PRICE_BTC,
                price_rate=TEST_PRICE_RATE_BTC,
                quantity=btc_position.position_amt,
                reduce_only=True
            )
            logger.info("設置 BTC 追蹤止損訂單...")
            trailing_result = executor.open_position_trailing(
                btc_trailing_stop,
                TEST_ACTIVATE_PRICE_BTC,
                TEST_PRICE_RATE_BTC
            )
            logger.info(f"BTC 追蹤止損訂單結果: {trailing_result}")
        
        # 4. 設置ETH止損、止盈、移動止損單(半倉)
        logger.info("4. 設置ETH止損、止盈、移動止損單(半倉)...")
        eth_position = executor.get_position(TEST_SYMBOL_ETH)
        if eth_position and eth_position.position_amt < 0:
            # 計算半倉數量
            half_quantity = abs(eth_position.position_amt) / Decimal("2")
            
            # 設置止損單
            eth_stop_loss = Order(
                symbol=TEST_SYMBOL_ETH,
                side=OrderSide.BUY,
                type=OrderType.STOP_MARKET,
                stop_price=TEST_STOP_LOSS_ETH,
                quantity=half_quantity,
                reduce_only=True
            )
            eth_stop_loss_result = executor.open_position_stop_loss(eth_stop_loss)
            logger.info(f"ETH止損單結果: {eth_stop_loss_result}")
            
            # 設置止盈單
            eth_take_profit = Order(
                symbol=TEST_SYMBOL_ETH,
                side=OrderSide.BUY,
                type=OrderType.TAKE_PROFIT_MARKET,
                stop_price=TEST_TAKE_PROFIT_ETH,
                quantity=half_quantity,
                reduce_only=True
            )
            eth_take_profit_result = executor.open_position_take_profit(eth_take_profit)
            logger.info(f"ETH止盈單結果: {eth_take_profit_result}")
            
            # 設置 ETH 追蹤止損訂單
            eth_trailing_stop = Order(
                symbol=TEST_SYMBOL_ETH,
                side=OrderSide.BUY,
                type=OrderType.TRAILING_STOP_MARKET,
                activate_price=TEST_ACTIVATE_PRICE_ETH,
                price_rate=TEST_PRICE_RATE_ETH,
                quantity=half_quantity,
                reduce_only=True
            )
            logger.info("設置 ETH 追蹤止損訂單...")
            trailing_result = executor.open_position_trailing(
                eth_trailing_stop,
                TEST_ACTIVATE_PRICE_ETH,
                TEST_PRICE_RATE_ETH
            )
            logger.info(f"ETH 追蹤止損訂單結果: {trailing_result}")
        
        # 等待1分鐘
        logger.info("等待10秒...")
        time.sleep(10)
        
        # 5. 平倉BTC艙位
        logger.info("5. 平倉BTC艙位...")
        close_btc_result = executor.close_position(TEST_SYMBOL_BTC)
        logger.info(f"平倉BTC結果: {close_btc_result}")
        
        # 6. 再開一次BTC市價買單
        logger.info("6. 再開一次BTC市價買單...")
        btc_market_order_again = Order(
            symbol=TEST_SYMBOL_BTC,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=TEST_QUANTITY_BTC
        )
        btc_market_result_again = executor.open_position_market(btc_market_order_again)
        logger.info(f"再次開BTC市價買單結果: {btc_market_result_again}")
        
        # 7. 設置BTC止損、止盈、移動止損單(全倉)
        logger.info("7. 設置BTC止損、止盈、移動止損單(全倉)...")
        btc_position_again = executor.get_position(TEST_SYMBOL_BTC)
        if btc_position_again and btc_position_again.position_amt > 0:
            # 設置止損單
            btc_stop_loss_again = Order(
                symbol=TEST_SYMBOL_BTC,
                side=OrderSide.SELL,
                type=OrderType.STOP_MARKET,
                stop_price=TEST_STOP_LOSS_BTC,
                close_position=True
            )
            btc_stop_loss_result_again = executor.open_position_stop_loss(btc_stop_loss_again)
            logger.info(f"BTC止損單結果: {btc_stop_loss_result_again}")
            
            # 設置止盈單
            btc_take_profit_again = Order(
                symbol=TEST_SYMBOL_BTC,
                side=OrderSide.SELL,
                type=OrderType.TAKE_PROFIT_MARKET,
                stop_price=TEST_TAKE_PROFIT_BTC,
                close_position=True
            )
            btc_take_profit_result_again = executor.open_position_take_profit(btc_take_profit_again)
            logger.info(f"BTC止盈單結果: {btc_take_profit_result_again}")
            
            # 設置新的 BTC 追蹤止損訂單
            btc_trailing_stop_again = Order(
                symbol=TEST_SYMBOL_BTC,
                side=OrderSide.SELL,
                type=OrderType.TRAILING_STOP_MARKET,
                activate_price=TEST_ACTIVATE_PRICE_BTC,
                price_rate=TEST_PRICE_RATE_BTC,
                quantity=btc_position_again.position_amt,
                reduce_only=True
            )
            logger.info("設置新的 BTC 追蹤止損訂單...")
            trailing_result = executor.open_position_trailing(
                btc_trailing_stop_again,
                TEST_ACTIVATE_PRICE_BTC,
                TEST_PRICE_RATE_BTC
            )
            logger.info(f"新的 BTC 追蹤止損訂單結果: {trailing_result}")
        
        # 8. 平掉所有倉位
        logger.info("8. 平掉所有倉位...")
        close_all_result = executor.close_all_positions()
        logger.info(f"平掉所有倉位結果: {close_all_result}")

        all_canceled_orders = order_executor.cancel_all_orders()
        logger.info(f"已取消的所有訂單數量: {len(all_canceled_orders)}")

        logger.info("倉位操作功能測試完成")
        
    except Exception as e:
        logger.error(f"測試倉位操作時發生錯誤: {str(e)}")
        raise

def position_callback(position_info: PositionInfo):
    """倉位更新回調函數"""
    logger.info(f"收到倉位更新: {position_info}")
    position_updates.append(position_info)

def order_callback(order_info: Dict):
    """訂單更新回調函數"""
    logger.info(f"收到訂單更新: {order_info}")
    order_updates.append(order_info)

def start_websocket_listener(api: BinanceAPI):
    """啟動 WebSocket 監聽器"""
    try:
        api.start_position_listener(position_callback)
        logger.info("WebSocket 監聽器啟動成功")
    except Exception as e:
        logger.error(f"WebSocket 監聽器啟動失敗: {str(e)}")
        raise

def test_websocket_connection(api: BinanceAPI):
    """測試 WebSocket 連接"""
    # 啟動 WebSocket 監聽器
    websocket_thread = threading.Thread(target=start_websocket_listener, args=(api,))
    websocket_thread.daemon = True
    websocket_thread.start()
    
    # 等待連接建立
    time.sleep(5)
    
    # 檢查連接狀態
    assert api.ws_client is not None
    assert api.ws_client.sock is not None
    assert api.ws_client.sock.connected
    assert api.listen_key is not None

def test_main():
    """主測試函數"""
    # 創建 API 和執行器實例
    api = BinanceAPI()
    executor = OrderExecutor(api)
    
    try:
        # 啟動 WebSocket 監聽器
        websocket_thread = threading.Thread(target=start_websocket_listener, args=(api,))
        websocket_thread.daemon = True
        websocket_thread.start()
        
        # 等待 WebSocket 連接建立
        time.sleep(5)
        
        # 執行測試
        test_websocket_connection(api)
        
        # 創建事件循環
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 根據測試開關執行相應的測試
        if TEST_MARKET_DATA:
            logger.info("執行市場數據測試...")
            loop.run_until_complete(test_market_data(api))
            
        if TEST_ACCOUNT_INFO:
            logger.info("執行賬戶信息測試...")
            loop.run_until_complete(test_account_info(api))
            
        if TEST_ORDER_OPERATIONS:
            logger.info("執行訂單操作測試...")
            loop.run_until_complete(test_order_operations())
            
        if TEST_POSITION_OPERATIONS:
            logger.info("執行倉位操作測試...")
            loop.run_until_complete(test_position_operations(executor))
            
    finally:
        # 清理
        api.close()
        loop.close()

if __name__ == "__main__":
    test_main() 