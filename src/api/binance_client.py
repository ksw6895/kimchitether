from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import asyncio
from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger
import time


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        if testnet:
            self.client = Client(api_key, api_secret, testnet=True)
        else:
            self.client = Client(api_key, api_secret)
            
        self._symbol_info_cache = {}
        self._last_cache_update = 0
        self.CACHE_DURATION = 3600  # 1 hour
        
    def _update_symbol_cache(self):
        if time.time() - self._last_cache_update > self.CACHE_DURATION:
            exchange_info = self.client.get_exchange_info()
            self._symbol_info_cache = {
                symbol['symbol']: symbol 
                for symbol in exchange_info['symbols']
            }
            self._last_cache_update = time.time()
            
    def get_symbol_info(self, symbol: str) -> Dict:
        self._update_symbol_cache()
        return self._symbol_info_cache.get(symbol.upper())
        
    def get_balance(self, asset: str) -> Dict[str, Decimal]:
        try:
            account_info = self.client.get_account()
            for balance in account_info['balances']:
                if balance['asset'] == asset.upper():
                    return {
                        'free': Decimal(balance['free']),
                        'locked': Decimal(balance['locked']),
                        'total': Decimal(balance['free']) + Decimal(balance['locked'])
                    }
            return {'free': Decimal('0'), 'locked': Decimal('0'), 'total': Decimal('0')}
        except BinanceAPIException as e:
            logger.error(f"Failed to get balance for {asset}: {e}")
            raise
            
    def get_ticker_price(self, symbol: str) -> Decimal:
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol.upper())
            return Decimal(ticker['price'])
        except BinanceAPIException as e:
            logger.error(f"Failed to get ticker price for {symbol}: {e}")
            raise
            
    def get_order_book(self, symbol: str, limit: int = 10) -> Dict:
        try:
            order_book = self.client.get_order_book(symbol=symbol.upper(), limit=limit)
            return {
                'bids': [(Decimal(price), Decimal(qty)) for price, qty in order_book['bids']],
                'asks': [(Decimal(price), Decimal(qty)) for price, qty in order_book['asks']],
                'lastUpdateId': order_book['lastUpdateId']
            }
        except BinanceAPIException as e:
            logger.error(f"Failed to get order book for {symbol}: {e}")
            raise
            
    def place_market_order(self, symbol: str, side: str, quantity: Decimal) -> Dict:
        try:
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                raise ValueError(f"Symbol {symbol} not found")
                
            # Apply lot size filter
            lot_size_filter = next(
                (f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), 
                None
            )
            if lot_size_filter:
                step_size = Decimal(lot_size_filter['stepSize'])
                min_qty = Decimal(lot_size_filter['minQty'])
                max_qty = Decimal(lot_size_filter['maxQty'])
                
                # Round quantity to step size
                quantity = self._round_step_size(quantity, step_size)
                
                # Check limits
                if quantity < min_qty:
                    raise ValueError(f"Quantity {quantity} is below minimum {min_qty}")
                if quantity > max_qty:
                    raise ValueError(f"Quantity {quantity} is above maximum {max_qty}")
                    
            order = self.client.create_order(
                symbol=symbol.upper(),
                side=side.upper(),
                type='MARKET',
                quantity=str(quantity)
            )
            
            logger.info(f"Market order placed: {order}")
            return order
            
        except BinanceAPIException as e:
            logger.error(f"Failed to place market order: {e}")
            raise
            
    def place_limit_order(self, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Dict:
        try:
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                raise ValueError(f"Symbol {symbol} not found")
                
            # Apply filters
            quantity = self._apply_lot_size_filter(symbol_info, quantity)
            price = self._apply_price_filter(symbol_info, price)
            
            order = self.client.create_order(
                symbol=symbol.upper(),
                side=side.upper(),
                type='LIMIT',
                timeInForce='GTC',
                quantity=str(quantity),
                price=str(price)
            )
            
            logger.info(f"Limit order placed: {order}")
            return order
            
        except BinanceAPIException as e:
            logger.error(f"Failed to place limit order: {e}")
            raise
            
    def get_deposit_address(self, coin: str, network: str = None) -> Dict:
        try:
            params = {'coin': coin.upper()}
            if network:
                params['network'] = network
                
            result = self.client.get_deposit_address(**params)
            return {
                'address': result['address'],
                'tag': result.get('tag', None),
                'coin': result['coin'],
                'network': network
            }
        except BinanceAPIException as e:
            logger.error(f"Failed to get deposit address for {coin}: {e}")
            raise
            
    def withdraw(self, coin: str, address: str, amount: Decimal, 
                network: str = None, tag: str = None) -> Dict:
        try:
            params = {
                'coin': coin.upper(),
                'address': address,
                'amount': str(amount)
            }
            
            if network:
                params['network'] = network
            if tag:
                params['addressTag'] = tag
                
            result = self.client.withdraw(**params)
            logger.info(f"Withdrawal initiated: {result}")
            return result
            
        except BinanceAPIException as e:
            logger.error(f"Failed to withdraw {coin}: {e}")
            raise
            
    def get_withdraw_history(self, coin: str = None, status: int = None, 
                           limit: int = 100) -> List[Dict]:
        try:
            params = {'limit': limit}
            if coin:
                params['coin'] = coin.upper()
            if status is not None:
                params['status'] = status
                
            history = self.client.get_withdraw_history(**params)
            return history
            
        except BinanceAPIException as e:
            logger.error(f"Failed to get withdraw history: {e}")
            raise
            
    def get_trading_fees(self, symbol: str = None) -> Dict:
        try:
            fees = self.client.get_trade_fee(symbol=symbol.upper() if symbol else None)
            return fees
        except BinanceAPIException as e:
            logger.error(f"Failed to get trading fees: {e}")
            raise
            
    def _round_step_size(self, quantity: Decimal, step_size: Decimal) -> Decimal:
        precision = int(-step_size.as_tuple().exponent)
        return quantity.quantize(Decimal(f'1e-{precision}'))
        
    def _apply_lot_size_filter(self, symbol_info: Dict, quantity: Decimal) -> Decimal:
        lot_size_filter = next(
            (f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), 
            None
        )
        if lot_size_filter:
            step_size = Decimal(lot_size_filter['stepSize'])
            min_qty = Decimal(lot_size_filter['minQty'])
            max_qty = Decimal(lot_size_filter['maxQty'])
            
            quantity = self._round_step_size(quantity, step_size)
            quantity = max(min_qty, min(quantity, max_qty))
            
        return quantity
        
    def _apply_price_filter(self, symbol_info: Dict, price: Decimal) -> Decimal:
        price_filter = next(
            (f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), 
            None
        )
        if price_filter:
            tick_size = Decimal(price_filter['tickSize'])
            min_price = Decimal(price_filter['minPrice'])
            max_price = Decimal(price_filter['maxPrice'])
            
            # Round to tick size
            precision = int(-tick_size.as_tuple().exponent)
            price = price.quantize(Decimal(f'1e-{precision}'))
            
            price = max(min_price, min(price, max_price))
            
        return price
        
    async def get_24hr_stats(self, symbol: str) -> Dict:
        try:
            stats = self.client.get_ticker(symbol=symbol.upper())
            return {
                'symbol': stats['symbol'],
                'priceChange': Decimal(stats['priceChange']),
                'priceChangePercent': Decimal(stats['priceChangePercent']),
                'volume': Decimal(stats['volume']),
                'quoteVolume': Decimal(stats['quoteVolume']),
                'highPrice': Decimal(stats['highPrice']),
                'lowPrice': Decimal(stats['lowPrice']),
                'lastPrice': Decimal(stats['lastPrice'])
            }
        except BinanceAPIException as e:
            logger.error(f"Failed to get 24hr stats for {symbol}: {e}")
            raise