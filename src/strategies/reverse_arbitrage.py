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
    BUYING_USDT_BINANCE = "buying_usdt_binance"
    BUYING_COIN_BINANCE = "buying_coin_binance"
    TRANSFERRING_TO_UPBIT = "transferring_to_upbit"
    SELLING_UPBIT = "selling_upbit"
    BUYING_USDT_UPBIT = "buying_usdt_upbit"
    TRANSFERRING_TO_BINANCE = "transferring_to_binance"
    COMPLETED = "completed"
    FAILED = "failed"


class ReverseArbitrageStrategy:
    """
    Reverse Arbitrage Strategy (Kimchi Premium)
    Buy USDT → Buy coin on Binance → Transfer to Upbit → Sell for KRW → Buy USDT on Upbit → Transfer back to Binance
    """
    
    def __init__(self, binance_client: BinanceClient, upbit_client: UpbitClient,
                 max_slippage: Decimal = Decimal("0.005"),
                 transfer_timeout_minutes: int = 30):
        self.binance = binance_client
        self.upbit = upbit_client
        self.max_slippage = max_slippage
        self.transfer_timeout = timedelta(minutes=transfer_timeout_minutes)
        self.active_trades = {}
        
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict:
        trade_id = f"reverse_{opportunity.coin_symbol}_{datetime.now().timestamp()}"
        
        trade_record = {
            'id': trade_id,
            'opportunity': opportunity,
            'status': TradeStatus.PENDING,
            'start_time': datetime.now(),
            'steps': []
        }
        
        self.active_trades[trade_id] = trade_record
        
        try:
            # Step 1: Calculate required USDT amount and ensure balance
            await self._ensure_usdt_balance(trade_record)
            
            # Step 2: Buy coin on Binance with USDT
            await self._buy_on_binance(trade_record)
            
            # Step 3: Transfer coin to Upbit
            await self._transfer_to_upbit(trade_record)
            
            # Step 4: Sell coin for KRW on Upbit
            await self._sell_on_upbit(trade_record)
            
            # Step 5: Buy USDT with KRW on Upbit
            await self._buy_usdt_on_upbit(trade_record)
            
            # Step 6: Transfer USDT back to Binance
            await self._transfer_usdt_to_binance(trade_record)
            
            trade_record['status'] = TradeStatus.COMPLETED
            trade_record['end_time'] = datetime.now()
            trade_record['profit'] = self._calculate_profit(trade_record)
            
            logger.info(f"Reverse arbitrage completed successfully: {trade_record}")
            return trade_record
            
        except Exception as e:
            trade_record['status'] = TradeStatus.FAILED
            trade_record['error'] = str(e)
            trade_record['end_time'] = datetime.now()
            logger.error(f"Reverse arbitrage failed: {e}")
            
            # Attempt recovery if possible
            await self._attempt_recovery(trade_record)
            
            return trade_record
            
    async def _ensure_usdt_balance(self, trade_record: Dict):
        opportunity = trade_record['opportunity']
        
        try:
            # Convert KRW amount to USDT
            from ..utils.exchange_rate import ExchangeRateProvider
            exchange_rate = ExchangeRateProvider()
            
            required_usdt = exchange_rate.convert_krw_to_usd(opportunity.trade_amount_krw)
            if required_usdt is None:
                raise ValueError("Cannot proceed with trade: Exchange rate unavailable")
            required_usdt *= Decimal("1.01")  # Add 1% buffer for price changes
            
            # Check current USDT balance
            balance = self.binance.get_balance('USDT')
            
            if balance['free'] < required_usdt:
                raise ValueError(f"Insufficient USDT balance. Required: {required_usdt}, Available: {balance['free']}")
                
            trade_record['steps'].append({
                'step': 'check_usdt_balance',
                'timestamp': datetime.now(),
                'required_usdt': required_usdt,
                'available_usdt': balance['free']
            })
            
        except Exception as e:
            logger.error(f"Failed to ensure USDT balance: {e}")
            raise
            
    async def _buy_on_binance(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.BUYING_COIN_BINANCE
        opportunity = trade_record['opportunity']
        
        try:
            # Get current market price
            symbol = f"{opportunity.coin_symbol}USDT"
            current_price = self.binance.get_ticker_price(symbol)
            
            # Calculate quantity to buy
            usdt_amount = trade_record['steps'][0]['required_usdt']
            quantity = (usdt_amount / current_price) * Decimal("0.995")  # Account for fees
            
            # Execute market buy
            order = self.binance.place_market_order(
                symbol=symbol,
                side='BUY',
                quantity=quantity
            )
            
            trade_record['steps'].append({
                'step': 'buy_binance',
                'timestamp': datetime.now(),
                'order': order,
                'symbol': symbol,
                'quantity': quantity,
                'usdt_spent': usdt_amount
            })
            
            logger.info(f"Bought {opportunity.coin_symbol} on Binance: {order}")
            
        except Exception as e:
            logger.error(f"Failed to buy on Binance: {e}")
            raise
            
    async def _transfer_to_upbit(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.TRANSFERRING_TO_UPBIT
        opportunity = trade_record['opportunity']
        
        try:
            # Get Upbit deposit address
            deposit_info = self.upbit.get_deposit_address(opportunity.coin_symbol)
            
            # Get actual coin balance
            balance = self.binance.get_balance(opportunity.coin_symbol)
            transfer_amount = balance['free']
            
            # Get withdrawal fee
            withdrawal_fee = self._get_withdrawal_fee(opportunity.coin_symbol)
            transfer_amount = transfer_amount - withdrawal_fee
            
            # Initiate withdrawal from Binance
            withdrawal = self.binance.withdraw(
                coin=opportunity.coin_symbol,
                address=deposit_info['deposit_address'],
                amount=transfer_amount,
                network=self._get_optimal_network(opportunity.coin_symbol),
                tag=deposit_info.get('secondary_address')
            )
            
            trade_record['steps'].append({
                'step': 'transfer_to_upbit',
                'timestamp': datetime.now(),
                'withdrawal': withdrawal,
                'amount': transfer_amount,
                'fee': withdrawal_fee,
                'address': deposit_info['deposit_address']
            })
            
            # Wait for deposit to arrive
            await self._wait_for_upbit_deposit(
                opportunity.coin_symbol,
                transfer_amount,
                withdrawal['id']
            )
            
            logger.info(f"Transfer to Upbit completed: {withdrawal}")
            
        except Exception as e:
            logger.error(f"Failed to transfer to Upbit: {e}")
            raise
            
    async def _sell_on_upbit(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.SELLING_UPBIT
        opportunity = trade_record['opportunity']
        
        try:
            # Get current balance
            balance = self.upbit.get_balance(opportunity.coin_symbol)
            sell_amount = balance['free']
            
            # Execute market sell
            ticker = f"KRW-{opportunity.coin_symbol}"
            order = self.upbit.place_market_sell_order(
                ticker=ticker,
                volume=sell_amount
            )
            
            # Wait for order to complete
            await asyncio.sleep(2)
            
            trade_record['steps'].append({
                'step': 'sell_upbit',
                'timestamp': datetime.now(),
                'order': order,
                'amount': sell_amount,
                'ticker': ticker
            })
            
            logger.info(f"Sold {opportunity.coin_symbol} on Upbit: {order}")
            
        except Exception as e:
            logger.error(f"Failed to sell on Upbit: {e}")
            raise
            
    async def _buy_usdt_on_upbit(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.BUYING_USDT_UPBIT
        
        try:
            # Get KRW balance
            balance = self.upbit.get_balance('KRW')
            available_krw = balance['free'] - Decimal("10000")  # Keep 10k KRW as buffer
            
            # Execute market buy of USDT
            order = self.upbit.place_market_buy_order(
                ticker='KRW-USDT',
                amount_krw=available_krw
            )
            
            # Wait for order to complete
            await asyncio.sleep(2)
            
            trade_record['steps'].append({
                'step': 'buy_usdt_upbit',
                'timestamp': datetime.now(),
                'order': order,
                'krw_spent': available_krw
            })
            
            logger.info(f"Bought USDT on Upbit: {order}")
            
        except Exception as e:
            logger.error(f"Failed to buy USDT on Upbit: {e}")
            raise
            
    async def _transfer_usdt_to_binance(self, trade_record: Dict):
        trade_record['status'] = TradeStatus.TRANSFERRING_TO_BINANCE
        
        try:
            # Get USDT balance
            balance = self.upbit.get_balance('USDT')
            transfer_amount = balance['free'] - Decimal("1")  # Keep 1 USDT for fees
            
            # Get Binance USDT deposit address
            deposit_info = self.binance.get_deposit_address('USDT', network='TRC20')
            
            # Initiate withdrawal from Upbit
            withdrawal = self.upbit.withdraw(
                currency='USDT',
                amount=transfer_amount,
                address=deposit_info['address'],
                secondary_address=deposit_info.get('tag'),
                transaction_type='default'
            )
            
            trade_record['steps'].append({
                'step': 'transfer_usdt_to_binance',
                'timestamp': datetime.now(),
                'withdrawal': withdrawal,
                'amount': transfer_amount,
                'network': 'TRC20'
            })
            
            # Wait for deposit to arrive
            await self._wait_for_binance_deposit('USDT', transfer_amount, withdrawal['uuid'])
            
            logger.info(f"USDT transfer to Binance completed: {withdrawal}")
            
        except Exception as e:
            logger.error(f"Failed to transfer USDT to Binance: {e}")
            raise
            
    async def _wait_for_upbit_deposit(self, currency: str, amount: Decimal,
                                    withdrawal_id: str):
        start_time = datetime.now()
        initial_balance = self.upbit.get_balance(currency)['total']
        
        while datetime.now() - start_time < self.transfer_timeout:
            try:
                # Check deposit history
                deposits = self.upbit.get_deposit_history(currency=currency, limit=10)
                for deposit in deposits:
                    if deposit.get('state') == 'accepted' and \
                       Decimal(deposit.get('amount', 0)) >= amount * Decimal("0.99"):
                        logger.info(f"Deposit confirmed on Upbit: {currency}")
                        return
                        
                # Also check balance increase
                current_balance = self.upbit.get_balance(currency)['total']
                if current_balance - initial_balance >= amount * Decimal("0.99"):
                    logger.info(f"Deposit confirmed on Upbit via balance check: {currency}")
                    return
                    
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.warning(f"Error checking Upbit deposit: {e}")
                await asyncio.sleep(30)
                
        raise TimeoutError(f"Deposit timeout: {currency} not received on Upbit")
        
    async def _wait_for_binance_deposit(self, coin: str, amount: Decimal,
                                       withdrawal_id: str):
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
        
    def _get_optimal_network(self, coin: str) -> str:
        network_map = {
            'BTC': 'BTC',
            'ETH': 'ETH',
            'USDT': 'TRC20',
            'XRP': 'XRP',
            'ADA': 'ADA',
            'SOL': 'SOL',
            'DOT': 'DOT',
            'AVAX': 'AVAX-C'
        }
        return network_map.get(coin, coin)
        
    def _get_withdrawal_fee(self, coin: str) -> Decimal:
        fees = {
            'BTC': Decimal("0.0005"),
            'ETH': Decimal("0.005"),
            'XRP': Decimal("0.25"),
            'ADA': Decimal("1"),
            'SOL': Decimal("0.01"),
            'DOT': Decimal("0.1"),
            'AVAX': Decimal("0.01")
        }
        return fees.get(coin, Decimal("0"))
        
    def _calculate_profit(self, trade_record: Dict) -> Dict:
        try:
            # Get initial USDT spent
            initial_usdt = trade_record['steps'][0]['required_usdt']
            
            # Get final USDT balance change
            final_step = [s for s in trade_record['steps'] if s['step'] == 'transfer_usdt_to_binance'][0]
            returned_usdt = final_step['amount']
            
            profit_usdt = returned_usdt - initial_usdt
            profit_rate = (profit_usdt / initial_usdt) * 100
            
            # Convert to KRW for reference
            from ..utils.exchange_rate import ExchangeRateProvider
            exchange_rate = ExchangeRateProvider()
            profit_krw = exchange_rate.convert_usd_to_krw(profit_usdt)
            if profit_krw is None:
                profit_krw = Decimal("0")  # Fallback if exchange rate unavailable
            
            return {
                'initial_usdt': initial_usdt,
                'final_usdt': returned_usdt,
                'profit_usdt': profit_usdt,
                'profit_krw': profit_krw,
                'profit_rate': profit_rate
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate profit: {e}")
            return {
                'initial_usdt': Decimal("0"),
                'final_usdt': Decimal("0"),
                'profit_usdt': Decimal("0"),
                'profit_krw': Decimal("0"),
                'profit_rate': Decimal("0")
            }
            
    async def _attempt_recovery(self, trade_record: Dict):
        """Attempt to recover from failed trades"""
        try:
            status = trade_record['status']
            
            if status == TradeStatus.BUYING_COIN_BINANCE:
                # Check if order was partially filled
                pass
                
            elif status == TradeStatus.TRANSFERRING_TO_UPBIT:
                # Check if transfer completed
                pass
                
            elif status == TradeStatus.SELLING_UPBIT:
                # Try to sell any remaining balance
                pass
                
            # Add more recovery logic as needed
            
        except Exception as e:
            logger.error(f"Recovery attempt failed: {e}")