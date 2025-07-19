import jwt
import time
import uuid
import hashlib
import requests
from urllib.parse import urlencode
from typing import Dict, Optional, List
import asyncio
import aiohttp
from loguru import logger


class UpbitClient:
    BASE_URL = "https://api.upbit.com"
    
    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session = None
        
    def _generate_jwt_token(self, params: Optional[Dict] = None) -> str:
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if params:
            query_string = urlencode(params).encode()
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
            
        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return jwt_token
    
    def _get_headers(self, jwt_token: str) -> Dict:
        return {
            'Authorization': f'Bearer {jwt_token}'
        }
    
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, need_auth: bool = True) -> Dict:
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {}
        if need_auth:
            jwt_token = self._generate_jwt_token(params)
            headers = self._get_headers(jwt_token)
        
        try:
            if method == "GET":
                async with self.session.get(url, params=params, headers=headers) as response:
                    data = await response.json()
            else:
                async with self.session.request(method, url, json=params, headers=headers) as response:
                    data = await response.json()
                    
            if 'error' in data:
                logger.error(f"Upbit API error: {data}")
                raise Exception(f"API error: {data['error']['message']}")
            return data
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
    
    async def get_price(self, symbol: str) -> float:
        endpoint = "/v1/ticker"
        params = {"markets": f"USDT-{symbol}"}
        data = await self._request("GET", endpoint, params, need_auth=False)
        
        if data and len(data) > 0:
            return float(data[0]['trade_price'])
        raise Exception(f"Failed to get price for {symbol}")
    
    async def get_all_markets(self) -> List[str]:
        endpoint = "/v1/market/all"
        data = await self._request("GET", endpoint, params={"isDetails": "false"}, need_auth=False)
        
        usdt_markets = []
        for market in data:
            if market['market'].startswith('USDT-'):
                coin = market['market'].split('-')[1]
                usdt_markets.append(coin)
        
        return usdt_markets
    
    async def get_balance(self, currency: str) -> Dict:
        endpoint = "/v1/accounts"
        accounts = await self._request("GET", endpoint)
        
        for account in accounts:
            if account['currency'] == currency:
                return {
                    'free': float(account['balance']),
                    'locked': float(account['locked']),
                    'total': float(account['balance']) + float(account['locked'])
                }
        return {'free': 0.0, 'locked': 0.0, 'total': 0.0}
    
    async def create_market_order(self, symbol: str, side: str, volume: Optional[float] = None, price: Optional[float] = None) -> Dict:
        endpoint = "/v1/orders"
        
        if side.upper() == "BUY":
            if not price:
                raise ValueError("Price (USDT amount) is required for market buy orders")
            params = {
                "market": f"USDT-{symbol}",
                "side": "bid",
                "ord_type": "price",
                "price": str(price)
            }
        else:
            if not volume:
                raise ValueError("Volume is required for market sell orders")
            params = {
                "market": f"USDT-{symbol}",
                "side": "ask",
                "ord_type": "market",
                "volume": str(volume)
            }
        
        result = await self._request("POST", endpoint, params)
        logger.info(f"Market order created: {result}")
        return result
    
    async def get_deposit_address(self, currency: str) -> Dict:
        endpoint = "/v1/deposits/generate_coin_address"
        params = {"currency": currency}
        
        try:
            data = await self._request("POST", endpoint, params)
            return {
                'address': data['deposit_address'],
                'secondary_address': data.get('secondary_address', ''),
                'currency': currency
            }
        except Exception as e:
            endpoint = "/v1/deposits/coin_addresses"
            addresses = await self._request("GET", endpoint)
            
            for addr in addresses:
                if addr['currency'] == currency:
                    return {
                        'address': addr['deposit_address'],
                        'secondary_address': addr.get('secondary_address', ''),
                        'currency': currency
                    }
            raise Exception(f"No deposit address found for {currency}")
    
    async def withdraw(self, currency: str, amount: float, address: str, secondary_address: Optional[str] = None) -> Dict:
        endpoint = "/v1/withdraws/coin"
        params = {
            "currency": currency,
            "amount": str(amount),
            "address": address
        }
        
        if secondary_address:
            params["secondary_address"] = secondary_address
            
        result = await self._request("POST", endpoint, params)
        logger.info(f"Withdrawal initiated: {result}")
        return result
    
    async def get_deposit_history(self, currency: Optional[str] = None, state: Optional[str] = None) -> List[Dict]:
        endpoint = "/v1/deposits"
        params = {}
        
        if currency:
            params["currency"] = currency
        if state:
            params["state"] = state
            
        data = await self._request("GET", endpoint, params)
        return data
    
    async def check_deposit_status(self, txid: str, currency: str) -> Optional[Dict]:
        deposits = await self.get_deposit_history(currency=currency)
        
        for deposit in deposits:
            if deposit.get('txid') == txid:
                return deposit
        return None
    
    async def close(self):
        if self.session:
            await self.session.close()