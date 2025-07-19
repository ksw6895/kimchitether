import asyncio
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from loguru import logger
from exchanges.binance_client import BinanceClient
from exchanges.upbit_client import UpbitClient


class PriceMonitor:
    def __init__(self, binance_client: BinanceClient, upbit_client: UpbitClient, config: Dict):
        self.binance = binance_client
        self.upbit = upbit_client
        self.config = config
        self.price_cache = {}
        self.last_update = {}
        self.available_coins = []
        self.last_market_update = 0
        
    async def update_available_coins(self):
        try:
            current_time = time.time()
            if current_time - self.last_market_update > 3600:
                self.available_coins = await self.upbit.get_all_markets()
                self.last_market_update = current_time
                logger.info(f"Updated available coins: {len(self.available_coins)} coins found")
        except Exception as e:
            logger.error(f"Failed to update available coins: {e}")
            
    async def get_prices(self, coin: str) -> Tuple[Optional[float], Optional[float]]:
        try:
            tasks = [
                self.binance.get_price(coin),
                self.upbit.get_price(coin)
            ]
            
            binance_price, upbit_price = await asyncio.gather(*tasks, return_exceptions=True)
            
            if isinstance(binance_price, Exception):
                logger.error(f"Binance price error for {coin}: {binance_price}")
                binance_price = None
            
            if isinstance(upbit_price, Exception):
                logger.error(f"Upbit price error for {coin}: {upbit_price}")
                upbit_price = None
            
            current_time = time.time()
            self.price_cache[coin] = {
                'binance': binance_price,
                'upbit': upbit_price,
                'timestamp': current_time
            }
            self.last_update[coin] = current_time
            
            return binance_price, upbit_price
            
        except Exception as e:
            logger.error(f"Failed to get prices for {coin}: {e}")
            return None, None
    
    def calculate_premium(self, upbit_price: float, binance_price: float) -> float:
        return (upbit_price - binance_price) / binance_price
    
    def check_axis_1_trigger(self, coin: str, upbit_price: float, binance_price: float) -> bool:
        premium = self.calculate_premium(binance_price, upbit_price)
        
        fee_total = (
            self.config['fee_data']['upbit']['trade'] +
            self.config['fee_data']['binance']['trade'] +
            (self.config['fee_data']['upbit']['withdraw'].get(coin, 0) / binance_price)
        )
        
        threshold = fee_total + self.config['a_margin']['default']
        
        if premium > threshold:
            logger.info(f"Axis 1 trigger for {coin}: premium={premium:.4f}, threshold={threshold:.4f}")
            return True
        
        return False
    
    def check_axis_2_trigger(self, coin: str, upbit_price: float, binance_price: float) -> bool:
        premium = self.calculate_premium(upbit_price, binance_price)
        
        fee_total = (
            self.config['fee_data']['upbit']['trade'] +
            self.config['fee_data']['binance']['trade'] +
            (self.config['fee_data']['binance']['withdraw'].get(coin, 0) / binance_price)
        )
        
        threshold = fee_total + self.config['a_margin']['default']
        
        if premium > threshold:
            logger.info(f"Axis 2 trigger for {coin}: premium={premium:.4f}, threshold={threshold:.4f}")
            return True
        
        return False
    
    async def monitor_prices(self) -> Optional[Tuple[str, int, float, float]]:
        await self.update_available_coins()
        
        if not self.available_coins:
            logger.warning("No available coins to monitor")
            return None
        
        for coin in self.available_coins:
            binance_price, upbit_price = await self.get_prices(coin)
            
            if binance_price and upbit_price:
                if self.check_axis_1_trigger(coin, upbit_price, binance_price):
                    return (coin, 1, upbit_price, binance_price)
                
                if self.check_axis_2_trigger(coin, upbit_price, binance_price):
                    return (coin, 2, upbit_price, binance_price)
                
                premium = abs(self.calculate_premium(upbit_price, binance_price))
                if premium > 0.001:
                    logger.debug(f"{coin}: Binance=${binance_price:.4f}, Upbit=${upbit_price:.4f}, Premium={premium:.2%}")
        
        return None
    
    def get_cached_price(self, coin: str, exchange: str) -> Optional[float]:
        if coin in self.price_cache:
            current_time = time.time()
            if current_time - self.price_cache[coin]['timestamp'] < self.config['monitoring']['max_price_age_seconds']:
                return self.price_cache[coin].get(exchange)
        return None