from engine import BacktestEngine

class Backtest:
  # 回測主程式
  def __init__(self):
    
    # 回測參數設定
    self.config = {
      "start_date": "2024-01-01",
      "end_date": "2024-12-31",
      "symbol": ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'BNBUSDT', 'SOLUSDT', 'DOGEUSDT', 'TRXUSDT', 'ADAUSDT'],
      "leverage": 5,
      "slippage": 0.0005,
      "fee": 0.0005,
      "initial_balance": 10000,
      "risk_free_rate": 0.025,
      "force_update": False,
    }
    
    # 初始化回測引擎
    self.engine = BacktestEngine(self.config)
    
  def run(self):
    self.engine.run()

if __name__ == "__main__":
  backtest = Backtest()
  backtest.run()
