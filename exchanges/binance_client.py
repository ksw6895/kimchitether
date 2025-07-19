import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from typing import Dict, Optional, List
import asyncio
import aiohttp
from loguru import logger


class BinanceClient:
    BASE_URL = "https://api.binance.com"
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = None
        
    def _generate_signature(self, params: Dict) -> str:
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_headers(self) -> Dict:
        return {
            'X-MBX-APIKEY': self.api_key
        }
    
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, signed: bool = False) -> Dict:
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        url = f"{self.BASE_URL}{endpoint}"
        
        if signed:
            if params is None:
                params = {}
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        headers = self._get_headers() if signed else {}
        
        try:
            async with self.session.request(method, url, params=params, headers=headers) as response:
                data = await response.json()
                if response.status != 200:
                    logger.error(f"Binance API error: {data}")
                    raise Exception(f"API error: {data.get('msg', 'Unknown error')}")
                return data
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
    
    async def get_price(self, symbol: str) -> float:
        endpoint = "/api/v3/ticker/price"
        params = {"symbol": f"{symbol}USDT"}
        data = await self._request("GET", endpoint, params)
        return float(data['price'])
    
    async def get_balance(self, asset: str) -> Dict:
        endpoint = "/api/v3/account"
        data = await self._request("GET", endpoint, signed=True)
        
        for balance in data['balances']:
            if balance['asset'] == asset:
                return {
                    'free': float(balance['free']),
                    'locked': float(balance['locked']),
                    'total': float(balance['free']) + float(balance['locked'])
                }
        return {'free': 0.0, 'locked': 0.0, 'total': 0.0}
    
    async def create_market_order(self, symbol: str, side: str, quantity: Optional[float] = None, quote_qty: Optional[float] = None) -> Dict:
        endpoint = "/api/v3/order"
        params = {
            "symbol": f"{symbol}USDT",
            "side": side.upper(),
            "type": "MARKET"
        }
        
        if quantity:
            params["quantity"] = quantity
        elif quote_qty:
            params["quoteOrderQty"] = quote_qty
        else:
            raise ValueError("Either quantity or quote_qty must be specified")
        
        result = await self._request("POST", endpoint, params, signed=True)
        logger.info(f"Market order created: {result}")
        return result
    
    async def get_deposit_address(self, coin: str, network: Optional[str] = None) -> Dict:
        endpoint = "/sapi/v1/capital/deposit/address"
        params = {"coin": coin}
        if network:
            params["network"] = network
            
        data = await self._request("GET", endpoint, params, signed=True)
        return {
            'address': data['address'],
            'tag': data.get('tag', ''),
            'coin': data['coin']
        }
    
    async def withdraw(self, coin: str, address: str, amount: float, network: Optional[str] = None, tag: Optional[str] = None) -> Dict:
        endpoint = "/sapi/v1/capital/withdraw/apply"
        params = {
            "coin": coin,
            "address": address,
            "amount": amount
        }
        
        if network:
            params["network"] = network
        if tag:
            params["addressTag"] = tag
            
        result = await self._request("POST", endpoint, params, signed=True)
        logger.info(f"Withdrawal initiated: {result}")
        return result
    
    async def get_deposit_history(self, coin: Optional[str] = None, status: Optional[int] = None) -> List[Dict]:
        endpoint = "/sapi/v1/capital/deposit/hisrec"
        params = {}
        
        if coin:
            params["coin"] = coin
        if status is not None:
            params["status"] = status
            
        data = await self._request("GET", endpoint, params, signed=True)
        return data
    
    async def check_deposit_status(self, txid: str, coin: str) -> Optional[Dict]:
        deposits = await self.get_deposit_history(coin=coin, status=1)
        
        for deposit in deposits:
            if deposit.get('txId') == txid:
                return deposit
        return None
    
    async def close(self):
        if self.session:
            await self.session.close()