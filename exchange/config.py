import yaml
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

def load_config():
    """加載配置"""
    try:
        # 加載環境變量
        load_dotenv(dotenv_path='config/api_keys.env')
        
        # 加載設置文件
        with open('config/settings.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        # 檢查必要的配置項
        required_keys = ['binance_api', 'control']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"配置文件中缺少必要的配置項: {key}")
                
        # 檢查 API 密鑰
        if config['control']['testnet']:
            api_key = os.getenv('BINANCE_TESTNET_API_KEY')
            api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
        else:
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_API_SECRET')
            
        if not api_key or not api_secret:
            raise ValueError("請在 config/api_keys.env 文件中設置 API 密鑰")
            
        return config
        
    except Exception as e:
        logger.error(f"加載配置失敗: {str(e)}")
        raise 