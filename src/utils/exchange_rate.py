from typing import Dict, Optional
from decimal import Decimal
import requests
from loguru import logger
import time
from datetime import datetime, timedelta


class ExchangeRateProvider:
    def __init__(self, cache_duration: int = 300):  # 5 minutes cache
        self.cache_duration = cache_duration
        self._cache = {}
        self._last_update = {}
        
    def get_usd_krw_rate(self) -> Optional[Decimal]:
        cache_key = "USD_KRW"
        
        # Check cache
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
            
        try:
            # Primary: Use Dunamu API (Upbit's parent company)
            rate = self._get_dunamu_rate()
            if rate:
                self._update_cache(cache_key, rate)
                return rate
                
            # Fallback: Use exchangerate-api
            rate = self._get_exchangerate_api_rate()
            if rate:
                self._update_cache(cache_key, rate)
                return rate
                
            # Second fallback: Use fixer.io free tier
            rate = self._get_fixer_rate()
            if rate:
                self._update_cache(cache_key, rate)
                return rate
                
            # If all fail, check if we have a recent cached rate (within 1 hour)
            if cache_key in self._cache:
                elapsed = time.time() - self._last_update.get(cache_key, 0)
                if elapsed < 3600:  # 1 hour
                    logger.warning(f"Using stale exchange rate from cache (age: {elapsed:.0f}s)")
                    return self._cache[cache_key]
                    
            # No reliable exchange rate available
            logger.error("Failed to get exchange rate from all sources. Trading should be halted.")
            return None
                
        except Exception as e:
            logger.error(f"Critical error getting exchange rate: {e}")
            # Check for recent cache
            if cache_key in self._cache:
                elapsed = time.time() - self._last_update.get(cache_key, 0)
                if elapsed < 3600:  # 1 hour
                    logger.warning(f"Using cached rate after error (age: {elapsed:.0f}s)")
                    return self._cache[cache_key]
            return None
            
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache or key not in self._last_update:
            return False
            
        elapsed = time.time() - self._last_update[key]
        return elapsed < self.cache_duration
        
    def _update_cache(self, key: str, value: Decimal):
        self._cache[key] = value
        self._last_update[key] = time.time()
        
    def _get_dunamu_rate(self) -> Optional[Decimal]:
        try:
            url = "https://quotation-api-cdn.dunamu.com/v1/forex/recent"
            params = {"codes": "FRX.KRWUSD"}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    # Dunamu provides KRW per USD
                    rate = Decimal(str(data[0]['basePrice']))
                    logger.info(f"Got exchange rate from Dunamu: {rate}")
                    return rate
                    
        except Exception as e:
            logger.debug(f"Dunamu API failed: {e}")
            
        return None
        
    def _get_exchangerate_api_rate(self) -> Optional[Decimal]:
        try:
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if 'rates' in data and 'KRW' in data['rates']:
                    rate = Decimal(str(data['rates']['KRW']))
                    logger.info(f"Got exchange rate from exchangerate-api: {rate}")
                    return rate
                    
        except Exception as e:
            logger.debug(f"Exchangerate-api failed: {e}")
            
        return None
        
    def _get_fixer_rate(self) -> Optional[Decimal]:
        try:
            # Free tier allows 100 requests per month
            url = "https://api.fixer.io/latest"
            params = {
                "base": "USD",
                "symbols": "KRW"
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if 'rates' in data and 'KRW' in data['rates']:
                    rate = Decimal(str(data['rates']['KRW']))
                    logger.info(f"Got exchange rate from fixer.io: {rate}")
                    return rate
                    
        except Exception as e:
            logger.debug(f"Fixer.io API failed: {e}")
            
        return None
        
    def convert_usd_to_krw(self, usd_amount: Decimal) -> Optional[Decimal]:
        rate = self.get_usd_krw_rate()
        if rate is None:
            return None
        return usd_amount * rate
        
    def convert_krw_to_usd(self, krw_amount: Decimal) -> Optional[Decimal]:
        rate = self.get_usd_krw_rate()
        if rate is None:
            return None
        return krw_amount / rate
        
    def get_exchange_rate_info(self) -> Dict:
        rate = self.get_usd_krw_rate()
        if rate is None:
            return {
                'usd_krw': None,
                'krw_usd': None,
                'last_update': datetime.now().isoformat(),
                'cache_valid': False,
                'error': 'Failed to get exchange rate'
            }
        return {
            'usd_krw': rate,
            'krw_usd': 1 / rate,
            'last_update': datetime.now().isoformat(),
            'cache_valid': self._is_cache_valid("USD_KRW")
        }