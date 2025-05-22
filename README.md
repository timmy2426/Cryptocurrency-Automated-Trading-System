# 加密貨幣自動交易系統

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/timmy2426/Cryptocurrency-Automated-Trading-System)&nbsp;
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)&nbsp;
[![License: AGPL v3](https://img.shields.io/badge/License-AGPLv3-orange.svg)](https://www.gnu.org/licenses/agpl-3.0.html)&nbsp;

## 專案概述

這是一個基於 Python 開發的加密貨幣 U 本位期貨交易系統，主要針對 Binance 期貨市場進行自動化交易。系統採用模組化設計，具有完整的風險控制機制和即時監控功能。

## 交易策略

### 技術指標

- 使用 15 分鐘 K 線時間框架為主進行技術分析
- 使用布林通道搭配 RSI 進行交易訊號判斷
- 使用多週期 SMA 快慢線判斷趨勢方向

### 策略種類

- **順勢多單**

  - 進場條件

    - 收盤價突破布林上軌
    - RSI 高於上漲動能閾值，尚未超買且呈持續上升趨勢
    - 布林帶寬擴張，且變化率超過閾值

  - 出場條件
    - RSI 超買反轉
    - 收盤價回到布林中軌

- **順勢空單**

  - 進場條件

    - 收盤價跌破布林下軌
    - RSI 低於下跌動能閾值，尚未超賣且呈持續下降趨勢
    - 布林帶寬擴張，且變化率超過閾值

  - 出場條件
    - RSI 超賣反轉
    - 收盤價回到布林中軌

- **逆勢多單**

  - 進場條件

    - 收盤價接近或觸及布林下軌
    - RSI 處於超賣區域，且出現反轉跡象

  - 出場條件
    - RSI 升至 50 之上
    - 收盤價接近布林中軌

- **逆勢空單**

  - 進場條件

    - 收盤價接近或觸及布林上軌
    - RSI 處於超買區域，且出現反轉跡象

  - 出場條件
    - RSI 降至 50 之下
    - 收盤價接近布林中軌

### 風險管理

- 控制單一倉位的最大損失上限為總資金的固定百分比
- 限制單一倉位的最長持有時間
- 限制每日最大虧損金額
- 限制每日交易次數
- 限制保證金使用百分比
- 限制進場的最小成交量和布林帶寬閾值
- 極端市場情況觸發冷靜期
- 使用 ATR 動態調整倉位大小
- 針對異常倉位(無法設定止損或倉位紀錄不完整)採取即時平倉措施

## 系統架構

### 核心模組

- **BinanceAPI** (`exchange/binance_api.py`)

  - 封裝 Binance 期貨 API
  - 處理 REST API 請求
  - 管理 WebSocket 連接
  - 處理訂單和倉位更新

- **PositionManager** (`core/position_manager.py`)

  - 管理交易倉位
  - 計算倉位大小
  - 控制風險參數
  - 處理止損止盈

- **Trader** (`core/trader.py`)

  - 執行交易策略
  - 管理交易信號
  - 控制交易流程

### 支援模組

- **DataLoader** (`data/data_loader.py`)

  - 獲取市場數據
  - 處理 K 線數據
  - 計算技術指標

- **EventLogger** (`core/event_logger.py`)

  - 記錄交易事件
  - 記錄錯誤日誌
  - 生成交易報告

- **Discord Bot** (`discord_bot/`)

  - 格式化消息
  - 發送交易通知
  - 發送心跳通知

## 主要功能

### 交易功能

- 自動化交易執行
- 多種訂單類型支援
- 追蹤止損功能
- 倉位管理

### 風險控制

- 保證金使用率限制
- 單日虧損限制
- 交易次數限制
- 冷卻期機制
- 滑價控制

### 監控功能

- 即時倉位監控
- 訂單狀態追蹤
- 帳戶權益監控
- 交易統計分析

## 技術特點

- 模組化設計
- 多線程機制
- 自動重連機制
- 完整的錯誤處理
- 詳細的日誌記錄

## 配置說明

系統使用 YAML 和 ENV 格式的配置文件，主要包含：

- API 金鑰配置
- 交易參數設定
- 風險控制參數
- 技術指標參數
- Discord 通知設定

## 安裝需求

- Python 3.8+
- 相關套件：
  - binance-futures-connector
  - python-dotenv
  - pandas
  - pyyaml
  - websocket-client
  - discord-webhook
  - numpy
  - pytest

## 使用說明

1. 安裝依賴套件
2. 配置環境變數和設定檔
3. 設定交易參數
4. 啟動交易系統

## 參數說明

### 控制參數 (Control)

| 參數    | 說明             |
| ------- | ---------------- |
| testnet | 是否使用測試網   |
| debug   | 是否開啟調試模式 |

### 幣安 API 參數 (Binance API)

| 參數                                | 說明                         |
| ----------------------------------- | ---------------------------- |
| base_endpoint                       | 主網 REST API 端點           |
| testnet_rest_api_url                | 測試網 REST API 端點         |
| webSocket_base_endpoint             | 主網 WebSocket 端點          |
| webSocket_base_endpoint_for_testnet | 測試網 WebSocket 端點        |
| max_weight_per_minute               | 每分鐘最大權重限制           |
| max_order_per_second                | 每秒最大訂單數               |
| ping_interval                       | WebSocket 心跳間隔（秒）     |
| pong_timeout                        | WebSocket 心跳超時時間（秒） |
| reconnect_attempts                  | 重連嘗試次數                 |
| max_order_per_minute                | 每分鐘最大訂單數             |
| recv_window                         | 接收窗口時間（毫秒）         |

### 指標參數 (Index)

| 參數                       | 說明               |
| -------------------------- | ------------------ |
| bb_length                  | 布林帶週期         |
| bb_mult                    | 布林帶倍數         |
| bb_change_rate             | 布林帶變化率閾值   |
| bb_change_rate_window      | 布林帶變化率窗口   |
| bb_price_threshold         | 布林帶價格閾值     |
| rsi_length                 | RSI 週期           |
| rsi_overbought             | RSI 超買閾值       |
| rsi_oversold               | RSI 超賣閾值       |
| rsi_momentum_offset        | RSI 動量偏移       |
| rsi_reversal_offset        | RSI 反轉偏移       |
| rsi_average_window         | RSI 平均窗口       |
| ma_slow_length             | 慢速均線週期       |
| ma_slope_window            | 均線斜率窗口       |
| ma_slope_trend_threshold   | 均線斜率趨勢閾值   |
| ma_slope_sideway_threshold | 均線斜率盤整閾值   |
| atr_period                 | ATR 週期           |
| average_volume_window      | 平均成交量窗口     |
| average_volume_scale       | 平均成交量縮放比例 |

### 交易參數 (Trading)

| 參數                | 說明                 |
| ------------------- | -------------------- |
| symbol_list         | 交易對列表           |
| leverage            | 槓桿倍數             |
| price_protect       | 是否啟用價格保護     |
| activate_price_rate | 追蹤止損觸發價格比例 |
| trailing_percent    | 追蹤止損百分比（%）  |
| max_loss_percent    | 最大止損百分比       |
| mean_reversion_tp   | 均值回歸止盈比例     |
| mean_reversion_sl   | 均值回歸止損比例     |

### 風險控制參數 (Risk Control)

| 參數                    | 說明                |
| ----------------------- | ------------------- |
| risk_per_trade          | 每筆交易風險比例    |
| max_margin_usage        | 最大保證金使用率    |
| slippage_percent        | 最大滑點百分比（%） |
| max_holding_bars        | 最大持倉 K 棒數     |
| max_daily_trades        | 每日最大交易次數    |
| max_daily_loss          | 每日最大虧損比例    |
| consecutive_losses      | 連續虧損次數限制    |
| cooldown_period         | 冷卻期時間（秒）    |
| min_bandwidth_threshold | 最小布林帶寬閾值    |

## 注意事項

- 請確保 API 金鑰安全
- 建議先在測試網進行測試
- 注意風險控制參數設定
- 定期檢查系統日誌

## 授權條款

本專案依據 [GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html) 授權釋出。  
您可以自由使用、修改與再散布本程式碼，但必須遵守 AGPL v3 授權條款，包括開放原始碼、保留原作者授權聲明，以及若透過網路提供本程式所建置的服務，也需提供對應的原始碼。

## 免責聲明

本專案及其所含之程式碼、文件、說明或相關資源，**僅供學術研究與學習參考用途**，不構成任何形式之投資建議、財務建議、法律建議、或其他專業建議。開發者不擔保本系統適用於任何特定用途、使用情境或市場環境。

系統內所提供之範例參數、策略邏輯與功能模組，僅為教學性示範，**未針對實際市場條件進行調整或驗證，亦未經任何形式之實盤驗證，請勿直接應用於真實交易**。使用者若將本系統應用於模擬或實際操作（包括但不限於數位資產、衍生性商品或其他金融工具之交易），應自行進行充分評估，並**完全承擔其所有風險與後果**。

使用本專案可能涉及以下風險，包括但不限於：

- 資金損失或交易失敗
- 系統錯誤、邏輯缺陷或不預期行為
- 第三方 API 或交易所服務異常、斷線、政策更動
- 資料延遲、計算誤差或風控失效
- 法律或監管風險

開發者不對任何因直接或間接使用、修改、執行或散布本專案而造成之損害或損失負責。使用者應了解並接受相關風險。

**一經下載、複製、修改、執行或散布本專案，即表示您已閱讀並完全理解本免責聲明，並同意完全承擔使用風險與法律責任。**
