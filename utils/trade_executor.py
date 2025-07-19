import asyncio
import time
from typing import Dict, Optional, Tuple
from datetime import datetime
from loguru import logger
from exchanges.binance_client import BinanceClient
from exchanges.upbit_client import UpbitClient


class TradeExecutor:
    def __init__(self, binance_client: BinanceClient, upbit_client: UpbitClient, config: Dict):
        self.binance = binance_client
        self.upbit = upbit_client
        self.config = config
        self.active_trades = []
        self.daily_profit = 0.0
        self.daily_loss = 0.0
        self.trade_history = []
        
    async def execute_axis_1(self, coin: str, trade_volume_usdt: float) -> Dict:
        """
        Axis 1: Upbit → Binance
        1. Buy on Upbit (USDT)
        2. Withdraw to Binance
        3. Sell on Binance (USDT)
        """
        logger.info(f"Executing Axis 1 trade for {coin} with {trade_volume_usdt} USDT")
        trade_result = {
            'coin': coin,
            'axis': 1,
            'status': 'pending',
            'start_time': datetime.now(),
            'steps': []
        }
        
        try:
            logger.info(f"Step 1: Buying {coin} on Upbit with {trade_volume_usdt} USDT")
            upbit_order = await self.upbit.create_market_order(coin, 'BUY', price=trade_volume_usdt)
            
            if not upbit_order or 'error' in upbit_order:
                raise Exception(f"Upbit order failed: {upbit_order}")
            
            executed_volume = float(upbit_order.get('executed_volume', 0))
            if executed_volume <= 0:
                raise Exception("No volume executed on Upbit")
            
            trade_result['steps'].append({
                'step': 'upbit_buy',
                'order': upbit_order,
                'volume': executed_volume,
                'usdt_spent': trade_volume_usdt,
                'timestamp': datetime.now()
            })
            
            logger.info(f"Step 2: Getting Binance deposit address for {coin}")
            binance_address = await self.binance.get_deposit_address(coin)
            
            withdrawal_fee = self.config['fee_data']['upbit']['withdraw'].get(coin, 0)
            withdrawal_amount = executed_volume - withdrawal_fee
            
            logger.info(f"Step 3: Withdrawing {withdrawal_amount} {coin} from Upbit to Binance")
            withdrawal = await self.upbit.withdraw(
                coin, 
                withdrawal_amount,
                binance_address['address'],
                binance_address.get('tag')
            )
            
            trade_result['steps'].append({
                'step': 'upbit_withdraw',
                'withdrawal': withdrawal,
                'amount': withdrawal_amount,
                'timestamp': datetime.now()
            })
            
            logger.info(f"Step 4: Waiting for deposit confirmation on Binance")
            deposit_confirmed = await self._wait_for_deposit(
                'binance',
                coin,
                withdrawal.get('uuid', ''),
                timeout=3600
            )
            
            if not deposit_confirmed:
                raise Exception("Deposit confirmation timeout")
            
            trade_result['steps'].append({
                'step': 'binance_deposit_confirmed',
                'timestamp': datetime.now()
            })
            
            logger.info(f"Step 5: Selling {coin} on Binance")
            binance_balance = await self.binance.get_balance(coin)
            sell_amount = binance_balance['free'] * 0.999
            
            binance_order = await self.binance.create_market_order(coin, 'SELL', quantity=sell_amount)
            
            usdt_received = float(binance_order.get('cummulativeQuoteQty', 0))
            
            trade_result['steps'].append({
                'step': 'binance_sell',
                'order': binance_order,
                'amount': sell_amount,
                'usdt_received': usdt_received,
                'timestamp': datetime.now()
            })
            
            trade_result['status'] = 'completed'
            trade_result['end_time'] = datetime.now()
            trade_result['profit'] = usdt_received - trade_volume_usdt
            
            self.trade_history.append(trade_result)
            logger.info(f"Axis 1 trade completed successfully. Profit: {trade_result['profit']} USDT")
            
        except Exception as e:
            logger.error(f"Axis 1 trade failed: {e}")
            trade_result['status'] = 'failed'
            trade_result['error'] = str(e)
            trade_result['end_time'] = datetime.now()
            self.trade_history.append(trade_result)
            
        return trade_result
    
    async def execute_axis_2(self, coin: str, trade_volume_usdt: float) -> Dict:
        """
        Axis 2: Binance → Upbit
        1. Buy on Binance (USDT)
        2. Withdraw to Upbit
        3. Sell on Upbit (USDT)
        """
        logger.info(f"Executing Axis 2 trade for {coin} with {trade_volume_usdt} USDT")
        trade_result = {
            'coin': coin,
            'axis': 2,
            'status': 'pending',
            'start_time': datetime.now(),
            'steps': []
        }
        
        try:
            logger.info(f"Step 1: Buying {coin} on Binance with {trade_volume_usdt} USDT")
            binance_order = await self.binance.create_market_order(coin, 'BUY', quote_qty=trade_volume_usdt)
            
            if not binance_order or 'status' not in binance_order:
                raise Exception(f"Binance order failed: {binance_order}")
            
            executed_qty = float(binance_order.get('executedQty', 0))
            if executed_qty <= 0:
                raise Exception("No volume executed on Binance")
            
            trade_result['steps'].append({
                'step': 'binance_buy',
                'order': binance_order,
                'volume': executed_qty,
                'usdt_spent': trade_volume_usdt,
                'timestamp': datetime.now()
            })
            
            logger.info(f"Step 2: Getting Upbit deposit address for {coin}")
            upbit_address = await self.upbit.get_deposit_address(coin)
            
            withdrawal_fee = self.config['fee_data']['binance']['withdraw'].get(coin, 0)
            withdrawal_amount = executed_qty - withdrawal_fee
            
            logger.info(f"Step 3: Withdrawing {withdrawal_amount} {coin} from Binance to Upbit")
            withdrawal = await self.binance.withdraw(
                coin,
                withdrawal_amount,
                upbit_address['address'],
                tag=upbit_address.get('secondary_address')
            )
            
            trade_result['steps'].append({
                'step': 'binance_withdraw',
                'withdrawal': withdrawal,
                'amount': withdrawal_amount,
                'timestamp': datetime.now()
            })
            
            logger.info(f"Step 4: Waiting for deposit confirmation on Upbit")
            deposit_confirmed = await self._wait_for_deposit(
                'upbit',
                coin,
                withdrawal.get('id', ''),
                timeout=3600
            )
            
            if not deposit_confirmed:
                raise Exception("Deposit confirmation timeout")
            
            trade_result['steps'].append({
                'step': 'upbit_deposit_confirmed',
                'timestamp': datetime.now()
            })
            
            logger.info(f"Step 5: Selling {coin} on Upbit")
            upbit_balance = await self.upbit.get_balance(coin)
            sell_amount = upbit_balance['free'] * 0.999
            
            upbit_order = await self.upbit.create_market_order(coin, 'SELL', volume=sell_amount)
            
            usdt_received = float(upbit_order.get('price', 0))
            
            trade_result['steps'].append({
                'step': 'upbit_sell',
                'order': upbit_order,
                'amount': sell_amount,
                'usdt_received': usdt_received,
                'timestamp': datetime.now()
            })
            
            trade_result['status'] = 'completed'
            trade_result['end_time'] = datetime.now()
            trade_result['profit'] = usdt_received - trade_volume_usdt
            
            self.trade_history.append(trade_result)
            logger.info(f"Axis 2 trade completed successfully. Profit: {trade_result['profit']} USDT")
            
        except Exception as e:
            logger.error(f"Axis 2 trade failed: {e}")
            trade_result['status'] = 'failed'
            trade_result['error'] = str(e)
            trade_result['end_time'] = datetime.now()
            self.trade_history.append(trade_result)
            
        return trade_result
    
    async def _wait_for_deposit(self, exchange: str, coin: str, tx_id: str, timeout: int = 3600) -> bool:
        start_time = time.time()
        check_interval = 30
        
        while time.time() - start_time < timeout:
            try:
                if exchange == 'binance':
                    deposit = await self.binance.check_deposit_status(tx_id, coin)
                else:
                    deposit = await self.upbit.check_deposit_status(tx_id, coin)
                
                if deposit and deposit.get('status') in ['completed', 'success', 1]:
                    logger.info(f"Deposit confirmed on {exchange}")
                    return True
                    
            except Exception as e:
                logger.error(f"Error checking deposit status: {e}")
            
            await asyncio.sleep(check_interval)
            
        return False
    
    def _calculate_profit(self, trade_result: Dict) -> float:
        try:
            usdt_spent = 0
            usdt_received = 0
            
            for step in trade_result['steps']:
                if 'usdt_spent' in step:
                    usdt_spent += step['usdt_spent']
                if 'usdt_received' in step:
                    usdt_received += step['usdt_received']
            
            return usdt_received - usdt_spent
                
        except Exception as e:
            logger.error(f"Error calculating profit: {e}")
            return 0.0
    
    def can_execute_trade(self, trade_volume_usdt: float) -> Tuple[bool, str]:
        if len(self.active_trades) >= self.config['risk_management']['max_open_positions']:
            return False, "Maximum open positions reached"
        
        if self.daily_loss >= self.config['risk_management']['daily_loss_limit_usdt']:
            return False, "Daily loss limit reached"
        
        if trade_volume_usdt < self.config['min_trade_volume_usdt']:
            return False, "Trade volume below minimum"
        
        if trade_volume_usdt > self.config['max_trade_volume_usdt']:
            return False, "Trade volume above maximum"
        
        return True, "OK"