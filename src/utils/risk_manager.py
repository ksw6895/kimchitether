from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
from loguru import logger
import asyncio

from ..utils.premium_calculator import ArbitrageOpportunity


@dataclass
class RiskLimits:
    max_single_trade_krw: Decimal
    max_daily_volume_krw: Decimal
    max_concurrent_trades: int
    max_slippage_percent: Decimal
    emergency_stop_loss_percent: Decimal
    min_exchange_balance_krw: Decimal
    max_exposure_percent: Decimal  # Max % of total capital in single trade


@dataclass
class TradingMetrics:
    daily_volume_krw: Decimal
    daily_profit_krw: Decimal
    daily_loss_krw: Decimal
    total_trades: int
    successful_trades: int
    failed_trades: int
    current_exposure_krw: Decimal
    last_updated: datetime


class RiskManager:
    def __init__(self, risk_limits: RiskLimits):
        self.limits = risk_limits
        self.active_trades = {}
        self.daily_metrics = TradingMetrics(
            daily_volume_krw=Decimal("0"),
            daily_profit_krw=Decimal("0"),
            daily_loss_krw=Decimal("0"),
            total_trades=0,
            successful_trades=0,
            failed_trades=0,
            current_exposure_krw=Decimal("0"),
            last_updated=datetime.now()
        )
        self.last_reset_date = datetime.now().date()
        self._lock = asyncio.Lock()
        
    async def can_execute_trade(self, opportunity: ArbitrageOpportunity) -> tuple[bool, str]:
        async with self._lock:
            # Reset daily metrics if new day
            await self._check_daily_reset()
            
            # Check concurrent trades limit
            if len(self.active_trades) >= self.limits.max_concurrent_trades:
                return False, f"Maximum concurrent trades reached ({self.limits.max_concurrent_trades})"
                
            # Check single trade size
            if opportunity.trade_amount_krw > self.limits.max_single_trade_krw:
                return False, f"Trade amount exceeds single trade limit ({self.limits.max_single_trade_krw:,.0f} KRW)"
                
            # Check daily volume limit
            if self.daily_metrics.daily_volume_krw + opportunity.trade_amount_krw > self.limits.max_daily_volume_krw:
                return False, f"Trade would exceed daily volume limit ({self.limits.max_daily_volume_krw:,.0f} KRW)"
                
            # Check exposure limit
            new_exposure = self.daily_metrics.current_exposure_krw + opportunity.trade_amount_krw
            if new_exposure > self._get_max_exposure():
                return False, f"Trade would exceed maximum exposure limit"
                
            # Check if exchange rate is available
            if opportunity.net_profit_rate <= 0:
                return False, "Trade opportunity no longer profitable"
                
            # All checks passed
            return True, "Trade approved"
            
    async def register_trade_start(self, trade_id: str, opportunity: ArbitrageOpportunity):
        async with self._lock:
            self.active_trades[trade_id] = {
                'opportunity': opportunity,
                'start_time': datetime.now(),
                'status': 'active'
            }
            self.daily_metrics.current_exposure_krw += opportunity.trade_amount_krw
            self.daily_metrics.total_trades += 1
            
    async def register_trade_complete(self, trade_id: str, profit_krw: Decimal, success: bool):
        async with self._lock:
            if trade_id not in self.active_trades:
                logger.warning(f"Trade {trade_id} not found in active trades")
                return
                
            trade = self.active_trades.pop(trade_id)
            
            # Update metrics
            self.daily_metrics.current_exposure_krw -= trade['opportunity'].trade_amount_krw
            self.daily_metrics.daily_volume_krw += trade['opportunity'].trade_amount_krw
            
            if success:
                self.daily_metrics.successful_trades += 1
                if profit_krw > 0:
                    self.daily_metrics.daily_profit_krw += profit_krw
                else:
                    self.daily_metrics.daily_loss_krw += abs(profit_krw)
            else:
                self.daily_metrics.failed_trades += 1
                self.daily_metrics.daily_loss_krw += abs(profit_krw)
                
            self.daily_metrics.last_updated = datetime.now()
            
    async def check_emergency_stop(self) -> tuple[bool, str]:
        async with self._lock:
            # Check if daily loss exceeds emergency stop threshold
            if self.daily_metrics.daily_volume_krw > 0:
                loss_rate = (self.daily_metrics.daily_loss_krw / self.daily_metrics.daily_volume_krw) * 100
                if loss_rate > self.limits.emergency_stop_loss_percent:
                    return True, f"Emergency stop triggered: Daily loss {loss_rate:.2f}% exceeds limit"
                    
            # Check failure rate
            if self.daily_metrics.total_trades > 10:  # Only check after some trades
                failure_rate = (self.daily_metrics.failed_trades / self.daily_metrics.total_trades) * 100
                if failure_rate > 50:  # More than 50% failure rate
                    return True, f"Emergency stop triggered: High failure rate {failure_rate:.1f}%"
                    
            return False, "System operating normally"
            
    async def get_trading_metrics(self) -> Dict:
        async with self._lock:
            await self._check_daily_reset()
            
            net_profit = self.daily_metrics.daily_profit_krw - self.daily_metrics.daily_loss_krw
            success_rate = 0
            if self.daily_metrics.total_trades > 0:
                success_rate = (self.daily_metrics.successful_trades / self.daily_metrics.total_trades) * 100
                
            return {
                'daily_volume_krw': self.daily_metrics.daily_volume_krw,
                'daily_profit_krw': self.daily_metrics.daily_profit_krw,
                'daily_loss_krw': self.daily_metrics.daily_loss_krw,
                'net_profit_krw': net_profit,
                'total_trades': self.daily_metrics.total_trades,
                'successful_trades': self.daily_metrics.successful_trades,
                'failed_trades': self.daily_metrics.failed_trades,
                'success_rate': success_rate,
                'current_exposure_krw': self.daily_metrics.current_exposure_krw,
                'active_trades': len(self.active_trades),
                'last_updated': self.daily_metrics.last_updated.isoformat()
            }
            
    async def validate_exchange_balances(self, upbit_krw: Decimal, binance_usdt: Decimal,
                                       usd_krw_rate: Optional[Decimal]) -> tuple[bool, str]:
        # Check if exchange rate is available
        if usd_krw_rate is None:
            return False, "Cannot validate balances: Exchange rate unavailable"
            
        # Convert Binance USDT to KRW equivalent
        binance_krw_equivalent = binance_usdt * usd_krw_rate
        
        # Check minimum balance requirements
        if upbit_krw < self.limits.min_exchange_balance_krw:
            return False, f"Insufficient Upbit KRW balance: {upbit_krw:,.0f} < {self.limits.min_exchange_balance_krw:,.0f}"
            
        if binance_krw_equivalent < self.limits.min_exchange_balance_krw:
            return False, f"Insufficient Binance balance: {binance_krw_equivalent:,.0f} KRW equivalent"
            
        return True, "Balances sufficient"
        
    async def calculate_safe_trade_amount(self, opportunity: ArbitrageOpportunity,
                                        available_krw: Decimal,
                                        available_usdt: Decimal,
                                        usd_krw_rate: Optional[Decimal]) -> Decimal:
        if usd_krw_rate is None:
            return Decimal("0")
            
        # Convert USDT to KRW
        available_usdt_krw = available_usdt * usd_krw_rate
        
        # Start with the opportunity's suggested amount
        safe_amount = opportunity.trade_amount_krw
        
        # Apply various constraints
        safe_amount = min(safe_amount, self.limits.max_single_trade_krw)
        safe_amount = min(safe_amount, available_krw * Decimal("0.9"))  # Use max 90% of available
        safe_amount = min(safe_amount, available_usdt_krw * Decimal("0.9"))
        
        # Ensure we don't exceed daily limit
        remaining_daily = self.limits.max_daily_volume_krw - self.daily_metrics.daily_volume_krw
        safe_amount = min(safe_amount, remaining_daily)
        
        # Ensure we don't exceed exposure limit
        max_new_exposure = self._get_max_exposure() - self.daily_metrics.current_exposure_krw
        safe_amount = min(safe_amount, max_new_exposure)
        
        # Round down to nearest 10,000 KRW
        safe_amount = (safe_amount // 10000) * 10000
        
        return safe_amount
        
    def _get_max_exposure(self) -> Decimal:
        # Maximum exposure should be a percentage of daily volume limit
        return self.limits.max_daily_volume_krw * (self.limits.max_exposure_percent / 100)
        
    async def _check_daily_reset(self):
        current_date = datetime.now().date()
        if current_date > self.last_reset_date:
            logger.info(f"Resetting daily metrics for {current_date}")
            self.daily_metrics = TradingMetrics(
                daily_volume_krw=Decimal("0"),
                daily_profit_krw=Decimal("0"),
                daily_loss_krw=Decimal("0"),
                total_trades=0,
                successful_trades=0,
                failed_trades=0,
                current_exposure_krw=self.daily_metrics.current_exposure_krw,  # Keep active trades
                last_updated=datetime.now()
            )
            self.last_reset_date = current_date
            
    async def check_slippage(self, expected_price: Decimal, actual_price: Decimal,
                           side: str) -> tuple[bool, Decimal]:
        """Check if slippage is within acceptable limits"""
        if side.upper() == "BUY":
            # For buy orders, actual price should not be much higher than expected
            slippage = ((actual_price - expected_price) / expected_price) * 100
        else:  # SELL
            # For sell orders, actual price should not be much lower than expected
            slippage = ((expected_price - actual_price) / expected_price) * 100
            
        if slippage > self.limits.max_slippage_percent:
            return False, slippage
            
        return True, slippage
        
    def get_risk_parameters(self) -> Dict:
        return {
            'max_single_trade_krw': self.limits.max_single_trade_krw,
            'max_daily_volume_krw': self.limits.max_daily_volume_krw,
            'max_concurrent_trades': self.limits.max_concurrent_trades,
            'max_slippage_percent': self.limits.max_slippage_percent,
            'emergency_stop_loss_percent': self.limits.emergency_stop_loss_percent,
            'min_exchange_balance_krw': self.limits.min_exchange_balance_krw,
            'max_exposure_percent': self.limits.max_exposure_percent
        }