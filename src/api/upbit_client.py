from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import asyncio
import pyupbit
from loguru import logger
import time
import jwt
import uuid
import hashlib
from urllib.parse import urlencode
import requests
from datetime import datetime, timedelta


class UpbitClient:
    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key
        self.upbit = pyupbit.Upbit(access_key, secret_key)
        self.server_url = "https://api.upbit.com"
        self._krw_markets_cache = []
        self._krw_markets_last_update = None
        self._cache_duration = timedelta(minutes=30)
        
    def _generate_jwt_token(self, query: Dict = None) -> str:
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query:
            query_string = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
            
        jwt_token = jwt.encode(payload, self.secret_key)
        return f"Bearer {jwt_token}"
        
    def get_balance(self, ticker: str = "KRW") -> Dict[str, Decimal]:
        try:
            balances = self.upbit.get_balances()
            for balance in balances:
                if balance['currency'] == ticker:
                    return {
                        'free': Decimal(balance['balance']),
                        'locked': Decimal(balance['locked']),
                        'total': Decimal(balance['balance']) + Decimal(balance['locked']),
                        'avg_buy_price': Decimal(balance['avg_buy_price'])
                    }
            return {'free': Decimal('0'), 'locked': Decimal('0'), 'total': Decimal('0')}
        except Exception as e:
            logger.error(f"Failed to get balance for {ticker}: {e}")
            raise
            
    def get_ticker_price(self, ticker: str) -> Decimal:
        try:
            price = pyupbit.get_current_price(ticker)
            if price is None:
                raise ValueError(f"Failed to get price for {ticker}")
            return Decimal(str(price))
        except Exception as e:
            logger.error(f"Failed to get ticker price for {ticker}: {e}")
            raise
            
    def get_orderbook(self, ticker: str) -> Dict:
        try:
            orderbook = pyupbit.get_orderbook(ticker)
            if not orderbook:
                raise ValueError(f"Failed to get orderbook for {ticker}")
                
            ob = orderbook[0]
            return {
                'bids': [(Decimal(str(unit['price'])), Decimal(str(unit['size']))) 
                        for unit in ob['orderbook_units']],
                'asks': [(Decimal(str(unit['ask_price'])), Decimal(str(unit['ask_size']))) 
                        for unit in ob['orderbook_units']],
                'timestamp': ob['timestamp']
            }
        except Exception as e:
            logger.error(f"Failed to get orderbook for {ticker}: {e}")
            raise
            
    def place_market_buy_order(self, ticker: str, amount_krw: Decimal) -> Dict:
        try:
            # Upbit market buy orders use KRW amount
            amount_krw = self._round_krw_amount(amount_krw)
            
            if amount_krw < 5000:
                raise ValueError(f"Minimum order amount is 5000 KRW, got {amount_krw}")
                
            order = self.upbit.buy_market_order(ticker, float(amount_krw))
            logger.info(f"Market buy order placed: {order}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to place market buy order: {e}")
            raise
            
    def place_market_sell_order(self, ticker: str, volume: Decimal) -> Dict:
        try:
            # Get market info for volume precision
            market_info = self._get_market_info(ticker)
            volume = self._apply_volume_precision(volume, market_info)
            
            order = self.upbit.sell_market_order(ticker, float(volume))
            logger.info(f"Market sell order placed: {order}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to place market sell order: {e}")
            raise
            
    def place_limit_buy_order(self, ticker: str, price: Decimal, volume: Decimal) -> Dict:
        try:
            market_info = self._get_market_info(ticker)
            price = self._apply_price_precision(price, ticker)
            volume = self._apply_volume_precision(volume, market_info)
            
            order = self.upbit.buy_limit_order(ticker, float(price), float(volume))
            logger.info(f"Limit buy order placed: {order}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to place limit buy order: {e}")
            raise
            
    def place_limit_sell_order(self, ticker: str, price: Decimal, volume: Decimal) -> Dict:
        try:
            market_info = self._get_market_info(ticker)
            price = self._apply_price_precision(price, ticker)
            volume = self._apply_volume_precision(volume, market_info)
            
            order = self.upbit.sell_limit_order(ticker, float(price), float(volume))
            logger.info(f"Limit sell order placed: {order}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to place limit sell order: {e}")
            raise
            
    def get_deposit_address(self, currency: str) -> Dict:
        try:
            headers = {"Authorization": self._generate_jwt_token()}
            
            # Generate deposit address
            generate_url = f"{self.server_url}/v1/deposits/generate_coin_address"
            params = {'currency': currency}
            headers_gen = {"Authorization": self._generate_jwt_token(params)}
            
            res = requests.post(generate_url, params=params, headers=headers_gen)
            if res.status_code != 201 and res.status_code != 200:
                # Try to get existing address
                get_url = f"{self.server_url}/v1/deposits/coin_addresses"
                res = requests.get(get_url, headers=headers)
                
            addresses = res.json()
            for addr in addresses if isinstance(addresses, list) else [addresses]:
                if addr['currency'] == currency:
                    return {
                        'currency': addr['currency'],
                        'deposit_address': addr['deposit_address'],
                        'secondary_address': addr.get('secondary_address')
                    }
                    
            raise ValueError(f"No deposit address found for {currency}")
            
        except Exception as e:
            logger.error(f"Failed to get deposit address for {currency}: {e}")
            raise
            
    def withdraw(self, currency: str, amount: Decimal, address: str, 
                secondary_address: str = None, transaction_type: str = 'default') -> Dict:
        try:
            params = {
                'currency': currency,
                'amount': str(amount),
                'address': address,
                'transaction_type': transaction_type
            }
            
            if secondary_address:
                params['secondary_address'] = secondary_address
                
            headers = {"Authorization": self._generate_jwt_token(params)}
            res = requests.post(
                f"{self.server_url}/v1/withdraws/coin",
                params=params,
                headers=headers
            )
            
            result = res.json()
            logger.info(f"Withdrawal initiated: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to withdraw {currency}: {e}")
            raise
            
    def get_withdraw_history(self, currency: str = None, state: str = None, 
                           limit: int = 100) -> List[Dict]:
        try:
            params = {'limit': limit}
            if currency:
                params['currency'] = currency
            if state:
                params['state'] = state
                
            headers = {"Authorization": self._generate_jwt_token(params)}
            res = requests.get(
                f"{self.server_url}/v1/withdraws",
                params=params,
                headers=headers
            )
            
            return res.json()
            
        except Exception as e:
            logger.error(f"Failed to get withdraw history: {e}")
            raise
            
    def get_deposit_history(self, currency: str = None, state: str = None,
                          limit: int = 100) -> List[Dict]:
        try:
            params = {'limit': limit}
            if currency:
                params['currency'] = currency
            if state:
                params['state'] = state
                
            headers = {"Authorization": self._generate_jwt_token(params)}
            res = requests.get(
                f"{self.server_url}/v1/deposits",
                params=params,
                headers=headers
            )
            
            return res.json()
            
        except Exception as e:
            logger.error(f"Failed to get deposit history: {e}")
            raise
            
    def get_trading_fee(self, market: str) -> Dict:
        try:
            # Upbit has a flat 0.05% fee for both maker and taker
            # Some accounts may have different fee rates
            return {
                'market': market,
                'maker_fee': Decimal('0.0005'),
                'taker_fee': Decimal('0.0005')
            }
        except Exception as e:
            logger.error(f"Failed to get trading fee: {e}")
            raise
            
    def _get_market_info(self, ticker: str) -> Dict:
        try:
            url = f"{self.server_url}/v1/market/all"
            res = requests.get(url)
            markets = res.json()
            
            for market in markets:
                if market['market'] == ticker:
                    return market
                    
            raise ValueError(f"Market info not found for {ticker}")
            
        except Exception as e:
            logger.error(f"Failed to get market info for {ticker}: {e}")
            raise
            
    def _round_krw_amount(self, amount: Decimal) -> Decimal:
        # Upbit requires KRW amounts to be integers
        return Decimal(int(amount))
        
    def _apply_price_precision(self, price: Decimal, ticker: str) -> Decimal:
        # Upbit price precision rules based on price range
        if 'KRW' in ticker:
            if price >= 2000000:
                # Round to nearest 1000
                return Decimal(int(price / 1000) * 1000)
            elif price >= 1000000:
                # Round to nearest 500
                return Decimal(int(price / 500) * 500)
            elif price >= 500000:
                # Round to nearest 100
                return Decimal(int(price / 100) * 100)
            elif price >= 100000:
                # Round to nearest 50
                return Decimal(int(price / 50) * 50)
            elif price >= 10000:
                # Round to nearest 10
                return Decimal(int(price / 10) * 10)
            elif price >= 1000:
                # Round to nearest 5
                return Decimal(int(price / 5) * 5)
            elif price >= 100:
                # Round to nearest 1
                return Decimal(int(price))
            elif price >= 10:
                # Round to 0.1
                return price.quantize(Decimal('0.1'))
            elif price >= 1:
                # Round to 0.01
                return price.quantize(Decimal('0.01'))
            else:
                # Round to 0.001
                return price.quantize(Decimal('0.001'))
        else:
            # BTC markets
            return price.quantize(Decimal('0.00000001'))
            
    def _apply_volume_precision(self, volume: Decimal, market_info: Dict) -> Decimal:
        # Most cryptos use 8 decimal places
        return volume.quantize(Decimal('0.00000001'))
        
    async def get_24hr_stats(self, ticker: str) -> Dict:
        try:
            # Get ticker data
            data = pyupbit.get_ticker(ticker)
            if not data or not isinstance(data, list) or len(data) == 0:
                raise ValueError(f"Failed to get 24hr stats for {ticker}")
                
            stats = data[0]
            return {
                'ticker': stats['market'],
                'trade_price': Decimal(str(stats['trade_price'])),
                'change_rate': Decimal(str(stats['signed_change_rate'])),
                'change_price': Decimal(str(stats['signed_change_price'])),
                'acc_trade_volume_24h': Decimal(str(stats['acc_trade_volume_24h'])),
                'acc_trade_price_24h': Decimal(str(stats['acc_trade_price_24h'])),
                'high_price': Decimal(str(stats['high_price'])),
                'low_price': Decimal(str(stats['low_price'])),
                'prev_closing_price': Decimal(str(stats['prev_closing_price']))
            }
        except Exception as e:
            logger.error(f"Failed to get 24hr stats for {ticker}: {e}")
            raise
            
    def get_krw_markets(self, force_refresh: bool = False) -> List[str]:
        """Get all KRW market symbols from Upbit"""
        now = datetime.now()
        
        # Check cache
        if (not force_refresh and 
            self._krw_markets_cache and 
            self._krw_markets_last_update and 
            now - self._krw_markets_last_update < self._cache_duration):
            return self._krw_markets_cache
            
        try:
            # Get all markets
            markets = pyupbit.get_tickers()
            
            # Filter KRW markets and extract coin symbols
            krw_markets = []
            for market in markets:
                if market.startswith('KRW-'):
                    coin_symbol = market.split('-')[1]
                    krw_markets.append(coin_symbol)
                    
            # Update cache
            self._krw_markets_cache = krw_markets
            self._krw_markets_last_update = now
            
            logger.info(f"Updated KRW markets cache: {len(krw_markets)} markets found")
            return krw_markets
            
        except Exception as e:
            logger.error(f"Failed to get KRW markets: {e}")
            # Return cache if available, otherwise raise
            if self._krw_markets_cache:
                logger.warning("Using cached KRW markets due to API error")
                return self._krw_markets_cache
            raise
            
    def get_tradable_markets_with_binance(self, binance_symbols: set) -> List[str]:
        """Get KRW markets that also have USDT pairs on Binance"""
        try:
            krw_markets = self.get_krw_markets()
            
            # Filter markets that exist on both exchanges
            common_markets = []
            for coin in krw_markets:
                if f"{coin}USDT" in binance_symbols:
                    common_markets.append(coin)
                    
            logger.info(f"Found {len(common_markets)} tradable markets on both Upbit and Binance")
            return common_markets
            
        except Exception as e:
            logger.error(f"Failed to get tradable markets: {e}")
            raise