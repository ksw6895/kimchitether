#!/usr/bin/env python3
import asyncio
import json
import os
import signal
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from exchanges.binance_client import BinanceClient
from exchanges.upbit_client import UpbitClient
from utils.price_monitor import PriceMonitor
from utils.trade_executor import TradeExecutor
from utils.risk_manager import RiskManager
from utils.logger import setup_logger, log_system_status, log_arbitrage_opportunity, log_trade


class KimchiTetherBot:
    def __init__(self):
        self.running = False
        self.config = None
        self.binance = None
        self.upbit = None
        self.price_monitor = None
        self.trade_executor = None
        self.risk_manager = None
        
    async def initialize(self):
        setup_logger()
        logger.info("Starting Kimchi Tether Bot...")
        
        load_dotenv()
        
        self.config = self._load_config()
        
        binance_api_key = os.getenv('BINANCE_API_KEY')
        binance_api_secret = os.getenv('BINANCE_API_SECRET')
        upbit_access_key = os.getenv('UPBIT_ACCESS_KEY')
        upbit_secret_key = os.getenv('UPBIT_SECRET_KEY')
        
        if not all([binance_api_key, binance_api_secret, upbit_access_key, upbit_secret_key]):
            logger.error("Missing API credentials. Please check .env file")
            sys.exit(1)
        
        self.binance = BinanceClient(binance_api_key, binance_api_secret)
        self.upbit = UpbitClient(upbit_access_key, upbit_secret_key)
        
        self.price_monitor = PriceMonitor(self.binance, self.upbit, self.config)
        self.trade_executor = TradeExecutor(self.binance, self.upbit, self.config)
        self.risk_manager = RiskManager(self.binance, self.upbit, self.config)
        
        logger.info("Bot initialized successfully")
        
    def _load_config(self) -> dict:
        config_path = Path("config.json")
        if not config_path.exists():
            logger.error("config.json not found")
            sys.exit(1)
            
        with open(config_path, 'r') as f:
            return json.load(f)
    
    async def run(self):
        self.running = True
        logger.info("Bot started. Monitoring prices...")
        
        while self.running:
            try:
                opportunity = await self.price_monitor.monitor_prices()
                
                if opportunity:
                    coin, axis, upbit_price, binance_price = opportunity
                    trade_volume = self.config['trade_volume_usdt']
                    
                    valid, reason = await self.risk_manager.validate_trade(coin, axis, trade_volume)
                    
                    if valid:
                        premium = abs((upbit_price - binance_price) / binance_price)
                        expected_profit = trade_volume * premium * 0.7
                        
                        log_arbitrage_opportunity(coin, axis, premium, expected_profit)
                        
                        trade_id = str(uuid.uuid4())
                        self.risk_manager.open_position(trade_id, coin, axis, trade_volume, binance_price)
                        
                        if axis == 1:
                            result = await self.trade_executor.execute_axis_1(coin, trade_volume)
                        else:
                            result = await self.trade_executor.execute_axis_2(coin, trade_volume)
                        
                        if result['status'] == 'completed':
                            self.risk_manager.close_position(trade_id, binance_price, result.get('profit', 0))
                            log_trade(result)
                        else:
                            logger.error(f"Trade failed: {result}")
                            self.risk_manager.close_position(trade_id, binance_price, -trade_volume * 0.005)
                    else:
                        logger.warning(f"Trade validation failed: {reason}")
                
                if datetime.now().second == 0:
                    risk_metrics = self.risk_manager.get_risk_metrics()
                    daily_stats = self.risk_manager.get_daily_stats()
                    
                    status = {
                        'timestamp': datetime.now().isoformat(),
                        'risk_metrics': risk_metrics,
                        'daily_stats': daily_stats
                    }
                    
                    log_system_status(status)
                
                await asyncio.sleep(self.config['monitoring']['check_interval_seconds'])
                
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(5)
    
    async def shutdown(self):
        logger.info("Shutting down bot...")
        self.running = False
        
        if self.risk_manager:
            await self.risk_manager.emergency_stop()
        
        if self.binance:
            await self.binance.close()
        
        if self.upbit:
            await self.upbit.close()
        
        logger.info("Bot shutdown complete")


async def main():
    bot = KimchiTetherBot()
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        asyncio.create_task(bot.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.initialize()
        await bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())