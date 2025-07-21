"""Virtual balance manager for paper trading simulation"""
from typing import Dict, Optional, List
from decimal import Decimal
from datetime import datetime
from loguru import logger
import json
import os
from dataclasses import dataclass, asdict


@dataclass
class VirtualBalance:
    """Virtual balance for a specific asset"""
    asset: str
    available: Decimal
    locked: Decimal = Decimal("0")
    
    @property
    def total(self) -> Decimal:
        return self.available + self.locked


@dataclass
class SimulatedTrade:
    """Record of a simulated trade"""
    timestamp: datetime
    trade_id: str
    exchange: str
    symbol: str
    side: str  # buy/sell
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_asset: str
    total_cost: Decimal
    trade_type: str  # market/limit
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['price'] = str(self.price)
        data['quantity'] = str(self.quantity)
        data['fee'] = str(self.fee)
        data['total_cost'] = str(self.total_cost)
        return data


@dataclass
class SimulatedTransfer:
    """Record of a simulated transfer between exchanges"""
    timestamp: datetime
    transfer_id: str
    asset: str
    amount: Decimal
    from_exchange: str
    to_exchange: str
    fee: Decimal
    status: str  # pending/completed/failed
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['amount'] = str(self.amount)
        data['fee'] = str(self.fee)
        return data


