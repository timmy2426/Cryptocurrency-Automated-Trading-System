from typing import List, Dict, Any
import yaml
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

def check_config_parameters(required_params: List[str]) -> Dict[str, Any]:
    """
    檢查配置參數並返回參數值
    
    Args:
        required_params: 需要檢查的參數名稱列表
        
    Returns:
        Dict[str, Any]: 參數名稱和對應的值，如果參數未設置則值為 None
    """
    def _load_config() -> Dict[str, Any]:
        """加載配置文件"""
        try:
            # 獲取配置文件目錄
            config_dir = os.getenv('CONFIG_DIR')
            if not config_dir:
                # 如果沒有設置環境變量，則嘗試從不同位置查找配置文件
                possible_paths = [
                    # 從當前工作目錄查找
                    os.path.join(os.getcwd(), 'config'),
                    # 從項目根目錄查找
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config'),
                ]
                
                # 檢查所有必要的配置文件
                for path in possible_paths:
                    env_path = os.path.join(path, 'api_keys.env')
                    config_path = os.path.join(path, 'settings.yaml')
                    if os.path.exists(env_path) and os.path.exists(config_path):
                        config_dir = path
                        break
                        
                if not config_dir:
                    raise FileNotFoundError("找不到配置文件目錄")
                    
            # 加載環境變量
            env_path = os.path.join(config_dir, 'api_keys.env')
            load_dotenv(dotenv_path=env_path)
            
            # 加載設置文件
            config_path = os.path.join(config_dir, 'settings.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            return config
            
        except Exception as e:
            logger.error(f"加載配置失敗: {str(e)}")
            raise

    try:
        # 加載配置
        config = _load_config()
        
        # 加載 API 金鑰
        api_keys = {
            'BINANCE_API_KEY': os.getenv('BINANCE_API_KEY'),
            'BINANCE_API_SECRET': os.getenv('BINANCE_API_SECRET'),
            'BINANCE_TESTNET_API_KEY': os.getenv('BINANCE_TESTNET_API_KEY'),
            'BINANCE_TESTNET_API_SECRET': os.getenv('BINANCE_TESTNET_API_SECRET'),
            'DISCORD_WEBHOOK_URL': os.getenv('DISCORD_WEBHOOK_URL')
        }
        
        # 初始化結果字典
        result = {}
        
        # 檢查每個參數
        for param in required_params:
            # 檢查交易配置參數
            if param in ['leverage', 'price_protect', 'activate_price_rate', 'trailing_percent', 'max_loss_percent', 
                        'mean_reversion_tp', 'mean_reversion_sl', 'symbol_list']:
                result[param] = config.get('trading', {}).get(param)
                
            # 檢查控制配置參數
            elif param in ['testnet', 'debug']:
                result[param] = config.get('control', {}).get(param)
                
            # 檢查 API 配置參數
            elif param in ['base_endpoint', 'testnet_rest_api_url', 'webSocket_base_endpoint',
                          'webSocket_base_endpoint_for_testnet', 'max_weight_per_minute',
                          'max_order_per_second', 'ping_interval', 'pong_timeout',
                          'reconnect_attempts', 'max_order_per_minute', 'recv_window']:
                result[param] = config.get('binance_api', {}).get(param)
                
            # 檢查指標配置參數
            elif param in ['bb_length', 'bb_mult', 'bb_change_rate', 'bb_change_rate_window', 'bb_price_threshold', 'rsi_length', 
                           'rsi_overbought', 'rsi_oversold', 'rsi_momentum_offset', 'rsi_reversal_offset', 'rsi_average_window', 
                           'ma_slow_length', 'ma_slope_window', 'ma_slope_threshold', 
                           'atr_period', 'average_volume_window', 'average_volume_scale']:
                result[param] = config.get('index', {}).get(param)
                
            # 檢查風險控制參數
            elif param in ['risk_per_trade', 'max_margin_usage', 'max_daily_loss', 
                          'max_daily_trades', 'slippage_percent', 'max_holding_bars',
                          'consecutive_losses', 'cooldown_period', 'min_bandwidth_threshold']:
                result[param] = config.get('risk_control', {}).get(param)
                
            # 檢查 API 金鑰
            elif param in api_keys:
                result[param] = api_keys.get(param)
                
            else:
                result[param] = None
                
        return result
        
    except Exception as e:
        logger.error(f"檢查配置參數失敗: {str(e)}")
        raise