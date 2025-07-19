import sys
import os
from pathlib import Path
from loguru import logger
from datetime import datetime


def setup_logger():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger.remove()
    
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True
    )
    
    logger.add(
        log_dir / f"kimchi_{datetime.now().strftime('%Y%m%d')}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="zip"
    )
    
    logger.add(
        log_dir / "errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level="ERROR",
        rotation="1 week",
        retention="3 months",
        compression="zip"
    )
    
    logger.add(
        log_dir / "trades.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        filter=lambda record: "trade" in record["extra"],
        rotation="1 day",
        retention="1 year",
        compression="zip"
    )
    
    return logger


def log_trade(trade_data: dict):
    logger.bind(trade=True).info(f"TRADE: {trade_data}")


def log_arbitrage_opportunity(coin: str, axis: int, premium: float, expected_profit: float):
    logger.bind(trade=True).info(
        f"OPPORTUNITY: {coin} | Axis: {axis} | Premium: {premium:.2%} | Expected Profit: {expected_profit:.2f} USDT"
    )


def log_balance_update(exchange: str, balances: dict):
    logger.info(f"BALANCE UPDATE [{exchange}]: {balances}")


def log_api_error(exchange: str, endpoint: str, error: str):
    logger.error(f"API ERROR [{exchange}] {endpoint}: {error}")


def log_system_status(status: dict):
    logger.info(f"SYSTEM STATUS: {status}")