class VirtualBalanceManager:
    """Manages virtual balances for paper trading simulation"""
    
    def __init__(self, initial_balances: Dict[str, Dict[str, Decimal]], 
                 state_file: str = "simulation_state.json"):
        """
        Initialize virtual balance manager
        
        Args:
            initial_balances: Initial balances by exchange and asset
                            e.g., {"binance": {"USDT": 10000}, "upbit": {"KRW": 10000000}}
            state_file: Path to save/load simulation state
        """
        self.state_file = state_file
        self.balances: Dict[str, Dict[str, VirtualBalance]] = {}
        self.trades: List[SimulatedTrade] = []
        self.transfers: List[SimulatedTransfer] = []
        self.trade_counter = 0
        self.transfer_counter = 0
        
        # Try to load existing state
        if os.path.exists(state_file):
            self.load_state()
        else:
            # Initialize with provided balances
            for exchange, assets in initial_balances.items():
                self.balances[exchange] = {}
                for asset, amount in assets.items():
                    self.balances[exchange][asset] = VirtualBalance(
                        asset=asset,
                        available=amount
                    )
                    
        logger.info("Virtual balance manager initialized")
        self._log_all_balances()
        
    def get_balance(self, exchange: str, asset: str) -> Optional[VirtualBalance]:
        """Get virtual balance for an asset on an exchange"""
        if exchange not in self.balances:
            return None
        return self.balances[exchange].get(asset)
        
    def lock_balance(self, exchange: str, asset: str, amount: Decimal) -> bool:
        """Lock balance for pending order"""
        balance = self.get_balance(exchange, asset)
        if not balance or balance.available < amount:
            return False
            
        balance.available -= amount
        balance.locked += amount
        self.save_state()
        return True
        
    def unlock_balance(self, exchange: str, asset: str, amount: Decimal) -> bool:
        """Unlock previously locked balance"""
        balance = self.get_balance(exchange, asset)
        if not balance or balance.locked < amount:
            return False
            
        balance.locked -= amount
        balance.available += amount
        self.save_state()
        return True
        
    def execute_trade(self, exchange: str, symbol: str, side: str, 
                     price: Decimal, quantity: Decimal, 
                     fee_rate: Decimal, trade_type: str = "market") -> Optional[SimulatedTrade]:
        """
        Simulate trade execution
        
        Args:
            exchange: Exchange name (binance/upbit)
            symbol: Trading pair (e.g., "BTCUSDT", "BTC-KRW")
            side: Buy or sell
            price: Execution price
            quantity: Trade quantity
            fee_rate: Trading fee rate (e.g., 0.001 for 0.1%)
            trade_type: Market or limit order
            
        Returns:
            SimulatedTrade object if successful, None otherwise
        """
        # Parse symbol to get base and quote assets
        if exchange == "binance":
            # Binance format: BTCUSDT
            if symbol.endswith("USDT"):
                base_asset = symbol[:-4]
                quote_asset = "USDT"
            else:
                logger.error(f"Unsupported Binance symbol format: {symbol}")
                return None
        else:  # upbit
            # Upbit format: KRW-BTC (quote-base)
            parts = symbol.split("-")
            if len(parts) != 2:
                logger.error(f"Invalid Upbit symbol format: {symbol}")
                return None
            quote_asset = parts[0]  # KRW
            base_asset = parts[1]   # BTC
            
        # Calculate costs and fees
        total_cost = price * quantity
        fee = total_cost * fee_rate
        
        # Update balances based on trade side
        if side.lower() == "buy":
            # Deduct quote asset and add base asset
            quote_balance = self.get_balance(exchange, quote_asset)
            if not quote_balance or quote_balance.available < (total_cost + fee):
                logger.error(f"Insufficient {quote_asset} balance for buy order - needed: {total_cost + fee}, available: {quote_balance.available if quote_balance else 0}")
                return None
                
            # Update balances
            quote_balance.available -= (total_cost + fee)
            
            # Add base asset
            if base_asset not in self.balances[exchange]:
                self.balances[exchange][base_asset] = VirtualBalance(
                    asset=base_asset,
                    available=Decimal("0")
                )
            self.balances[exchange][base_asset].available += quantity
            
            fee_asset = quote_asset
            
        else:  # sell
            # Deduct base asset and add quote asset
            base_balance = self.get_balance(exchange, base_asset)
            if not base_balance or base_balance.available < quantity:
                logger.error(f"Insufficient {base_asset} balance for sell order - needed: {quantity}, available: {base_balance.available if base_balance else 0}")
                return None
                
            # Update balances
            base_balance.available -= quantity
            
            # Add quote asset (minus fee)
            if quote_asset not in self.balances[exchange]:
                self.balances[exchange][quote_asset] = VirtualBalance(
                    asset=quote_asset,
                    available=Decimal("0")
                )
            self.balances[exchange][quote_asset].available += (total_cost - fee)
            
            fee_asset = quote_asset
            
        # Create trade record
        self.trade_counter += 1
        trade = SimulatedTrade(
            timestamp=datetime.now(),
            trade_id=f"SIM_{exchange}_{self.trade_counter}",
            exchange=exchange,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            fee=fee,
            fee_asset=fee_asset,
            total_cost=total_cost,
            trade_type=trade_type
        )
        
        self.trades.append(trade)
        self.save_state()
        
        logger.info(f"Simulated {side} trade on {exchange}: {quantity} {base_asset} @ {price} {quote_asset}")
        logger.info(f"Fee: {fee} {fee_asset}, Total: {total_cost} {quote_asset}")
        
        return trade
        
    def simulate_transfer(self, asset: str, amount: Decimal, 
                         from_exchange: str, to_exchange: str,
                         network_fee: Decimal) -> Optional[SimulatedTransfer]:
        """
        Simulate asset transfer between exchanges
        
        Args:
            asset: Asset to transfer
            amount: Amount to transfer
            from_exchange: Source exchange
            to_exchange: Destination exchange
            network_fee: Network transfer fee
            
        Returns:
            SimulatedTransfer object if successful, None otherwise
        """
        # Check source balance
        from_balance = self.get_balance(from_exchange, asset)
        if not from_balance or from_balance.available < (amount + network_fee):
            logger.error(f"Insufficient {asset} balance on {from_exchange} for transfer")
            return None
            
        # Deduct from source (including fee)
        from_balance.available -= (amount + network_fee)
        
        # Add to destination
        if asset not in self.balances[to_exchange]:
            self.balances[to_exchange][asset] = VirtualBalance(
                asset=asset,
                available=Decimal("0")
            )
        self.balances[to_exchange][asset].available += amount
        
        # Create transfer record
        self.transfer_counter += 1
        transfer = SimulatedTransfer(
            timestamp=datetime.now(),
            transfer_id=f"SIM_TRANSFER_{self.transfer_counter}",
            asset=asset,
            amount=amount,
            from_exchange=from_exchange,
            to_exchange=to_exchange,
            fee=network_fee,
            status="completed"
        )
        
        self.transfers.append(transfer)
        self.save_state()
        
        logger.info(f"Simulated transfer: {amount} {asset} from {from_exchange} to {to_exchange}")
        logger.info(f"Network fee: {network_fee} {asset}")
        
        return transfer
        
    def get_total_value_krw(self, exchange_rate_provider) -> Dict[str, Decimal]:
        """
        Calculate total portfolio value in KRW for each exchange
        
        Args:
            exchange_rate_provider: Provider for USD/KRW exchange rate
            
        Returns:
            Dictionary of total values by exchange
        """
        total_values = {}
        
        for exchange, balances in self.balances.items():
            total_krw = Decimal("0")
            
            for asset, balance in balances.items():
                if balance.total == 0:
                    continue
                    
                if asset == "KRW":
                    total_krw += balance.total
                elif asset == "USDT":
                    # Convert USDT to KRW
                    usd_krw_rate = exchange_rate_provider.get_usd_krw_rate()
                    if usd_krw_rate:
                        total_krw += balance.total * usd_krw_rate
                else:
                    # For other assets, we'd need their prices
                    # For now, we'll skip them
                    logger.debug(f"Skipping {asset} in portfolio value calculation")
                    
            total_values[exchange] = total_krw
            
        return total_values
        
    def get_trade_history(self, limit: Optional[int] = None) -> List[SimulatedTrade]:
        """Get recent trade history"""
        if limit:
            return self.trades[-limit:]
        return self.trades
        
    def get_transfer_history(self, limit: Optional[int] = None) -> List[SimulatedTransfer]:
        """Get recent transfer history"""
        if limit:
            return self.transfers[-limit:]
        return self.transfers
        
    def save_state(self):
        """Save current state to file"""
        state = {
            "balances": {},
            "trades": [trade.to_dict() for trade in self.trades],
            "transfers": [transfer.to_dict() for transfer in self.transfers],
            "trade_counter": self.trade_counter,
            "transfer_counter": self.transfer_counter
        }
        
        # Convert balances to serializable format
        for exchange, assets in self.balances.items():
            state["balances"][exchange] = {}
            for asset, balance in assets.items():
                state["balances"][exchange][asset] = {
                    "available": str(balance.available),
                    "locked": str(balance.locked)
                }
                
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
            
    def load_state(self):
        """Load state from file"""
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                
            # Restore balances
            self.balances = {}
            for exchange, assets in state.get("balances", {}).items():
                self.balances[exchange] = {}
                for asset, data in assets.items():
                    self.balances[exchange][asset] = VirtualBalance(
                        asset=asset,
                        available=Decimal(data["available"]),
                        locked=Decimal(data.get("locked", "0"))
                    )
                    
            # Restore counters
            self.trade_counter = state.get("trade_counter", 0)
            self.transfer_counter = state.get("transfer_counter", 0)
            
            # Note: We're not restoring trade/transfer history for simplicity
            # Could be added if needed
            
            logger.info("Loaded simulation state from file")
            
        except Exception as e:
            logger.error(f"Failed to load simulation state: {e}")
            
    def reset_state(self, initial_balances: Dict[str, Dict[str, Decimal]]):
        """Reset to initial state"""
        self.balances = {}
        self.trades = []
        self.transfers = []
        self.trade_counter = 0
        self.transfer_counter = 0
        
        for exchange, assets in initial_balances.items():
            self.balances[exchange] = {}
            for asset, amount in assets.items():
                self.balances[exchange][asset] = VirtualBalance(
                    asset=asset,
                    available=amount
                )
                
        self.save_state()
        logger.info("Reset simulation state to initial balances")
        
    def _log_all_balances(self):
        """Log all current balances"""
        for exchange, balances in self.balances.items():
            logger.info(f"{exchange.upper()} balances:")
            for asset, balance in balances.items():
                if balance.total > 0:
                    logger.info(f"  {asset}: {balance.available} available, {balance.locked} locked")