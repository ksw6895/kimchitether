from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List, Optional
from decimal import Decimal
import os
from dotenv import load_dotenv

load_dotenv()


class TradingConfig(BaseSettings):
    # API Keys
    binance_api_key: str = Field(..., env='BINANCE_API_KEY')
    binance_secret_key: str = Field(..., env='BINANCE_SECRET_KEY')
    upbit_access_key: str = Field(..., env='UPBIT_ACCESS_KEY')
    upbit_secret_key: str = Field(..., env='UPBIT_SECRET_KEY')
    
    # Trading Parameters
    safety_margin_percent: Decimal = Field(default=Decimal("1.5"), env='SAFETY_MARGIN_PERCENT')
    min_trade_amount_krw: Decimal = Field(default=Decimal("100000"), env='MIN_TRADE_AMOUNT_KRW')
    max_trade_amount_krw: Decimal = Field(default=Decimal("5000000"), env='MAX_TRADE_AMOUNT_KRW')
    
    # Coins to monitor (empty list means monitor all available coins)
    monitor_coins: List[str] = Field(default=[])
    
    # Risk Management
    max_slippage_percent: Decimal = Field(default=Decimal("0.5"), env='MAX_SLIPPAGE_PERCENT')
    transfer_timeout_minutes: int = Field(default=30, env='TRANSFER_TIMEOUT_MINUTES')
    emergency_stop_loss_percent: Decimal = Field(default=Decimal("3.0"), env='EMERGENCY_STOP_LOSS_PERCENT')
    max_concurrent_trades: int = Field(default=3, env='MAX_CONCURRENT_TRADES')
    max_daily_volume_krw: Decimal = Field(default=Decimal("50000000"), env='MAX_DAILY_VOLUME_KRW')
    min_exchange_balance_krw: Decimal = Field(default=Decimal("1000000"), env='MIN_EXCHANGE_BALANCE_KRW')
    max_exposure_percent: Decimal = Field(default=Decimal("30"), env='MAX_EXPOSURE_PERCENT')
    
    # Monitoring
    price_update_interval_seconds: int = Field(default=1, env='PRICE_UPDATE_INTERVAL_SECONDS')
    dashboard_port: int = Field(default=8050, env='DASHBOARD_PORT')
    enable_dashboard: bool = Field(default=True, env='ENABLE_DASHBOARD')
    
    # Exchange Rate Settings
    exchange_rate_cache_duration: int = Field(default=300, env='EXCHANGE_RATE_CACHE_DURATION')
    
    # Logging
    log_level: str = Field(default="INFO", env='LOG_LEVEL')
    log_file: str = Field(default="logs/trading.log", env='LOG_FILE')
    
    # Trading Mode
    testnet: bool = Field(default=False, env='TESTNET')
    dry_run: bool = Field(default=False, env='DRY_RUN')
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        
    @validator('monitor_coins', pre=True)
    def parse_monitor_coins(cls, v):
        if isinstance(v, str):
            return [coin.strip() for coin in v.split(',')]
        return v
        
    @validator('safety_margin_percent', 'min_trade_amount_krw', 'max_trade_amount_krw', 
               'max_slippage_percent', 'emergency_stop_loss_percent', 'max_daily_volume_krw',
               'min_exchange_balance_krw', 'max_exposure_percent', pre=True)
    def convert_to_decimal(cls, v):
        if isinstance(v, str):
            return Decimal(v)
        return v
        
    def validate_config(self):
        """Validate configuration settings"""
        errors = []
        
        # Check API keys
        if not self.binance_api_key or self.binance_api_key == 'your_binance_api_key_here':
            errors.append("Binance API key not configured")
        if not self.upbit_access_key or self.upbit_access_key == 'your_upbit_access_key_here':
            errors.append("Upbit access key not configured")
            
        # Check trading amounts
        if self.min_trade_amount_krw >= self.max_trade_amount_krw:
            errors.append("min_trade_amount_krw must be less than max_trade_amount_krw")
            
        # Check risk parameters
        if self.safety_margin_percent <= 0:
            errors.append("safety_margin_percent must be positive")
            
        if self.max_slippage_percent <= 0:
            errors.append("max_slippage_percent must be positive")
            
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
            
    def get_risk_limits(self):
        """Get risk management limits"""
        from src.utils.risk_manager import RiskLimits
        
        return RiskLimits(
            max_single_trade_krw=self.max_trade_amount_krw,
            max_daily_volume_krw=self.max_daily_volume_krw,
            max_concurrent_trades=self.max_concurrent_trades,
            max_slippage_percent=self.max_slippage_percent,
            emergency_stop_loss_percent=self.emergency_stop_loss_percent,
            min_exchange_balance_krw=self.min_exchange_balance_krw,
            max_exposure_percent=self.max_exposure_percent
        )


# Create global config instance
config = TradingConfig()