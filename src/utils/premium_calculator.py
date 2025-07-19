from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
import asyncio
from loguru import logger

from ..api.binance_client import BinanceClient
from ..api.upbit_client import UpbitClient
from .exchange_rate import ExchangeRateProvider


@dataclass
class PremiumInfo:
    symbol: str
    upbit_price_krw: Decimal
    binance_price_usdt: Decimal
    binance_price_krw: Decimal
    premium_rate: Decimal
    reverse_premium_rate: Decimal
    usd_krw_rate: Decimal
    timestamp: datetime
    
    @property
    def is_kimchi_premium(self) -> bool:
        return self.premium_rate > 0
        
    @property
    def is_reverse_premium(self) -> bool:
        return self.premium_rate < 0


@dataclass
class ArbitrageOpportunity:
    coin_symbol: str
    direction: str  # 'forward' or 'reverse'
    coin_premium: Decimal
    tether_premium: Decimal
    total_fees: Decimal
    expected_profit: Decimal
    safety_margin: Decimal
    trade_amount_krw: Decimal
    timestamp: datetime
    
    @property
    def net_profit_rate(self) -> Decimal:
        return self.expected_profit - self.total_fees - self.safety_margin


class PremiumCalculator:
    def __init__(self, binance_client: BinanceClient, upbit_client: UpbitClient,
                 exchange_rate_provider: ExchangeRateProvider):
        self.binance = binance_client
        self.upbit = upbit_client
        self.exchange_rate = exchange_rate_provider
        
        # Fee structure
        self.BINANCE_TRADING_FEE = Decimal("0.001")  # 0.1%
        self.UPBIT_TRADING_FEE = Decimal("0.0005")   # 0.05%
        self.WITHDRAWAL_FEES = {
            'BTC': Decimal("0.0005"),
            'ETH': Decimal("0.005"),
            'USDT': {'TRC20': Decimal("1"), 'ERC20': Decimal("10")},
            'XRP': Decimal("0.25"),
            'ADA': Decimal("1"),
            'SOL': Decimal("0.01"),
            'DOT': Decimal("0.1"),
            'AVAX': Decimal("0.01")
        }
        
    def calculate_premium(self, symbol: str) -> Optional[PremiumInfo]:
        try:
            # Get Upbit price in KRW
            upbit_ticker = f"KRW-{symbol}"
            upbit_price = self.upbit.get_ticker_price(upbit_ticker)
            
            # Get Binance price in USDT
            binance_ticker = f"{symbol}USDT"
            binance_price_usdt = self.binance.get_ticker_price(binance_ticker)
            
            # Get exchange rate
            usd_krw_rate = self.exchange_rate.get_usd_krw_rate()
            if usd_krw_rate is None:
                logger.error(f"Cannot calculate premium for {symbol}: Exchange rate unavailable")
                return None
            
            # Convert Binance price to KRW
            binance_price_krw = binance_price_usdt * usd_krw_rate
            
            # Calculate premium rate
            premium_rate = ((upbit_price - binance_price_krw) / binance_price_krw) * 100
            reverse_premium_rate = -premium_rate
            
            return PremiumInfo(
                symbol=symbol,
                upbit_price_krw=upbit_price,
                binance_price_usdt=binance_price_usdt,
                binance_price_krw=binance_price_krw,
                premium_rate=premium_rate,
                reverse_premium_rate=reverse_premium_rate,
                usd_krw_rate=usd_krw_rate,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to calculate premium for {symbol}: {e}")
            return None
            
    def calculate_tether_premium(self) -> Optional[PremiumInfo]:
        try:
            # Get Upbit USDT price in KRW
            upbit_usdt_price = self.upbit.get_ticker_price("KRW-USDT")
            
            # Get exchange rate
            usd_krw_rate = self.exchange_rate.get_usd_krw_rate()
            if usd_krw_rate is None:
                logger.error("Cannot calculate USDT premium: Exchange rate unavailable")
                return None
            
            # USDT should be 1 USD, so theoretical price in KRW is the exchange rate
            theoretical_usdt_krw = usd_krw_rate
            
            # Calculate premium rate
            premium_rate = ((upbit_usdt_price - theoretical_usdt_krw) / theoretical_usdt_krw) * 100
            
            return PremiumInfo(
                symbol="USDT",
                upbit_price_krw=upbit_usdt_price,
                binance_price_usdt=Decimal("1"),  # USDT is always 1 USD
                binance_price_krw=theoretical_usdt_krw,
                premium_rate=premium_rate,
                reverse_premium_rate=-premium_rate,
                usd_krw_rate=usd_krw_rate,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to calculate USDT premium: {e}")
            return None
            
    def check_arbitrage_opportunity(self, coin_symbol: str, 
                                  safety_margin: Decimal,
                                  min_trade_amount_krw: Decimal,
                                  max_trade_amount_krw: Decimal) -> Optional[ArbitrageOpportunity]:
        try:
            # Get coin premium
            coin_premium = self.calculate_premium(coin_symbol)
            if not coin_premium:
                return None
                
            # Get tether premium
            tether_premium = self.calculate_tether_premium()
            if not tether_premium:
                return None
                
            # Calculate total fees
            total_fees = self._calculate_total_fees(coin_symbol)
            
            # Check forward arbitrage (reverse premium)
            # Buy on Upbit, sell on Binance
            if coin_premium.is_reverse_premium:
                profit_rate = abs(coin_premium.premium_rate) - tether_premium.premium_rate
                if profit_rate > total_fees + safety_margin:
                    return ArbitrageOpportunity(
                        coin_symbol=coin_symbol,
                        direction="forward",
                        coin_premium=coin_premium.premium_rate,
                        tether_premium=tether_premium.premium_rate,
                        total_fees=total_fees,
                        expected_profit=profit_rate,
                        safety_margin=safety_margin,
                        trade_amount_krw=self._calculate_optimal_trade_amount(
                            coin_symbol, min_trade_amount_krw, max_trade_amount_krw
                        ),
                        timestamp=datetime.now()
                    )
                    
            # Check reverse arbitrage (kimchi premium)
            # Buy on Binance, sell on Upbit
            elif coin_premium.is_kimchi_premium:
                profit_rate = coin_premium.premium_rate - tether_premium.premium_rate
                if profit_rate > total_fees + safety_margin:
                    return ArbitrageOpportunity(
                        coin_symbol=coin_symbol,
                        direction="reverse",
                        coin_premium=coin_premium.premium_rate,
                        tether_premium=tether_premium.premium_rate,
                        total_fees=total_fees,
                        expected_profit=profit_rate,
                        safety_margin=safety_margin,
                        trade_amount_krw=self._calculate_optimal_trade_amount(
                            coin_symbol, min_trade_amount_krw, max_trade_amount_krw
                        ),
                        timestamp=datetime.now()
                    )
                    
            return None
            
        except Exception as e:
            logger.error(f"Failed to check arbitrage opportunity for {coin_symbol}: {e}")
            return None
            
    def _calculate_total_fees(self, coin_symbol: str) -> Decimal:
        # Trading fees (2 trades on each exchange)
        trading_fees = (self.BINANCE_TRADING_FEE * 2) + (self.UPBIT_TRADING_FEE * 2)
        
        # Withdrawal fees (coin + USDT)
        coin_withdrawal_fee = self._get_withdrawal_fee_rate(coin_symbol)
        usdt_withdrawal_fee = Decimal("0.0001")  # Approximate USDT withdrawal fee as percentage
        
        total_fees = trading_fees + coin_withdrawal_fee + usdt_withdrawal_fee
        
        return total_fees * 100  # Convert to percentage
        
    def _get_withdrawal_fee_rate(self, coin_symbol: str) -> Decimal:
        if coin_symbol not in self.WITHDRAWAL_FEES:
            return Decimal("0.001")  # Default 0.1% for unknown coins
            
        fee = self.WITHDRAWAL_FEES[coin_symbol]
        if isinstance(fee, dict):
            # For USDT, use TRC20 as it's cheaper
            fee = fee['TRC20']
            
        # Convert fixed fee to approximate percentage
        # This is a rough estimate - should be calculated based on actual price
        try:
            coin_price = self.binance.get_ticker_price(f"{coin_symbol}USDT")
            fee_rate = fee / coin_price
            return fee_rate
        except:
            return Decimal("0.001")  # Default 0.1%
            
    def _calculate_optimal_trade_amount(self, coin_symbol: str,
                                      min_amount: Decimal,
                                      max_amount: Decimal) -> Decimal:
        try:
            # Get order books
            upbit_orderbook = self.upbit.get_orderbook(f"KRW-{coin_symbol}")
            binance_orderbook = self.binance.get_order_book(f"{coin_symbol}USDT")
            
            # Calculate available liquidity
            upbit_bid_liquidity = sum(price * qty for price, qty in upbit_orderbook['bids'][:5])
            upbit_ask_liquidity = sum(price * qty for price, qty in upbit_orderbook['asks'][:5])
            
            # Convert Binance liquidity to KRW
            usd_krw_rate = self.exchange_rate.get_usd_krw_rate()
            binance_bid_liquidity = sum(price * qty for price, qty in binance_orderbook['bids'][:5]) * usd_krw_rate
            binance_ask_liquidity = sum(price * qty for price, qty in binance_orderbook['asks'][:5]) * usd_krw_rate
            
            # Use the minimum available liquidity
            available_liquidity = min(
                upbit_bid_liquidity,
                upbit_ask_liquidity,
                binance_bid_liquidity,
                binance_ask_liquidity
            ) * Decimal("0.3")  # Use only 30% of available liquidity
            
            # Apply min/max constraints
            optimal_amount = max(min_amount, min(available_liquidity, max_amount))
            
            return optimal_amount
            
        except Exception as e:
            logger.error(f"Failed to calculate optimal trade amount: {e}")
            return min_amount
            
    async def monitor_premiums(self, symbols: List[str], interval: int = 1):
        while True:
            try:
                for symbol in symbols:
                    premium_info = self.calculate_premium(symbol)
                    if premium_info:
                        logger.info(
                            f"{symbol} - Upbit: {premium_info.upbit_price_krw:,.0f} KRW, "
                            f"Binance: {premium_info.binance_price_krw:,.0f} KRW, "
                            f"Premium: {premium_info.premium_rate:.2f}%"
                        )
                        
                # Also monitor USDT premium
                usdt_premium = self.calculate_tether_premium()
                if usdt_premium:
                    logger.info(
                        f"USDT - Upbit: {usdt_premium.upbit_price_krw:,.0f} KRW, "
                        f"Theoretical: {usdt_premium.binance_price_krw:,.0f} KRW, "
                        f"Premium: {usdt_premium.premium_rate:.2f}%"
                    )
                    
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in premium monitoring: {e}")
                await asyncio.sleep(interval)