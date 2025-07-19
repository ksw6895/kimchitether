import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from loguru import logger
from exchanges.binance_client import BinanceClient
from exchanges.upbit_client import UpbitClient


class RiskManager:
    def __init__(self, binance_client: BinanceClient, upbit_client: UpbitClient, config: Dict):
        self.binance = binance_client
        self.upbit = upbit_client
        self.config = config
        self.positions = {}
        self.daily_trades = []
        self.daily_pnl = 0.0
        self.last_reset = datetime.now()
        
    def reset_daily_stats(self):
        current_time = datetime.now()
        if current_time.date() > self.last_reset.date():
            self.daily_trades = []
            self.daily_pnl = 0.0
            self.last_reset = current_time
            logger.info("Daily stats reset")
    
    async def check_balances(self) -> Tuple[Dict, Dict]:
        try:
            tasks = [
                self.binance.get_balance('USDT'),
                self.upbit.get_balance('USDT')
            ]
            
            binance_usdt, upbit_usdt = await asyncio.gather(*tasks)
            
            return {
                'binance': binance_usdt,
                'upbit': upbit_usdt
            }
        except Exception as e:
            logger.error(f"Failed to check balances: {e}")
            return {}, {}
    
    async def validate_trade(self, coin: str, axis: int, volume_usdt: float) -> Tuple[bool, str]:
        self.reset_daily_stats()
        
        balances = await self.check_balances()
        
        min_balance = self.config['risk_management']['min_balance_usdt']
        if axis == 1:
            if balances.get('upbit', {}).get('total', 0) < volume_usdt + min_balance:
                return False, "Insufficient USDT balance on Upbit"
        else:
            if balances.get('binance', {}).get('total', 0) < volume_usdt + min_balance:
                return False, "Insufficient USDT balance on Binance"
        
        open_positions = len([p for p in self.positions.values() if p['status'] == 'open'])
        max_positions = self.config['risk_management']['max_open_positions']
        if open_positions >= max_positions:
            return False, f"Maximum open positions ({max_positions}) reached"
        
        if self.daily_pnl < -self.config['risk_management']['daily_loss_limit_usdt']:
            return False, "Daily loss limit reached"
        
        total_exposure = sum(p['volume_usdt'] for p in self.positions.values() if p['status'] == 'open')
        total_balance = balances.get('binance', {}).get('total', 0) + balances.get('upbit', {}).get('total', 0)
        
        if total_balance > 0:
            exposure_percent = (total_exposure + volume_usdt) / total_balance * 100
            max_exposure = self.config['risk_management']['max_position_size_percent']
            
            if exposure_percent > max_exposure:
                return False, f"Maximum position size ({max_exposure}%) would be exceeded"
        
        if volume_usdt < self.config['min_trade_volume_usdt']:
            return False, f"Trade volume below minimum ({self.config['min_trade_volume_usdt']} USDT)"
        
        if volume_usdt > self.config['max_trade_volume_usdt']:
            return False, f"Trade volume above maximum ({self.config['max_trade_volume_usdt']} USDT)"
        
        return True, "Trade validated"
    
    def open_position(self, trade_id: str, coin: str, axis: int, volume_usdt: float, entry_price: float):
        self.positions[trade_id] = {
            'coin': coin,
            'axis': axis,
            'volume_usdt': volume_usdt,
            'entry_price': entry_price,
            'open_time': datetime.now(),
            'status': 'open'
        }
        logger.info(f"Position opened: {trade_id}")
    
    def close_position(self, trade_id: str, exit_price: float, profit: float):
        if trade_id in self.positions:
            self.positions[trade_id]['status'] = 'closed'
            self.positions[trade_id]['exit_price'] = exit_price
            self.positions[trade_id]['close_time'] = datetime.now()
            self.positions[trade_id]['profit'] = profit
            
            self.daily_pnl += profit
            self.daily_trades.append(trade_id)
            
            logger.info(f"Position closed: {trade_id}, Profit: {profit:.2f} USDT")
    
    def get_position_status(self, trade_id: str) -> Optional[Dict]:
        return self.positions.get(trade_id)
    
    def should_stop_loss(self, trade_id: str, current_price: float) -> bool:
        position = self.positions.get(trade_id)
        if not position or position['status'] != 'open':
            return False
        
        entry_price = position['entry_price']
        stop_loss_percent = self.config['risk_management']['stop_loss_percent']
        
        if position['axis'] == 1:
            loss_percent = (entry_price - current_price) / entry_price * 100
        else:
            loss_percent = (current_price - entry_price) / entry_price * 100
        
        if loss_percent >= stop_loss_percent:
            logger.warning(f"Stop loss triggered for {trade_id}: {loss_percent:.2f}%")
            return True
        
        return False
    
    def get_daily_stats(self) -> Dict:
        self.reset_daily_stats()
        
        return {
            'trades_count': len(self.daily_trades),
            'pnl': self.daily_pnl,
            'open_positions': len([p for p in self.positions.values() if p['status'] == 'open']),
            'last_reset': self.last_reset
        }
    
    async def emergency_stop(self):
        logger.error("Emergency stop triggered!")
        
        open_positions = [p for p in self.positions.values() if p['status'] == 'open']
        
        for position in open_positions:
            try:
                if position['axis'] == 1:
                    balance = await self.binance.get_balance(position['coin'])
                    if balance['free'] > 0:
                        await self.binance.create_market_order(
                            position['coin'], 
                            'SELL', 
                            quantity=balance['free']
                        )
                else:
                    balance = await self.upbit.get_balance(position['coin'])
                    if balance['free'] > 0:
                        await self.upbit.create_market_order(
                            position['coin'], 
                            'SELL', 
                            volume=balance['free']
                        )
                
                position['status'] = 'emergency_closed'
                logger.info(f"Emergency closed position: {position}")
                
            except Exception as e:
                logger.error(f"Failed to emergency close position: {e}")
    
    def get_risk_metrics(self) -> Dict:
        total_positions = len(self.positions)
        open_positions = len([p for p in self.positions.values() if p['status'] == 'open'])
        closed_positions = len([p for p in self.positions.values() if p['status'] == 'closed'])
        
        total_profit = sum(p.get('profit', 0) for p in self.positions.values() if p['status'] == 'closed')
        winning_trades = len([p for p in self.positions.values() if p['status'] == 'closed' and p.get('profit', 0) > 0])
        losing_trades = len([p for p in self.positions.values() if p['status'] == 'closed' and p.get('profit', 0) < 0])
        
        win_rate = (winning_trades / closed_positions * 100) if closed_positions > 0 else 0
        
        return {
            'total_positions': total_positions,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'total_profit': total_profit,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'daily_pnl': self.daily_pnl
        }