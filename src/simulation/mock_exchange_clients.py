"""Mock exchange clients for paper trading simulation"""
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
import asyncio
from loguru import logger

from src.simulation.virtual_balance_manager import VirtualBalanceManager, SimulatedTrade


class MockBinanceClient:
    """Mock Binance client for paper trading"""
    
    def __init__(self, real_client, balance_manager: VirtualBalanceManager):
        """
        Initialize mock client
        
        Args:
            real_client: Real Binance client (for price data)
            balance_manager: Virtual balance manager
        """
        self.real_client = real_client
        self.balance_manager = balance_manager
        self.exchange_name = "binance"
        self.trading_fee = Decimal("0.001")  # 0.1% default fee
        
    def get_balance(self, asset: str) -> Dict[str, Decimal]:
        """Get virtual balance for an asset"""
        balance = self.balance_manager.get_balance(self.exchange_name, asset)
        if balance:
            return {
                "free": balance.available,
                "locked": balance.locked,
                "total": balance.total
            }
        return {"free": Decimal("0"), "locked": Decimal("0"), "total": Decimal("0")}
        
    def get_ticker_price(self, symbol: str) -> Optional[Decimal]:
        """Get real ticker price from actual API"""
        return self.real_client.get_ticker_price(symbol)
        
    def get_order_book(self, symbol: str, limit: int = 5) -> Dict:
        """Get real order book from actual API"""
        return self.real_client.get_order_book(symbol, limit)
        
    def place_market_order(self, symbol: str, side: str, quantity: Decimal) -> Dict:
        """Simulate market order"""
        # Get current price
        price = self.get_ticker_price(symbol)
        if not price:
            raise Exception(f"Could not get price for {symbol}")
            
        # Get order book for slippage simulation
        order_book = self.get_order_book(symbol, limit=10)
        
        # Calculate execution price with slippage
        if side.upper() == "BUY":
            # For buy orders, use ask prices
            asks = order_book.get("asks", [])
            exec_price = self._calculate_execution_price(asks, quantity, price)
        else:
            # For sell orders, use bid prices
            bids = order_book.get("bids", [])
            exec_price = self._calculate_execution_price(bids, quantity, price)
            
        # Execute simulated trade
        trade = self.balance_manager.execute_trade(
            exchange=self.exchange_name,
            symbol=symbol,
            side=side,
            price=exec_price,
            quantity=quantity,
            fee_rate=self.trading_fee,
            trade_type="market"
        )
        
        if trade:
            return {
                "orderId": trade.trade_id,
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "executedQty": str(quantity),
                "cummulativeQuoteQty": str(trade.total_cost),
                "status": "FILLED",
                "fills": [{
                    "price": str(exec_price),
                    "qty": str(quantity),
                    "commission": str(trade.fee),
                    "commissionAsset": trade.fee_asset
                }]
            }
        else:
            raise Exception("Failed to execute simulated trade")
            
    def place_limit_order(self, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Dict:
        """Simulate limit order (instant fill for simplicity)"""
        # For simulation, we'll assume limit orders fill immediately at the specified price
        trade = self.balance_manager.execute_trade(
            exchange=self.exchange_name,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            fee_rate=self.trading_fee,
            trade_type="limit"
        )
        
        if trade:
            return {
                "orderId": trade.trade_id,
                "symbol": symbol,
                "side": side,
                "type": "LIMIT",
                "price": str(price),
                "executedQty": str(quantity),
                "status": "FILLED"
            }
        else:
            raise Exception("Failed to execute simulated trade")
            
    def get_deposit_address(self, coin: str, network: str = None) -> Dict:
        """Return mock deposit address"""
        return {
            "address": f"MOCK_{self.exchange_name}_{coin}_ADDRESS",
            "tag": None,
            "coin": coin,
            "network": network or "MOCK_NETWORK"
        }
        
    def withdraw(self, coin: str, address: str, amount: Decimal, 
                      network: str = None, tag: str = None) -> Dict:
        """Simulate withdrawal (transfer)"""
        # Determine destination exchange from address
        if "upbit" in address.lower():
            to_exchange = "upbit"
        else:
            to_exchange = "external"
            
        # Use a fixed network fee for simulation
        network_fees = {
            "BTC": Decimal("0.0005"),
            "ETH": Decimal("0.005"),
            "XRP": Decimal("0.25"),
            "USDT": Decimal("1.0")
        }
        network_fee = network_fees.get(coin, Decimal("1.0"))
        
        transfer = self.balance_manager.simulate_transfer(
            asset=coin,
            amount=amount,
            from_exchange=self.exchange_name,
            to_exchange=to_exchange,
            network_fee=network_fee
        )
        
        if transfer:
            return {
                "id": transfer.transfer_id,
                "amount": str(amount),
                "transactionFee": str(network_fee),
                "status": 1  # Success
            }
        else:
            raise Exception("Failed to simulate withdrawal")
            
    def get_withdraw_history(self, coin: str = None, limit: int = 10) -> List[Dict]:
        """Get simulated withdrawal history"""
        transfers = self.balance_manager.get_transfer_history(limit=limit)
        history = []
        
        for transfer in transfers:
            if transfer.from_exchange == self.exchange_name:
                if coin and transfer.asset != coin:
                    continue
                    
                history.append({
                    "id": transfer.transfer_id,
                    "amount": str(transfer.amount),
                    "transactionFee": str(transfer.fee),
                    "coin": transfer.asset,
                    "status": 6 if transfer.status == "completed" else 2,  # 6=Success, 2=Processing
                    "address": f"MOCK_{transfer.to_exchange}_ADDRESS",
                    "applyTime": transfer.timestamp.isoformat()
                })
                
        return history
        
    def get_trading_fees(self) -> List[Dict]:
        """Get trading fee structure"""
        return [{
            "symbol": "BTCUSDT",
            "makerCommission": str(self.trading_fee * 1000),  # Convert to basis points
            "takerCommission": str(self.trading_fee * 1000)
        }]
        
    async def get_24hr_stats(self, symbol: str) -> Dict:
        """Get real 24hr stats from actual API"""
        return await self.real_client.get_24hr_stats(symbol)
        
    def get_usdt_markets(self) -> List[str]:
        """Get real USDT markets from actual API"""
        return self.real_client.get_usdt_markets()
        
    def withdraw(self, coin: str, address: str, amount: Decimal, 
                network: str = None, tag: str = None) -> Dict:
        """Simulate withdrawal (instant for paper trading)"""
        # In paper trading, we'll handle the actual transfer in the strategy
        return {
            "id": f"MOCK_WITHDRAWAL_{self.exchange_name}_{datetime.now().timestamp()}",
            "coin": coin,
            "amount": str(amount),
            "address": address,
            "network": network,
            "status": "processing"
        }
        
    def get_deposit_address(self, coin: str, network: str = None) -> Dict:
        """Get mock deposit address"""
        return {
            "address": f"MOCK_{self.exchange_name}_{coin}_ADDRESS",
            "tag": f"MOCK_TAG_{coin}" if coin in ["XRP", "XLM"] else None,
            "coin": coin,
            "network": network
        }
        
    def _calculate_execution_price(self, orders: List[List], quantity: Decimal, 
                                  default_price: Decimal) -> Decimal:
        """Calculate execution price considering order book depth"""
        if not orders:
            return default_price
            
        remaining_qty = quantity
        total_cost = Decimal("0")
        
        for order in orders:
            price = Decimal(order[0])
            available_qty = Decimal(order[1])
            
            if remaining_qty <= available_qty:
                total_cost += remaining_qty * price
                break
            else:
                total_cost += available_qty * price
                remaining_qty -= available_qty
                
        if remaining_qty > 0:
            # Not enough liquidity, use last price for remaining
            total_cost += remaining_qty * default_price
            
        return total_cost / quantity


class MockUpbitClient:
    """Mock Upbit client for paper trading"""
    
    def __init__(self, real_client, balance_manager: VirtualBalanceManager):
        """
        Initialize mock client
        
        Args:
            real_client: Real Upbit client (for price data)
            balance_manager: Virtual balance manager
        """
        self.real_client = real_client
        self.balance_manager = balance_manager
        self.exchange_name = "upbit"
        self.trading_fee = Decimal("0.0005")  # 0.05% fee
        
    def get_balance(self, ticker: str = None) -> Dict[str, Decimal]:
        """Get virtual balance for a specific ticker"""
        if ticker:
            balance = self.balance_manager.get_balance(self.exchange_name, ticker)
            if balance:
                return {
                    "free": balance.available,
                    "locked": balance.locked,
                    "total": balance.total
                }
        return {"free": Decimal("0"), "locked": Decimal("0"), "total": Decimal("0")}
        
    def get_ticker_price(self, ticker: str) -> Optional[Decimal]:
        """Get real ticker price from actual API"""
        return self.real_client.get_ticker_price(ticker)
        
    def get_orderbook(self, ticker: str) -> Dict:
        """Get real order book from actual API"""
        return self.real_client.get_orderbook(ticker)
        
    def place_market_buy_order(self, ticker: str, amount_krw: Decimal) -> Dict:
        """Simulate market buy order with KRW amount"""
        # Get current price
        price = self.get_ticker_price(ticker)
        if not price:
            raise Exception(f"Could not get price for {ticker}")
            
        # Calculate quantity
        quantity = amount_krw / price
        
        # Get order book for slippage
        order_book = self.get_orderbook(ticker)
        asks = order_book.get("orderbook_units", [])
        
        # Calculate execution price
        exec_price = self._calculate_execution_price_krw(
            asks, amount_krw, price, is_buy=True
        )
        
        # Recalculate actual quantity with execution price
        actual_quantity = amount_krw / exec_price
        
        # Execute simulated trade
        trade = self.balance_manager.execute_trade(
            exchange=self.exchange_name,
            symbol=ticker,
            side="buy",
            price=exec_price,
            quantity=actual_quantity,
            fee_rate=self.trading_fee,
            trade_type="market"
        )
        
        if trade:
            return {
                "uuid": trade.trade_id,
                "side": "bid",
                "ord_type": "price",
                "price": str(amount_krw),
                "state": "done",
                "market": ticker,
                "created_at": trade.timestamp.isoformat(),
                "volume": None,
                "executed_volume": str(actual_quantity),
                "trades_count": 1,
                "trades": [{
                    "market": ticker,
                    "price": str(exec_price),
                    "volume": str(actual_quantity),
                    "funds": str(trade.total_cost),
                    "side": "bid"
                }]
            }
        else:
            raise Exception("Failed to execute simulated trade")
            
    def place_market_sell_order(self, ticker: str, volume: Decimal) -> Dict:
        """Simulate market sell order"""
        # Get current price
        price = self.get_ticker_price(ticker)
        if not price:
            raise Exception(f"Could not get price for {ticker}")
            
        # Get order book for slippage
        order_book = self.get_orderbook(ticker)
        bids = order_book.get("orderbook_units", [])
        
        # Calculate execution price
        exec_price = self._calculate_execution_price_volume(
            bids, volume, price, is_buy=False
        )
        
        # Execute simulated trade
        trade = self.balance_manager.execute_trade(
            exchange=self.exchange_name,
            symbol=ticker,
            side="sell",
            price=exec_price,
            quantity=volume,
            fee_rate=self.trading_fee,
            trade_type="market"
        )
        
        if trade:
            return {
                "uuid": trade.trade_id,
                "side": "ask",
                "ord_type": "market",
                "state": "done",
                "market": ticker,
                "created_at": trade.timestamp.isoformat(),
                "volume": str(volume),
                "executed_volume": str(volume),
                "price": None,
                "trades_count": 1,
                "trades": [{
                    "market": ticker,
                    "price": str(exec_price),
                    "volume": str(volume),
                    "funds": str(trade.total_cost),
                    "side": "ask"
                }]
            }
        else:
            raise Exception("Failed to execute simulated trade")
            
    def place_limit_buy_order(self, ticker: str, price: Decimal, volume: Decimal) -> Dict:
        """Simulate limit buy order"""
        trade = self.balance_manager.execute_trade(
            exchange=self.exchange_name,
            symbol=ticker,
            side="buy",
            price=price,
            quantity=volume,
            fee_rate=self.trading_fee,
            trade_type="limit"
        )
        
        if trade:
            return {
                "uuid": trade.trade_id,
                "side": "bid",
                "ord_type": "limit",
                "price": str(price),
                "state": "done",
                "market": ticker,
                "volume": str(volume),
                "executed_volume": str(volume)
            }
        else:
            raise Exception("Failed to execute simulated trade")
            
    def place_limit_sell_order(self, ticker: str, price: Decimal, volume: Decimal) -> Dict:
        """Simulate limit sell order"""
        trade = self.balance_manager.execute_trade(
            exchange=self.exchange_name,
            symbol=ticker,
            side="sell",
            price=price,
            quantity=volume,
            fee_rate=self.trading_fee,
            trade_type="limit"
        )
        
        if trade:
            return {
                "uuid": trade.trade_id,
                "side": "ask",
                "ord_type": "limit",
                "price": str(price),
                "state": "done",
                "market": ticker,
                "volume": str(volume),
                "executed_volume": str(volume)
            }
        else:
            raise Exception("Failed to execute simulated trade")
            
    def get_deposit_address(self, currency: str) -> List[Dict]:
        """Return mock deposit address"""
        return [{
            "currency": currency,
            "deposit_address": f"MOCK_{self.exchange_name}_{currency}_ADDRESS",
            "secondary_address": None
        }]
        
    def withdraw(self, currency: str, amount: Decimal, address: str,
                      secondary_address: str = None, transaction_type: str = "default") -> Dict:
        """Simulate withdrawal"""
        # Determine destination exchange
        if "binance" in address.lower():
            to_exchange = "binance"
        else:
            to_exchange = "external"
            
        # Use fixed network fees
        network_fees = {
            "BTC": Decimal("0.0005"),
            "ETH": Decimal("0.005"), 
            "XRP": Decimal("0.25"),
            "USDT": Decimal("1.0")
        }
        network_fee = network_fees.get(currency, Decimal("1.0"))
        
        transfer = self.balance_manager.simulate_transfer(
            asset=currency,
            amount=amount,
            from_exchange=self.exchange_name,
            to_exchange=to_exchange,
            network_fee=network_fee
        )
        
        if transfer:
            return {
                "type": "withdraw",
                "uuid": transfer.transfer_id,
                "currency": currency,
                "txid": f"MOCK_TXID_{transfer.transfer_id}",
                "state": "DONE",
                "created_at": transfer.timestamp.isoformat(),
                "done_at": transfer.timestamp.isoformat(),
                "amount": str(amount),
                "fee": str(network_fee)
            }
        else:
            raise Exception("Failed to simulate withdrawal")
            
    def get_withdraw_history(self, currency: str = None, limit: int = 10) -> List[Dict]:
        """Get simulated withdrawal history"""
        transfers = self.balance_manager.get_transfer_history(limit=limit)
        history = []
        
        for transfer in transfers:
            if transfer.from_exchange == self.exchange_name:
                if currency and transfer.asset != currency:
                    continue
                    
                history.append({
                    "type": "withdraw",
                    "uuid": transfer.transfer_id,
                    "currency": transfer.asset,
                    "txid": f"MOCK_TXID_{transfer.transfer_id}",
                    "state": "DONE" if transfer.status == "completed" else "PROCESSING",
                    "created_at": transfer.timestamp.isoformat(),
                    "done_at": transfer.timestamp.isoformat() if transfer.status == "completed" else None,
                    "amount": str(transfer.amount),
                    "fee": str(transfer.fee)
                })
                
        return history
        
    def get_deposit_history(self, currency: str = None, limit: int = 10) -> List[Dict]:
        """Get simulated deposit history"""
        transfers = self.balance_manager.get_transfer_history(limit=limit)
        history = []
        
        for transfer in transfers:
            if transfer.to_exchange == self.exchange_name:
                if currency and transfer.asset != currency:
                    continue
                    
                history.append({
                    "type": "deposit",
                    "uuid": f"DEPOSIT_{transfer.transfer_id}",
                    "currency": transfer.asset,
                    "txid": f"MOCK_TXID_{transfer.transfer_id}",
                    "state": "ACCEPTED" if transfer.status == "completed" else "PROCESSING",
                    "created_at": transfer.timestamp.isoformat(),
                    "done_at": transfer.timestamp.isoformat() if transfer.status == "completed" else None,
                    "amount": str(transfer.amount),
                    "fee": "0"
                })
                
        return history
        
    def get_trading_fee(self, market: str) -> Decimal:
        """Get trading fee"""
        return self.trading_fee
        
    async def get_24hr_stats(self, ticker: str) -> Dict:
        """Get real 24hr stats from actual API"""
        return await self.real_client.get_24hr_stats(ticker)
        
    def get_krw_markets(self) -> List[str]:
        """Get real KRW markets from actual API"""
        return self.real_client.get_krw_markets()
        
    def get_tradable_markets_with_binance(self, binance_usdt_markets: List[str]) -> List[str]:
        """Get KRW markets that also exist on Binance"""
        return self.real_client.get_tradable_markets_with_binance(binance_usdt_markets)
        
    def _calculate_execution_price_krw(self, orders: List[Dict], amount_krw: Decimal,
                                      default_price: Decimal, is_buy: bool) -> Decimal:
        """Calculate execution price for KRW amount order"""
        if not orders:
            return default_price
            
        total_volume = Decimal("0")
        total_cost = Decimal("0")
        
        for order in orders:
            if is_buy:
                price = Decimal(str(order.get("ask_price", 0)))
                size = Decimal(str(order.get("ask_size", 0)))
            else:
                price = Decimal(str(order.get("bid_price", 0)))
                size = Decimal(str(order.get("bid_size", 0)))
                
            if price == 0 or size == 0:
                continue
                
            order_cost = price * size
            
            if total_cost + order_cost <= amount_krw:
                total_cost += order_cost
                total_volume += size
            else:
                # Partial fill of this order
                remaining_krw = amount_krw - total_cost
                partial_volume = remaining_krw / price
                total_volume += partial_volume
                total_cost = amount_krw
                break
                
        if total_volume > 0:
            return total_cost / total_volume
        else:
            return default_price
            
    def _calculate_execution_price_volume(self, orders: List[Dict], volume: Decimal,
                                         default_price: Decimal, is_buy: bool) -> Decimal:
        """Calculate execution price for volume order"""
        if not orders:
            return default_price
            
        remaining_volume = volume
        total_cost = Decimal("0")
        
        for order in orders:
            if is_buy:
                price = Decimal(str(order.get("ask_price", 0)))
                size = Decimal(str(order.get("ask_size", 0)))
            else:
                price = Decimal(str(order.get("bid_price", 0)))
                size = Decimal(str(order.get("bid_size", 0)))
                
            if price == 0 or size == 0:
                continue
                
            if remaining_volume <= size:
                total_cost += remaining_volume * price
                break
            else:
                total_cost += size * price
                remaining_volume -= size
                
        if remaining_volume > 0:
            # Not enough liquidity
            total_cost += remaining_volume * default_price
            
        return total_cost / volume