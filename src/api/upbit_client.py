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
        self._api_access_verified = False
        
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
            
            # Enhanced error logging for debugging
            if orderbook is None:
                logger.error(f"pyupbit.get_orderbook returned None for {ticker} - likely API access issue")
                raise ValueError(f"No orderbook data returned for {ticker} - check API access and IP whitelist")
            
            # Handle both dict (single ticker) and list (multiple tickers) responses
            if isinstance(orderbook, dict):
                # Single ticker response - use directly
                ob = orderbook
                logger.debug(f"Orderbook for {ticker} returned as dict")
            elif isinstance(orderbook, list):
                # Multiple ticker response - get first element
                if len(orderbook) == 0:
                    logger.error(f"Empty orderbook list for {ticker}")
                    raise ValueError(f"Empty orderbook data for {ticker}")
                ob = orderbook[0]
                logger.debug(f"Orderbook for {ticker} returned as list with {len(orderbook)} items")
            else:
                logger.error(f"Unexpected orderbook type for {ticker}: {type(orderbook)}")
                raise ValueError(f"Invalid orderbook format for {ticker} - expected dict or list, got {type(orderbook).__name__}")
            
            # Check if it's an error response
            if 'error' in ob:
                error_code = ob['error'].get('name', 'Unknown')
                error_msg = ob['error'].get('message', 'No message')
                logger.error(f"Upbit API error for {ticker}: {error_code} - {error_msg}")
                if 'UNAUTHORIZED' in error_code or 'jwt' in error_msg.lower():
                    raise ValueError(f"Authentication error for {ticker}: {error_msg} - Check API keys and IP whitelist")
                else:
                    raise ValueError(f"API error for {ticker}: {error_code} - {error_msg}")
            
            # Extract orderbook data
            orderbook_units = ob.get('orderbook_units', [])
            if not orderbook_units:
                logger.error(f"No orderbook units for {ticker}, response: {ob}")
                raise ValueError(f"No orderbook units for {ticker}")
                
            bids = []
            asks = []
            
            for unit in orderbook_units:
                # Bid side
                bid_price = unit.get('bid_price')
                bid_size = unit.get('bid_size')
                if bid_price and bid_size:
                    bids.append((Decimal(str(bid_price)), Decimal(str(bid_size))))
                    
                # Ask side
                ask_price = unit.get('ask_price')
                ask_size = unit.get('ask_size')
                if ask_price and ask_size:
                    asks.append((Decimal(str(ask_price)), Decimal(str(ask_size))))
                    
            return {
                'bids': bids,
                'asks': asks,
                'timestamp': ob.get('timestamp', 0),
                'orderbook_units': orderbook_units  # Keep original for compatibility
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
            
    def verify_api_access(self) -> Tuple[bool, str]:
        """Verify API access and permissions
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Test 1: Check if we can get account info
            logger.info("Verifying Upbit API access...")
            
            # Try to get balance (requires authentication)
            try:
                balances = self.upbit.get_balances()
                if balances is None:
                    return False, "API returned None for balance check - verify API keys"
                logger.info("✓ Balance API access verified")
            except Exception as e:
                error_msg = str(e)
                if 'jwt' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                    return False, f"Authentication failed: {error_msg} - Check API keys and secret"
                else:
                    return False, f"Balance API error: {error_msg}"
            
            # Test 2: Check orderbook access (public API but may be IP restricted)
            test_ticker = "KRW-BTC"
            try:
                orderbook = pyupbit.get_orderbook(test_ticker)
                if orderbook is None:
                    return False, "Orderbook API returned None - IP may not be whitelisted"
                    
                # Handle both dict and list responses
                if isinstance(orderbook, dict):
                    # Single ticker response
                    if 'error' in orderbook:
                        error_info = orderbook['error']
                        return False, f"Orderbook API error: {error_info.get('message', 'Unknown error')} - Add your IP to Upbit whitelist"
                    if 'orderbook_units' not in orderbook:
                        return False, f"Invalid orderbook structure - missing orderbook_units"
                elif isinstance(orderbook, list):
                    # Multiple ticker response
                    if len(orderbook) == 0:
                        return False, f"Empty orderbook list - API may be restricted"
                    if 'error' in orderbook[0]:
                        error_info = orderbook[0]['error']
                        return False, f"Orderbook API error: {error_info.get('message', 'Unknown error')} - Add your IP to Upbit whitelist"
                else:
                    return False, f"Invalid orderbook format: {type(orderbook)} - API may be restricted"
                    
                logger.info("✓ Orderbook API access verified")
                
            except Exception as e:
                return False, f"Orderbook API error: {str(e)} - Check IP whitelist"
            
            # Test 3: Try to get markets list
            try:
                markets = pyupbit.get_tickers()
                if not markets:
                    return False, "Cannot fetch market list - API access may be restricted"
                logger.info("✓ Market list API access verified")
            except Exception as e:
                return False, f"Market API error: {str(e)}"
            
            self._api_access_verified = True
            return True, "All API access verified successfully"
            
        except Exception as e:
            logger.error(f"API verification failed: {e}")
            return False, f"Verification error: {str(e)}"