import asyncio
import sys
import signal
from decimal import Decimal
from datetime import datetime
import threading
from loguru import logger
from typing import Dict, List

from config.config import config
from src.api.binance_client import BinanceClient
from src.api.upbit_client import UpbitClient
from src.utils.exchange_rate import ExchangeRateProvider
from src.utils.premium_calculator import PremiumCalculator
from src.utils.risk_manager import RiskManager
from src.strategies.forward_arbitrage import ForwardArbitrageStrategy
from src.strategies.reverse_arbitrage import ReverseArbitrageStrategy
from src.monitoring.dashboard import TradingDashboard


class ArbitrageTradingBot:
    def __init__(self):
        # Validate configuration
        try:
            config.validate_config()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
            
        # Setup logging
        logger.remove()
        logger.add(sys.stdout, level=config.log_level)
        logger.add(config.log_file, rotation="1 day", retention="7 days", level=config.log_level)
        
        logger.info("Initializing Arbitrage Trading Bot...")
        
        # Initialize components
        self.binance = BinanceClient(
            config.binance_api_key,
            config.binance_secret_key,
            testnet=config.testnet
        )
        self.upbit = UpbitClient(
            config.upbit_access_key,
            config.upbit_secret_key
        )
        self.exchange_rate = ExchangeRateProvider(
            cache_duration=config.exchange_rate_cache_duration
        )
        self.premium_calculator = PremiumCalculator(
            self.binance,
            self.upbit,
            self.exchange_rate
        )
        self.risk_manager = RiskManager(config.get_risk_limits())
        
        # Initialize strategies
        self.forward_strategy = ForwardArbitrageStrategy(
            self.binance,
            self.upbit,
            max_slippage=config.max_slippage_percent / 100,
            transfer_timeout_minutes=config.transfer_timeout_minutes
        )
        self.reverse_strategy = ReverseArbitrageStrategy(
            self.binance,
            self.upbit,
            max_slippage=config.max_slippage_percent / 100,
            transfer_timeout_minutes=config.transfer_timeout_minutes
        )
        
        # Initialize dashboard
        self.dashboard = None
        if config.enable_dashboard:
            self.dashboard = TradingDashboard(port=config.dashboard_port)
            
        self.running = False
        self.tasks = []
        self.monitor_coins = []  # Dynamic coin list
        
    async def start(self):
        """Start the trading bot"""
        logger.info("Starting trading bot...")
        self.running = True
        
        # Start dashboard in separate thread
        if self.dashboard:
            dashboard_thread = threading.Thread(
                target=self.dashboard.run,
                kwargs={'debug': False}
            )
            dashboard_thread.daemon = True
            dashboard_thread.start()
            logger.info(f"Dashboard started on port {config.dashboard_port}")
            
        # Initialize dynamic coin list
        await self._initialize_coin_list()
        
        # Check initial balances
        await self._check_balances()
        
        # Start monitoring tasks
        self.tasks = [
            asyncio.create_task(self._monitor_premiums()),
            asyncio.create_task(self._check_arbitrage_opportunities()),
            asyncio.create_task(self._update_metrics()),
            asyncio.create_task(self._monitor_system_health()),
        ]
        
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("Trading bot stopped.")
            
    async def stop(self):
        """Stop the trading bot"""
        logger.info("Stopping trading bot...")
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
            
        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
    async def _initialize_coin_list(self):
        """Initialize the dynamic coin list"""
        try:
            # Get Binance USDT markets first
            binance_usdt_markets = self.binance.get_usdt_markets()
            
            # Get Upbit KRW markets that also exist on Binance
            self.monitor_coins = self.upbit.get_tradable_markets_with_binance(binance_usdt_markets)
            
            # If config has specific coins, use intersection
            if config.monitor_coins:
                configured_coins = set(config.monitor_coins)
                self.monitor_coins = [coin for coin in self.monitor_coins if coin in configured_coins]
                logger.info(f"Using configured coins that exist on both exchanges: {self.monitor_coins}")
            else:
                logger.info(f"Monitoring all {len(self.monitor_coins)} coins available on both exchanges")
                
            # Update coin list periodically
            asyncio.create_task(self._update_coin_list_periodically())
            
        except Exception as e:
            logger.error(f"Failed to initialize coin list: {e}")
            # Fallback to config coins
            self.monitor_coins = config.monitor_coins
            logger.warning(f"Using fallback coin list from config: {self.monitor_coins}")
            
    async def _update_coin_list_periodically(self):
        """Update coin list every 30 minutes"""
        while self.running:
            await asyncio.sleep(1800)  # 30 minutes
            try:
                binance_usdt_markets = self.binance.get_usdt_markets(force_refresh=True)
                new_coins = self.upbit.get_tradable_markets_with_binance(binance_usdt_markets)
                
                # Check for new coins
                added = set(new_coins) - set(self.monitor_coins)
                removed = set(self.monitor_coins) - set(new_coins)
                
                if added:
                    logger.info(f"New coins added to monitoring: {added}")
                if removed:
                    logger.warning(f"Coins removed from monitoring: {removed}")
                    
                # Update the list
                if config.monitor_coins:
                    configured_coins = set(config.monitor_coins)
                    self.monitor_coins = [coin for coin in new_coins if coin in configured_coins]
                else:
                    self.monitor_coins = new_coins
                    
            except Exception as e:
                logger.error(f"Failed to update coin list: {e}")
        
    async def _monitor_premiums(self):
        """Monitor premium rates for configured coins"""
        while self.running:
            try:
                for coin in self.monitor_coins:
                    premium_info = self.premium_calculator.calculate_premium(coin)
                    if premium_info:
                        logger.info(
                            f"{coin} - Upbit: {premium_info.upbit_price_krw:,.0f} KRW, "
                            f"Binance: {premium_info.binance_price_krw:,.0f} KRW, "
                            f"Premium: {premium_info.premium_rate:.2f}%"
                        )
                        
                        # Update dashboard
                        if self.dashboard:
                            self.dashboard.update_data('premium', {
                                'coin': coin,
                                'premium_rate': float(premium_info.premium_rate),
                                'timestamp': premium_info.timestamp
                            })
                            
                # Monitor USDT premium
                usdt_premium = self.premium_calculator.calculate_tether_premium()
                if usdt_premium:
                    logger.info(
                        f"USDT - Upbit: {usdt_premium.upbit_price_krw:,.0f} KRW, "
                        f"Theory: {usdt_premium.binance_price_krw:,.0f} KRW, "
                        f"Premium: {usdt_premium.premium_rate:.2f}%"
                    )
                    
                    if self.dashboard:
                        self.dashboard.update_data('premium', {
                            'coin': 'USDT',
                            'premium_rate': float(usdt_premium.premium_rate),
                            'timestamp': usdt_premium.timestamp
                        })
                        
                await asyncio.sleep(config.price_update_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error monitoring premiums: {e}")
                await asyncio.sleep(5)
                
    async def _check_arbitrage_opportunities(self):
        """Check and execute arbitrage opportunities"""
        while self.running:
            try:
                # Check emergency stop
                should_stop, reason = await self.risk_manager.check_emergency_stop()
                if should_stop:
                    logger.error(f"Emergency stop triggered: {reason}")
                    if self.dashboard:
                        self.dashboard.update_data('alert', {
                            'level': 'danger',
                            'message': reason
                        })
                    await asyncio.sleep(60)  # Wait before checking again
                    continue
                    
                # Check each coin for opportunities
                for coin in self.monitor_coins:
                    opportunity = self.premium_calculator.check_arbitrage_opportunity(
                        coin,
                        config.safety_margin_percent,
                        config.min_trade_amount_krw,
                        config.max_trade_amount_krw
                    )
                    
                    if opportunity:
                        # Check if we can execute the trade
                        can_trade, reason = await self.risk_manager.can_execute_trade(opportunity)
                        
                        if can_trade:
                            logger.info(f"Arbitrage opportunity found: {opportunity}")
                            
                            if not config.dry_run:
                                await self._execute_arbitrage(opportunity)
                            else:
                                logger.info("DRY RUN: Would execute trade")
                                
                            if self.dashboard:
                                self.dashboard.update_data('alert', {
                                    'level': 'success',
                                    'message': f'Arbitrage opportunity: {coin} {opportunity.direction}'
                                })
                        else:
                            logger.debug(f"Trade rejected: {reason}")
                            
                await asyncio.sleep(config.price_update_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error checking arbitrage opportunities: {e}")
                await asyncio.sleep(5)
                
    async def _execute_arbitrage(self, opportunity):
        """Execute arbitrage trade"""
        try:
            # Register trade start
            trade_id = f"{opportunity.coin_symbol}_{datetime.now().timestamp()}"
            await self.risk_manager.register_trade_start(trade_id, opportunity)
            
            # Execute based on direction
            if opportunity.direction == "forward":
                result = await self.forward_strategy.execute_arbitrage(opportunity)
            else:
                result = await self.reverse_strategy.execute_arbitrage(opportunity)
                
            # Register trade completion
            success = result['status'].value == 'completed'
            profit = result.get('profit', {}).get('profit_krw', Decimal('0'))
            await self.risk_manager.register_trade_complete(trade_id, profit, success)
            
            # Update dashboard
            if self.dashboard:
                self.dashboard.update_data('trade', {
                    'coin': opportunity.coin_symbol,
                    'direction': opportunity.direction,
                    'status': result['status'].value,
                    'profit_krw': float(profit)
                })
                
        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            await self.risk_manager.register_trade_complete(
                trade_id, Decimal('0'), False
            )
            
    async def _update_metrics(self):
        """Update trading metrics"""
        while self.running:
            try:
                metrics = await self.risk_manager.get_trading_metrics()
                
                if self.dashboard:
                    self.dashboard.update_data('metrics', metrics)
                    
                # Log metrics periodically
                logger.info(
                    f"Daily metrics - Volume: {metrics['daily_volume_krw']:,.0f} KRW, "
                    f"Net profit: {metrics['net_profit_krw']:,.0f} KRW, "
                    f"Success rate: {metrics['success_rate']:.1f}%"
                )
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                logger.error(f"Error updating metrics: {e}")
                await asyncio.sleep(30)
                
    async def _monitor_system_health(self):
        """Monitor system health and balances"""
        while self.running:
            try:
                await self._check_balances()
                
                # Check exchange rate availability
                rate_info = self.exchange_rate.get_exchange_rate_info()
                if rate_info.get('error'):
                    logger.warning("Exchange rate unavailable")
                    if self.dashboard:
                        self.dashboard.update_data('alert', {
                            'level': 'warning',
                            'message': 'Exchange rate unavailable - trading paused'
                        })
                        
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error monitoring system health: {e}")
                await asyncio.sleep(60)
                
    async def _check_balances(self):
        """Check and log exchange balances"""
        try:
            # Get balances
            upbit_krw = self.upbit.get_balance('KRW')['total']
            binance_usdt = self.binance.get_balance('USDT')['total']
            
            # Get exchange rate
            usd_krw_rate = self.exchange_rate.get_usd_krw_rate()
            
            # Validate balances
            valid, message = await self.risk_manager.validate_exchange_balances(
                upbit_krw, binance_usdt, usd_krw_rate
            )
            
            if not valid:
                logger.warning(f"Balance validation failed: {message}")
                if self.dashboard:
                    self.dashboard.update_data('alert', {
                        'level': 'warning',
                        'message': message
                    })
                    
            # Update dashboard
            if self.dashboard:
                self.dashboard.update_data('balances', {
                    'Upbit': {'KRW': float(upbit_krw)},
                    'Binance': {'USDT': float(binance_usdt)}
                })
                
            logger.info(
                f"Balances - Upbit: {upbit_krw:,.0f} KRW, "
                f"Binance: {binance_usdt:,.2f} USDT"
            )
            
        except Exception as e:
            logger.error(f"Error checking balances: {e}")


async def main():
    bot = ArbitrageTradingBot()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(bot.stop())
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await bot.stop()
        

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("암호화폐 재정거래 봇 시작")
    logger.info(f"초기 모니터링 코인: {', '.join(config.monitor_coins) if config.monitor_coins else '모든 가능한 코인'}")
    logger.info(f"안전 마진: {config.safety_margin_percent}%")
    logger.info(f"거래 범위: {config.min_trade_amount_krw:,.0f} - {config.max_trade_amount_krw:,.0f} KRW")
    logger.info(f"모드: {'테스트넷' if config.testnet else '실거래'} / {'모의거래' if config.dry_run else '실거래'}")
    logger.info("=" * 50)
    
    asyncio.run(main())