# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a cryptocurrency arbitrage trading bot that capitalizes on price differences between Upbit (Korean exchange) and Binance (international exchange). The bot implements bidirectional arbitrage strategies to profit from the "Kimchi Premium" phenomenon.

## Key Commands

### Running the Bot
```bash
# Live trading mode
python main.py

# Dry run mode (paper trading simulation)
DRY_RUN=true python main.py

# With custom log level
LOG_LEVEL=DEBUG python main.py

# Disable dashboard
ENABLE_DASHBOARD=false python main.py
```

### Development Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Type checking (MyPy is installed)
mypy .

# Run tests (pytest is installed but no tests exist yet)
pytest
```

## Architecture Overview

### Core Components

1. **main.py**: Entry point containing `ArbitrageTradingBot` class that orchestrates all components
2. **config/config.py**: Pydantic-based configuration management with environment variable support
3. **src/api/**: Exchange API clients (Binance and Upbit) with caching mechanisms
4. **src/strategies/**: Trading strategies for forward and reverse arbitrage
5. **src/utils/**: Core utilities including risk management, premium calculation, and exchange rate fetching
6. **src/monitoring/dashboard.py**: Real-time web dashboard (Dash/Plotly) on port 8050
7. **src/simulation/**: Paper trading components with virtual balance management

### Async Architecture

The bot uses asyncio with multiple concurrent tasks:
- Premium monitoring task (continuous price fetching)
- Opportunity detection task (analyzes arbitrage opportunities)
- Trade execution task (manages complete trade lifecycle)
- System health monitoring task (tracks balances and metrics)
- Coin list update task (refreshes available pairs every 30 minutes)

### Trading Flow

1. **Forward Arbitrage** (Reverse Premium):
   - Buy crypto on Upbit (KRW) → Transfer to Binance → Sell for USDT → Transfer back → Sell USDT for KRW

2. **Reverse Arbitrage** (Kimchi Premium):
   - Buy crypto on Binance (USDT) → Transfer to Upbit → Sell for KRW → Buy USDT → Transfer back

### Risk Management

The `RiskManager` class enforces:
- Daily volume limits (`MAX_DAILY_VOLUME_KRW`)
- Concurrent trade limits (`MAX_CONCURRENT_TRADES`)
- Emergency stop loss (`EMERGENCY_STOP_LOSS_PERCENT`)
- Minimum balance requirements
- Slippage protection

## Configuration

Required `.env` file based on `.env.example`:
- Exchange API credentials (Binance and Upbit)
- Trading parameters (safety margins, trade amounts)
- Risk management settings
- Monitoring configuration

Key configuration points:
- `monitor_coins` in config: Empty list = monitor all available coins
- Dynamic coin discovery: Updates available trading pairs every 30 minutes
- Exchange rate caching: Reduces API calls for USD/KRW rates

## Important Development Notes

1. **API Clients**: Both exchange clients implement common interface with methods like `get_balance()`, `place_order()`, `get_orderbook()`

2. **Premium Calculation**: The `PremiumCalculator` considers:
   - Trading fees on both exchanges
   - USDT premium on Upbit (actual market price, not theoretical)
   - Slippage based on orderbook depth
   - Network transfer fees

3. **Error Handling**: 
   - Graceful shutdown on SIGINT/SIGTERM
   - Exchange rate failure protection (stops trading if rates unavailable)
   - Transfer timeout protection
   - Orderbook failure handling (skips coins after 5 consecutive failures)
   - Comprehensive logging with loguru

4. **Testing Considerations**:
   - Always test with `DRY_RUN=true` first
   - Monitor dashboard at http://localhost:8050
   - Check logs in `logs/trading.log`
   - Paper trading simulates 1-minute transfer times

5. **State Management**:
   - Uses in-memory state (no database)
   - Daily metrics reset at midnight KST
   - Active trades tracked in `risk_manager.active_trades`
   - Virtual balances stored in `simulation_state.json` for paper trading

## Code Style Patterns

- Type hints throughout (compatible with mypy)
- Async/await for all exchange operations
- Pydantic models for configuration validation
- Structured logging with contextual information
- Error handling with specific exception types

## Recent Technical Improvements (2025-07-21)

### 1. USDT Premium Calculation
- Fixed to use actual Upbit KRW-USDT market price instead of theoretical USD/KRW rate
- Added debug logging for premium calculations
- More accurate profit estimation

### 2. Paper Trading Enhancements
- Fixed virtual balance manager ticker parsing (KRW-BTC format)
- Implemented realistic 1-minute transfer delays
- Dashboard now shows all virtual balances in paper trading mode
- Fixed ROI calculation in performance analyzer

### 3. Exchange Client Architecture
- Mock clients (`MockBinanceClient`, `MockUpbitClient`) for paper trading
- Real clients wrapped with virtual balance management
- Seamless switching between live and paper trading modes

### 4. Transfer Simulation
- Both directions simulate 1-minute delays in paper trading
- Automatic balance updates after transfers
- Network fees properly deducted

## Known Issues & TODOs

1. **Reverse Arbitrage Strategy**: Not fully implemented yet
2. **Unit Tests**: Test suite needs to be created
3. **Database Integration**: Currently uses in-memory state only
4. **Advanced Order Types**: Only market orders supported
5. **Multi-currency Support**: Currently focused on KRW/USDT pairs

## Paper Trading Architecture

### VirtualBalanceManager
- Manages virtual balances for both exchanges
- Tracks all trades and transfers
- Persists state to `simulation_state.json`
- Supports balance locking for pending orders

### Mock Exchange Clients
- `MockBinanceClient` and `MockUpbitClient` wrap real clients
- Use actual market data for realistic simulation
- Execute trades against virtual balances
- Simulate network delays and fees

### Performance Analyzer
- Calculates comprehensive metrics (ROI, Sharpe ratio, max drawdown)
- Groups trades by arbitrage opportunity
- Generates both text and JSON reports
- Tracks performance by cryptocurrency

## Debugging Tips

1. **Insufficient Balance Errors**:
   - Check ticker parsing (Upbit uses KRW-BTC format)
   - Verify virtual balance initialization
   - Review balance manager logs

2. **No Opportunities Detected**:
   - Check USDT premium calculation
   - Verify safety margin isn't too high
   - Monitor volatility levels

3. **API Errors**:
   - Verify IP whitelist on Upbit
   - Check API key permissions
   - Monitor rate limits

4. **Performance Issues**:
   - Use caching for frequently accessed data
   - Batch API calls where possible
   - Monitor async task performance

## Best Practices

1. **Always use paper trading first** to test configuration changes
2. **Monitor the dashboard** for real-time system health
3. **Check logs regularly** for warnings and errors
4. **Start with small amounts** when transitioning to live trading
5. **Keep safety margins appropriate** for market conditions
6. **Review daily performance reports** to optimize parameters

## Critical File Paths

- **Virtual Balances**: `simulation_state.json`
- **Logs**: `logs/trading.log`
- **Performance Reports**: `paper_trading_report.txt`, `paper_trading_report.json`
- **Configuration**: `.env`, `config/config.py`

## Emergency Procedures

1. **To stop the bot**: Press Ctrl+C (handles graceful shutdown)
2. **If trades are stuck**: Check transfer status on exchanges
3. **If balances mismatch**: Verify with exchange APIs directly
4. **If API fails**: Check IP whitelist and API permissions

## Future Enhancements

1. **Database Support**: PostgreSQL for trade history and analytics
2. **Machine Learning**: Optimize safety margins based on historical data
3. **Multi-Exchange**: Support for additional exchanges
4. **Mobile App**: React Native app for monitoring
5. **Backtesting**: Historical data analysis framework