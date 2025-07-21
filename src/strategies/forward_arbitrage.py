from typing import Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio
from loguru import logger
from enum import Enum

from ..api.binance_client import BinanceClient
from ..api.upbit_client import UpbitClient
from ..utils.premium_calculator import ArbitrageOpportunity


class TradeStatus(Enum):
    PENDING = "pending"
    BUYING_UPBIT = "buying_upbit"
    TRANSFERRING_TO_BINANCE = "transferring_to_binance"
    SELLING_BINANCE = "selling_binance"
    TRANSFERRING_TO_UPBIT = "transferring_to_upbit"
    SELLING_USDT_UPBIT = "selling_usdt_upbit"
    COMPLETED = "completed"
    FAILED = "failed"


class ForwardArbitrageStrategy:
    """
    Forward Arbitrage Strategy (Reverse Premium)
    Buy on Upbit (cheaper) → Transfer to Binance → Sell for USDT → Transfer USDT to Upbit → Sell for KRW
    """
    
    def __init__(self, binance_client: BinanceClient, upbit_client: UpbitClient,
                 max_slippage: Decimal = Decimal("0.005"),
                 transfer_timeout_minutes: int = 30,
                 is_paper_trading: bool = False):
        self.binance = binance_client
        self.upbit = upbit_client
        self.max_slippage = max_slippage
        self.transfer_timeout = timedelta(minutes=transfer_timeout_minutes)
        self.active_trades = {}
        self.is_paper_trading = is_paper_trading
        # Use 1 minute for paper trading, otherwise use configured timeout
        self.paper_trading_transfer_time = 60  # seconds
        
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict:
        trade_id = f"forward_{opportunity.coin_symbol}_{datetime.now().timestamp()}"
        
        trade_record = {
            'id': trade_id,
            'opportunity': opportunity,
            'status': TradeStatus.PENDING,
            'start_time': datetime.now(),
            'steps': []
        }
        
        self.active_trades[trade_id] = trade_record
        
        try:
            # Step 1: Buy coin on Upbit
            await self._buy_on_upbit(trade_record)
            
            # Step 2: Transfer coin to Binance
            await self._transfer_to_binance(trade_record)
            
            # Step 3: Sell coin for USDT on Binance
            await self._sell_on_binance(trade_record)
            
            # Step 4: Transfer USDT to Upbit
            await self._transfer_usdt_to_upbit(trade_record)
            
            # Step 5: Sell USDT for KRW on Upbit
            await self._sell_usdt_on_upbit(trade_record)
            
            trade_record['status'] = TradeStatus.COMPLETED
            trade_record['end_time'] = datetime.now()
            trade_record['profit'] = self._calculate_profit(trade_record)
            
            logger.info(f"Forward arbitrage completed successfully: {trade_record}")
            return trade_record
            
        except Exception as e:
            trade_record['status'] = TradeStatus.FAILED
            trade_record['error'] = str(e)
            trade_record['end_time'] = datetime.now()
            logger.error(f"Forward arbitrage failed: {e}")
            
            # Attempt recovery if possible
            await self._attempt_recovery(trade_record)
            
            return trade_record
            
    async def _buy_on_upbit(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.BUYING_UPBIT
        opportunity = trade_record['opportunity']
        
        try:
            # Get current market price
            ticker = f"KRW-{opportunity.coin_symbol}"
            current_price = self.upbit.get_ticker_price(ticker)
            
            # Check slippage
            expected_price = current_price  # You might want to use orderbook for better accuracy
            
            # Execute market buy
            order = self.upbit.place_market_buy_order(
                ticker=ticker,
                amount_krw=opportunity.trade_amount_krw
            )
            
            # Wait for order to fill
            await asyncio.sleep(2)  # Give time for order to fill
            
            # Record the step
            trade_record['steps'].append({
                'step': 'buy_upbit',
                'timestamp': datetime.now(),
                'order': order,
                'amount_krw': opportunity.trade_amount_krw,
                'executed_price': current_price
            })
            
            logger.info(f"Bought {opportunity.coin_symbol} on Upbit: {order}")
            
        except Exception as e:
            logger.error(f"Failed to buy on Upbit: {e}")
            raise
            
    async def _transfer_to_binance(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.TRANSFERRING_TO_BINANCE
        opportunity = trade_record['opportunity']
        
        try:
            # Get Binance deposit address
            deposit_info = self.binance.get_deposit_address(
                coin=opportunity.coin_symbol,
                network=self._get_optimal_network(opportunity.coin_symbol)
            )
            
            # Get actual coin balance
            balance = self.upbit.get_balance(opportunity.coin_symbol)
            transfer_amount = balance['free'] * Decimal("0.999")  # Keep small amount for fees
            
            # Initiate withdrawal from Upbit
            withdrawal = self.upbit.withdraw(
                currency=opportunity.coin_symbol,
                amount=transfer_amount,
                address=deposit_info['address'],
                secondary_address=deposit_info.get('tag'),
                transaction_type='default'
            )
            
            trade_record['steps'].append({
                'step': 'transfer_to_binance',
                'timestamp': datetime.now(),
                'withdrawal': withdrawal,
                'amount': transfer_amount,
                'address': deposit_info['address']
            })
            
            # Wait for deposit to arrive
            await self._wait_for_binance_deposit(
                opportunity.coin_symbol,
                transfer_amount,
                withdrawal['uuid']
            )
            
            logger.info(f"Transfer to Binance completed: {withdrawal}")
            
        except Exception as e:
            logger.error(f"Failed to transfer to Binance: {e}")
            raise
            
    async def _sell_on_binance(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.SELLING_BINANCE
        opportunity = trade_record['opportunity']
        
        try:
            # Get current balance
            balance = self.binance.get_balance(opportunity.coin_symbol)
            sell_amount = balance['free']
            
            # Execute market sell
            symbol = f"{opportunity.coin_symbol}USDT"
            order = self.binance.place_market_order(
                symbol=symbol,
                side='SELL',
                quantity=sell_amount
            )
            
            trade_record['steps'].append({
                'step': 'sell_binance',
                'timestamp': datetime.now(),
                'order': order,
                'amount': sell_amount,
                'symbol': symbol
            })
            
            logger.info(f"Sold {opportunity.coin_symbol} on Binance: {order}")
            
        except Exception as e:
            logger.error(f"Failed to sell on Binance: {e}")
            raise
            
    async def _transfer_usdt_to_upbit(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.TRANSFERRING_TO_UPBIT
        
        try:
            # Get USDT balance
            balance = self.binance.get_balance('USDT')
            transfer_amount = balance['free'] - Decimal("1")  # Keep 1 USDT for fees
            
            # Get Upbit USDT deposit address
            deposit_info = self.upbit.get_deposit_address('USDT')
            
            # Initiate withdrawal from Binance
            withdrawal = self.binance.withdraw(
                coin='USDT',
                address=deposit_info['deposit_address'],
                amount=transfer_amount,
                network='TRC20',  # Use TRC20 for lower fees
                tag=deposit_info.get('secondary_address')
            )
            
            trade_record['steps'].append({
                'step': 'transfer_usdt_to_upbit',
                'timestamp': datetime.now(),
                'withdrawal': withdrawal,
                'amount': transfer_amount,
                'network': 'TRC20'
            })
            
            # Wait for deposit to arrive
            await self._wait_for_upbit_deposit('USDT', transfer_amount, withdrawal['id'])
            
            logger.info(f"USDT transfer to Upbit completed: {withdrawal}")
            
        except Exception as e:
            logger.error(f"Failed to transfer USDT to Upbit: {e}")
            raise
            
    async def _sell_usdt_on_upbit(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.SELLING_USDT_UPBIT
        
        try:
            # Get USDT balance
            balance = self.upbit.get_balance('USDT')
            sell_amount = balance['free']
            
            # Execute market sell
            order = self.upbit.place_market_sell_order(
                ticker='KRW-USDT',
                volume=sell_amount
            )
            
            trade_record['steps'].append({
                'step': 'sell_usdt_upbit',
                'timestamp': datetime.now(),
                'order': order,
                'amount': sell_amount
            })
            
            logger.info(f"Sold USDT on Upbit: {order}")
            
        except Exception as e:
            logger.error(f"Failed to sell USDT on Upbit: {e}")
            raise
            
    async def _wait_for_binance_deposit(self, coin: str, amount: Decimal, 
                                       withdrawal_id: str):
        if self.is_paper_trading:
            # For paper trading, simulate 1 minute transfer time
            logger.info(f"Paper trading: Simulating {coin} transfer to Binance (1 minute)...")
            await asyncio.sleep(self.paper_trading_transfer_time)
            logger.info(f"Paper trading: {coin} transfer to Binance completed")
            
            # In paper trading, the transfer is already simulated by MockUpbitClient.withdraw()
            return
            
        # Real trading logic
        start_time = datetime.now()
        initial_balance = self.binance.get_balance(coin)['total']
        
        while datetime.now() - start_time < self.transfer_timeout:
            try:
                current_balance = self.binance.get_balance(coin)['total']
                
                if current_balance > initial_balance:
                    # Check if the increase matches expected amount (with some tolerance)
                    if current_balance - initial_balance >= amount * Decimal("0.99"):
                        logger.info(f"Deposit confirmed on Binance: {coin}")
                        return
                        
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.warning(f"Error checking Binance balance: {e}")
                await asyncio.sleep(30)
                
        raise TimeoutError(f"Deposit timeout: {coin} not received on Binance")
        
    async def _wait_for_upbit_deposit(self, currency: str, amount: Decimal,
                                    withdrawal_id: str):
        if self.is_paper_trading:
            # For paper trading, simulate 1 minute transfer time
            logger.info(f"Paper trading: Simulating {currency} transfer to Upbit (1 minute)...")
            await asyncio.sleep(self.paper_trading_transfer_time)
            logger.info(f"Paper trading: {currency} transfer to Upbit completed")
            
            # In paper trading, the transfer is already simulated by MockBinanceClient.withdraw()
            return
            
        # Real trading logic
        start_time = datetime.now()
        initial_balance = self.upbit.get_balance(currency)['total']
        
        while datetime.now() - start_time < self.transfer_timeout:
            try:
                current_balance = self.upbit.get_balance(currency)['total']
                
                if current_balance > initial_balance:
                    # Check if the increase matches expected amount (with some tolerance)
                    if current_balance - initial_balance >= amount * Decimal("0.99"):
                        logger.info(f"Deposit confirmed on Upbit: {currency}")
                        return
                        
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.warning(f"Error checking Upbit balance: {e}")
                await asyncio.sleep(30)
                
        raise TimeoutError(f"Deposit timeout: {currency} not received on Upbit")
        
    def _get_optimal_network(self, coin: str) -> str:
        # Network selection for different coins
        network_map = {
            'BTC': 'BTC',
            'ETH': 'ETH',
            'USDT': 'TRC20',  # TRC20 is faster and cheaper
            'XRP': 'XRP',
            'ADA': 'ADA',
            'SOL': 'SOL',
            'DOT': 'DOT',
            'AVAX': 'AVAX-C'
        }
        return network_map.get(coin, coin)
        
    def _get_network_fee(self, coin: str) -> Decimal:
        """Get network fee for a coin"""
        network_fees = {
            "BTC": Decimal("0.0005"),
            "ETH": Decimal("0.005"),
            "XRP": Decimal("0.25"),
            "USDT": Decimal("1.0"),
            "ADA": Decimal("1.0"),
            "SOL": Decimal("0.01"),
            "DOT": Decimal("0.1"),
            "AVAX": Decimal("0.01")
        }
        return network_fees.get(coin, Decimal("1.0"))  # Default fee
        
    def _calculate_profit(self, trade_record: Dict) -> Dict:
        try:
            initial_krw = trade_record['opportunity'].trade_amount_krw
            
            # Get final KRW amount from last step
            final_step = trade_record['steps'][-1]
            if 'order' in final_step:
                # Estimate final KRW (this should be more accurate with actual order data)
                final_krw = Decimal(str(final_step['order'].get('executed_funds', 0)))
            else:
                final_krw = Decimal("0")
                
            profit_krw = final_krw - initial_krw
            profit_rate = (profit_krw / initial_krw) * 100
            
            return {
                'initial_krw': initial_krw,
                'final_krw': final_krw,
                'profit_krw': profit_krw,
                'profit_rate': profit_rate
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate profit: {e}")
            return {
                'initial_krw': trade_record['opportunity'].trade_amount_krw,
                'final_krw': Decimal("0"),
                'profit_krw': Decimal("0"),
                'profit_rate': Decimal("0")
            }
            
    async def _attempt_recovery(self, trade_record: Dict):
        """Attempt to recover from failed trades"""
        try:
            status = trade_record['status']
            
            if status == TradeStatus.TRANSFERRING_TO_BINANCE:
                # Check if transfer completed
                pass
                
            elif status == TradeStatus.SELLING_BINANCE:
                # Try to sell any remaining balance
                pass
                
            elif status == TradeStatus.TRANSFERRING_TO_UPBIT:
                # Check if USDT transfer completed
                pass
                
            # Add more recovery logic as needed
            
        except Exception as e:
            logger.error(f"Recovery attempt failed: {e}")