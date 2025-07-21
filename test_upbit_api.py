#!/usr/bin/env python3
"""Test script to verify Upbit API access and diagnose orderbook issues"""

import os
import sys
from dotenv import load_dotenv
import pyupbit
from loguru import logger

# Load environment variables
load_dotenv()

def test_upbit_api():
    """Test Upbit API access"""
    logger.info("Starting Upbit API test...")
    
    # Get API credentials
    access_key = os.getenv("UPBIT_ACCESS_KEY")
    secret_key = os.getenv("UPBIT_SECRET_KEY")
    
    if not access_key or not secret_key:
        logger.error("UPBIT_ACCESS_KEY or UPBIT_SECRET_KEY not found in .env file")
        sys.exit(1)
    
    # Initialize Upbit client
    upbit = pyupbit.Upbit(access_key, secret_key)
    
    # Test 1: Check balance (requires valid API key)
    logger.info("\nTest 1: Checking account balance...")
    try:
        balances = upbit.get_balances()
        if balances:
            logger.success(f"✓ Successfully retrieved {len(balances)} balance entries")
            for balance in balances[:3]:  # Show first 3
                logger.info(f"  - {balance['currency']}: {balance['balance']} (locked: {balance['locked']})")
        else:
            logger.error("✗ Failed to get balances - API key may be invalid")
    except Exception as e:
        logger.error(f"✗ Balance check failed: {e}")
    
    # Test 2: Get market price (doesn't require authentication)
    logger.info("\nTest 2: Getting market price...")
    try:
        price = pyupbit.get_current_price("KRW-BTC")
        if price:
            logger.success(f"✓ BTC price: {price:,.0f} KRW")
        else:
            logger.error("✗ Failed to get BTC price")
    except Exception as e:
        logger.error(f"✗ Price check failed: {e}")
    
    # Test 3: Get orderbook (this is where IP whitelist matters)
    logger.info("\nTest 3: Getting orderbook...")
    test_coins = ["BTC", "ETH", "USDT"]
    
    for coin in test_coins:
        ticker = f"KRW-{coin}"
        try:
            orderbook = pyupbit.get_orderbook(ticker)
            
            if orderbook is None:
                logger.error(f"✗ {ticker}: get_orderbook returned None")
                logger.error("  → This usually means API access is blocked")
                logger.error("  → Check if your IP is whitelisted in Upbit API settings")
            elif isinstance(orderbook, list) and len(orderbook) > 0:
                ob = orderbook[0]
                if 'error' in ob:
                    logger.error(f"✗ {ticker}: API error - {ob['error']}")
                elif 'orderbook_units' in ob:
                    units = ob['orderbook_units']
                    if units:
                        logger.success(f"✓ {ticker}: Retrieved {len(units)} orderbook levels")
                        # Show best bid/ask
                        best_bid = units[0].get('bid_price', 0)
                        best_ask = units[0].get('ask_price', 0)
                        logger.info(f"    Best bid: {best_bid:,.0f} KRW, Best ask: {best_ask:,.0f} KRW")
                    else:
                        logger.warning(f"⚠ {ticker}: Empty orderbook units")
                else:
                    logger.warning(f"⚠ {ticker}: Unexpected format - {list(ob.keys())}")
            else:
                logger.error(f"✗ {ticker}: Unexpected orderbook type: {type(orderbook)}")
                
        except Exception as e:
            logger.error(f"✗ {ticker}: Exception - {e}")
    
    # Test 4: Get all KRW markets
    logger.info("\nTest 4: Getting all KRW markets...")
    try:
        markets = pyupbit.get_tickers()
        krw_markets = [m for m in markets if m.startswith('KRW-')]
        logger.success(f"✓ Found {len(krw_markets)} KRW markets")
        logger.info(f"  First 10: {krw_markets[:10]}")
    except Exception as e:
        logger.error(f"✗ Failed to get markets: {e}")
    
    logger.info("\n" + "="*60)
    logger.info("TROUBLESHOOTING TIPS:")
    logger.info("1. If orderbook returns None → Add your IP to Upbit API whitelist")
    logger.info("2. If balance check fails → Verify your API keys are correct")
    logger.info("3. Visit: https://upbit.com/mypage/open_api_management")
    logger.info("4. Add your current IP address to the whitelist")
    logger.info("5. Wait a few minutes for changes to take effect")
    logger.info("="*60)

if __name__ == "__main__":
    test_upbit_api()