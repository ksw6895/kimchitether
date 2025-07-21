"""Performance analyzer for paper trading results"""
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
from collections import defaultdict
from loguru import logger

from src.simulation.virtual_balance_manager import SimulatedTrade, SimulatedTransfer


@dataclass
class PerformanceMetrics:
    """Performance metrics for paper trading"""
    total_trades: int
    successful_trades: int
    failed_trades: int
    win_rate: float
    total_profit_krw: Decimal
    total_fees_krw: Decimal
    net_profit_krw: Decimal
    average_profit_per_trade: Decimal
    best_trade_profit: Decimal
    worst_trade_loss: Decimal
    total_volume_krw: Decimal
    roi_percent: float
    sharpe_ratio: float
    max_drawdown_percent: float
    trades_by_coin: Dict[str, int]
    profit_by_coin: Dict[str, Decimal]
    daily_returns: List[Tuple[datetime, Decimal]]


class PerformanceAnalyzer:
    """Analyzes paper trading performance"""
    
    def __init__(self, balance_manager, exchange_rate_provider):
        """
        Initialize performance analyzer
        
        Args:
            balance_manager: Virtual balance manager instance
            exchange_rate_provider: Exchange rate provider for conversions
        """
        self.balance_manager = balance_manager
        self.exchange_rate_provider = exchange_rate_provider
        
    def analyze_performance(self, initial_capital_krw: Decimal) -> PerformanceMetrics:
        """
        Analyze overall trading performance
        
        Args:
            initial_capital_krw: Initial capital in KRW
            
        Returns:
            PerformanceMetrics object with detailed analysis
        """
        trades = self.balance_manager.trades
        transfers = self.balance_manager.transfers
        
        if not trades:
            return self._empty_metrics()
            
        # Group trades by arbitrage opportunities
        arbitrage_trades = self._group_arbitrage_trades(trades, transfers)
        
        # Calculate metrics
        total_trades = len(arbitrage_trades)
        successful_trades = 0
        total_profit_krw = Decimal("0")
        total_fees_krw = Decimal("0")
        total_volume_krw = Decimal("0")
        
        profits = []
        trades_by_coin = defaultdict(int)
        profit_by_coin = defaultdict(Decimal)
        
        for arb_trade in arbitrage_trades:
            profit, fees, volume = self._calculate_arbitrage_profit(arb_trade)
            
            if profit > 0:
                successful_trades += 1
                
            total_profit_krw += profit
            total_fees_krw += fees
            total_volume_krw += volume
            profits.append(profit)
            
            # Track by coin
            coin = self._extract_coin_from_trades(arb_trade['trades'])
            trades_by_coin[coin] += 1
            profit_by_coin[coin] += profit
            
        # Calculate aggregate metrics
        win_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0
        net_profit_krw = total_profit_krw - total_fees_krw
        avg_profit = net_profit_krw / total_trades if total_trades > 0 else Decimal("0")
        
        best_trade = max(profits) if profits else Decimal("0")
        worst_trade = min(profits) if profits else Decimal("0")
        
        # Calculate ROI based on net profit
        # ROI should be net profit / initial capital
        roi_percent = float((net_profit_krw / initial_capital_krw) * 100) if initial_capital_krw > 0 else 0
        
        # Calculate risk metrics
        daily_returns = self._calculate_daily_returns(trades, initial_capital_krw)
        sharpe_ratio = self._calculate_sharpe_ratio(daily_returns)
        max_drawdown = self._calculate_max_drawdown(daily_returns, initial_capital_krw)
        
        return PerformanceMetrics(
            total_trades=total_trades,
            successful_trades=successful_trades,
            failed_trades=total_trades - successful_trades,
            win_rate=win_rate,
            total_profit_krw=total_profit_krw,
            total_fees_krw=total_fees_krw,
            net_profit_krw=net_profit_krw,
            average_profit_per_trade=avg_profit,
            best_trade_profit=best_trade,
            worst_trade_loss=worst_trade,
            total_volume_krw=total_volume_krw,
            roi_percent=roi_percent,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_percent=max_drawdown,
            trades_by_coin=dict(trades_by_coin),
            profit_by_coin=dict(profit_by_coin),
            daily_returns=daily_returns
        )
        
    def generate_report(self, metrics: PerformanceMetrics, format: str = "text") -> str:
        """
        Generate performance report
        
        Args:
            metrics: Performance metrics
            format: Output format ("text" or "json")
            
        Returns:
            Formatted report string
        """
        if format == "json":
            return self._generate_json_report(metrics)
        else:
            return self._generate_text_report(metrics)
            
    def _group_arbitrage_trades(self, trades: List[SimulatedTrade], 
                               transfers: List[SimulatedTransfer]) -> List[Dict]:
        """Group trades and transfers into complete arbitrage opportunities"""
        # Simple grouping by timestamp proximity (within 5 minutes)
        arbitrage_trades = []
        used_trades = set()
        
        for i, trade in enumerate(trades):
            if i in used_trades:
                continue
                
            # Find related trades within 5 minutes
            arb_group = {
                'trades': [trade],
                'transfers': []
            }
            
            for j, other_trade in enumerate(trades[i+1:], i+1):
                if j in used_trades:
                    continue
                    
                time_diff = abs((other_trade.timestamp - trade.timestamp).total_seconds())
                if time_diff <= 300:  # 5 minutes
                    arb_group['trades'].append(other_trade)
                    used_trades.add(j)
                    
            # Find related transfers
            for transfer in transfers:
                time_diff = abs((transfer.timestamp - trade.timestamp).total_seconds())
                if time_diff <= 600:  # 10 minutes
                    arb_group['transfers'].append(transfer)
                    
            arbitrage_trades.append(arb_group)
            used_trades.add(i)
            
        return arbitrage_trades
        
    def _calculate_arbitrage_profit(self, arb_trade: Dict) -> Tuple[Decimal, Decimal, Decimal]:
        """Calculate profit, fees, and volume for an arbitrage trade"""
        trades = arb_trade['trades']
        transfers = arb_trade['transfers']
        
        total_buy_cost = Decimal("0")
        total_sell_revenue = Decimal("0")
        total_fees = Decimal("0")
        total_volume = Decimal("0")
        
        for trade in trades:
            if trade.side.lower() == "buy":
                total_buy_cost += trade.total_cost
            else:
                total_sell_revenue += trade.total_cost
                
            total_fees += trade.fee
            total_volume += trade.total_cost
            
        # Add transfer fees
        for transfer in transfers:
            total_fees += transfer.fee
            
        # Convert to KRW if needed
        usd_krw_rate = self.exchange_rate_provider.get_usd_krw_rate()
        
        # Simple profit calculation (assuming proper currency conversions in trades)
        profit = total_sell_revenue - total_buy_cost - total_fees
        
        return profit, total_fees, total_volume
        
    def _calculate_current_portfolio_value(self) -> Decimal:
        """Calculate current total portfolio value in KRW"""
        total_values = self.balance_manager.get_total_value_krw(self.exchange_rate_provider)
        return sum(total_values.values())
        
    def _calculate_daily_returns(self, trades: List[SimulatedTrade], 
                                initial_capital: Decimal) -> List[Tuple[datetime, Decimal]]:
        """Calculate daily returns"""
        if not trades:
            return []
            
        # Group trades by date
        trades_by_date = defaultdict(list)
        for trade in trades:
            date = trade.timestamp.date()
            trades_by_date[date].append(trade)
            
        # Calculate cumulative returns by date
        daily_returns = []
        cumulative_profit = Decimal("0")
        
        for date in sorted(trades_by_date.keys()):
            day_trades = trades_by_date[date]
            day_profit = Decimal("0")
            
            for trade in day_trades:
                # Simplified profit calculation
                if trade.side.lower() == "sell":
                    day_profit += trade.total_cost - trade.fee
                else:
                    day_profit -= trade.total_cost + trade.fee
                    
            cumulative_profit += day_profit
            daily_return = cumulative_profit / initial_capital
            daily_returns.append((datetime.combine(date, datetime.min.time()), daily_return))
            
        return daily_returns
        
    def _calculate_sharpe_ratio(self, daily_returns: List[Tuple[datetime, Decimal]]) -> float:
        """Calculate Sharpe ratio (simplified version)"""
        if len(daily_returns) < 2:
            return 0.0
            
        returns = [float(r[1]) for r in daily_returns]
        
        # Calculate average return
        avg_return = sum(returns) / len(returns)
        
        # Calculate standard deviation
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5
        
        # Sharpe ratio (assuming 0% risk-free rate)
        if std_dev == 0:
            return 0.0
            
        # Annualize (assuming 365 trading days)
        return (avg_return * 365 ** 0.5) / std_dev
        
    def _calculate_max_drawdown(self, daily_returns: List[Tuple[datetime, Decimal]], 
                               initial_capital: Decimal) -> float:
        """Calculate maximum drawdown percentage"""
        if not daily_returns:
            return 0.0
            
        peak_value = initial_capital
        max_drawdown = Decimal("0")
        
        for date, cumulative_return in daily_returns:
            current_value = initial_capital * (1 + cumulative_return)
            
            if current_value > peak_value:
                peak_value = current_value
            else:
                drawdown = (peak_value - current_value) / peak_value
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    
        return float(max_drawdown * 100)
        
    def _extract_coin_from_trades(self, trades: List[SimulatedTrade]) -> str:
        """Extract coin symbol from trades"""
        for trade in trades:
            if trade.exchange == "binance" and trade.symbol.endswith("USDT"):
                return trade.symbol[:-4]
            elif trade.exchange == "upbit" and "-" in trade.symbol:
                # Upbit format is KRW-BTC, so coin is the second part
                parts = trade.symbol.split("-")
                if len(parts) == 2 and parts[0] == "KRW":
                    return parts[1]
                
        return "UNKNOWN"
        
    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics when no trades"""
        return PerformanceMetrics(
            total_trades=0,
            successful_trades=0,
            failed_trades=0,
            win_rate=0.0,
            total_profit_krw=Decimal("0"),
            total_fees_krw=Decimal("0"),
            net_profit_krw=Decimal("0"),
            average_profit_per_trade=Decimal("0"),
            best_trade_profit=Decimal("0"),
            worst_trade_loss=Decimal("0"),
            total_volume_krw=Decimal("0"),
            roi_percent=0.0,
            sharpe_ratio=0.0,
            max_drawdown_percent=0.0,
            trades_by_coin={},
            profit_by_coin={},
            daily_returns=[]
        )
        
    def _generate_text_report(self, metrics: PerformanceMetrics) -> str:
        """Generate text format report"""
        report = []
        report.append("=" * 60)
        report.append("PAPER TRADING PERFORMANCE REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Trading Summary
        report.append("TRADING SUMMARY:")
        report.append(f"  Total Trades: {metrics.total_trades}")
        report.append(f"  Successful Trades: {metrics.successful_trades}")
        report.append(f"  Failed Trades: {metrics.failed_trades}")
        report.append(f"  Win Rate: {metrics.win_rate:.1f}%")
        report.append("")
        
        # Financial Performance
        report.append("FINANCIAL PERFORMANCE:")
        report.append(f"  Total Volume: {metrics.total_volume_krw:,.0f} KRW")
        report.append(f"  Total Profit: {metrics.total_profit_krw:,.0f} KRW")
        report.append(f"  Total Fees: {metrics.total_fees_krw:,.0f} KRW")
        report.append(f"  Net Profit: {metrics.net_profit_krw:,.0f} KRW")
        report.append(f"  ROI: {metrics.roi_percent:.2f}%")
        report.append("")
        
        # Trade Statistics
        report.append("TRADE STATISTICS:")
        report.append(f"  Average Profit per Trade: {metrics.average_profit_per_trade:,.0f} KRW")
        report.append(f"  Best Trade: {metrics.best_trade_profit:,.0f} KRW")
        report.append(f"  Worst Trade: {metrics.worst_trade_loss:,.0f} KRW")
        report.append("")
        
        # Risk Metrics
        report.append("RISK METRICS:")
        report.append(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        report.append(f"  Max Drawdown: {metrics.max_drawdown_percent:.2f}%")
        report.append("")
        
        # Performance by Coin
        if metrics.trades_by_coin:
            report.append("PERFORMANCE BY COIN:")
            for coin, count in sorted(metrics.trades_by_coin.items()):
                profit = metrics.profit_by_coin.get(coin, Decimal("0"))
                report.append(f"  {coin}: {count} trades, {profit:,.0f} KRW profit")
            report.append("")
            
        report.append("=" * 60)
        
        return "\n".join(report)
        
    def _generate_json_report(self, metrics: PerformanceMetrics) -> str:
        """Generate JSON format report"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "trading_summary": {
                "total_trades": metrics.total_trades,
                "successful_trades": metrics.successful_trades,
                "failed_trades": metrics.failed_trades,
                "win_rate_percent": metrics.win_rate
            },
            "financial_performance": {
                "total_volume_krw": float(metrics.total_volume_krw),
                "total_profit_krw": float(metrics.total_profit_krw),
                "total_fees_krw": float(metrics.total_fees_krw),
                "net_profit_krw": float(metrics.net_profit_krw),
                "roi_percent": metrics.roi_percent
            },
            "trade_statistics": {
                "average_profit_per_trade_krw": float(metrics.average_profit_per_trade),
                "best_trade_profit_krw": float(metrics.best_trade_profit),
                "worst_trade_loss_krw": float(metrics.worst_trade_loss)
            },
            "risk_metrics": {
                "sharpe_ratio": metrics.sharpe_ratio,
                "max_drawdown_percent": metrics.max_drawdown_percent
            },
            "performance_by_coin": {
                coin: {
                    "trades": count,
                    "profit_krw": float(metrics.profit_by_coin.get(coin, 0))
                }
                for coin, count in metrics.trades_by_coin.items()
            },
            "daily_returns": [
                {
                    "date": date.isoformat(),
                    "cumulative_return": float(ret)
                }
                for date, ret in metrics.daily_returns
            ]
        }
        
        return json.dumps(report_data, indent=2)