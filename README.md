# Crypto Arbitrage Bot

An advanced cryptocurrency arbitrage trading bot that capitalizes on price differences between Upbit (Korean exchange) and Binance (international exchange), specifically designed to profit from the "Kimchi Premium" phenomenon.

## 🚀 Features

### Core Functionality
- **Bidirectional Arbitrage**: Supports both forward (reverse premium) and reverse (Kimchi premium) arbitrage strategies
- **Real-time Premium Monitoring**: Continuously tracks price differences across 100+ cryptocurrency pairs
- **Automated Trade Execution**: Executes complete arbitrage cycles including transfers between exchanges
- **Dynamic Coin Discovery**: Automatically monitors all coins available on both exchanges (updates every 30 minutes)

### Risk Management
- **Multi-layered Safety Controls**: 
  - Minimum profit margin requirements (configurable safety margin)
  - Maximum concurrent trade limits
  - Daily volume caps
  - Emergency stop loss protection
  - Slippage protection based on orderbook depth
- **Balance Validation**: Continuous monitoring of exchange balances with alerts
- **Transfer Timeout Protection**: Automatic handling of delayed transfers

### Development & Testing
- **Paper Trading Mode**: Full simulation with virtual balances and realistic transfer delays
- **Performance Analytics**: Comprehensive metrics including ROI, Sharpe ratio, and drawdown analysis
- **Web Dashboard**: Real-time monitoring interface with:
  - Live premium charts
  - Balance tracking
  - Trade history
  - Performance metrics
  - System alerts

### Technical Features
- **Asynchronous Architecture**: High-performance async/await implementation
- **Smart Caching**: Reduces API calls with intelligent caching for exchange rates and market data
- **Robust Error Handling**: Graceful degradation and recovery mechanisms
- **Comprehensive Logging**: Structured logging with loguru for debugging and analysis

## 📋 Prerequisites

- Python 3.8 or higher
- Upbit account with API access enabled
- Binance account with API access enabled
- For Upbit API: IP whitelist configuration required

## 🛠️ Installation

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/crypto-arbitrage-bot.git
cd crypto-arbitrage-bot
```

2. **Create and activate virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

## ⚙️ Configuration

### Environment Variables (.env)

```env
# Binance API Keys
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key

# Upbit API Keys
UPBIT_ACCESS_KEY=your_upbit_access_key
UPBIT_SECRET_KEY=your_upbit_secret_key

# Trading Parameters
SAFETY_MARGIN_PERCENT=1.5          # Minimum profit margin after all fees
MIN_TRADE_AMOUNT_KRW=100000        # Minimum trade size
MAX_TRADE_AMOUNT_KRW=5000000       # Maximum trade size

# Risk Management
MAX_SLIPPAGE_PERCENT=0.5           # Maximum acceptable slippage
TRANSFER_TIMEOUT_MINUTES=30        # Transfer timeout (1 min for paper trading)
EMERGENCY_STOP_LOSS_PERCENT=3.0    # Emergency stop threshold

# Monitoring
PRICE_UPDATE_INTERVAL_SECONDS=1    # Price check frequency
DASHBOARD_PORT=8050                # Web dashboard port
```

### Advanced Configuration (config/config.py)

- `monitor_coins`: List of specific coins to monitor (empty = monitor all)
- `max_concurrent_trades`: Maximum simultaneous trades
- `max_daily_volume_krw`: Daily trading volume limit
- Network fee configurations per cryptocurrency

## 🚀 Usage

### Live Trading Mode
```bash
python main.py
```

### Paper Trading Mode (Recommended for Testing)
```bash
DRY_RUN=true python main.py
```

### Advanced Usage
```bash
# Debug mode with paper trading
LOG_LEVEL=DEBUG DRY_RUN=true python main.py

# Disable dashboard
ENABLE_DASHBOARD=false python main.py

# Custom configuration
SAFETY_MARGIN_PERCENT=2.0 MAX_TRADE_AMOUNT_KRW=10000000 python main.py
```

## 📊 Trading Strategies

### Forward Arbitrage (Reverse Premium)
Executed when cryptocurrency is cheaper on Upbit than on Binance:
1. Buy cryptocurrency on Upbit with KRW
2. Transfer to Binance (1 min simulation in paper trading)
3. Sell for USDT on Binance
4. Transfer USDT to Upbit (1 min simulation in paper trading)
5. Sell USDT for KRW on Upbit

### Reverse Arbitrage (Kimchi Premium)
Executed when cryptocurrency is more expensive on Upbit:
1. Buy cryptocurrency on Binance with USDT
2. Transfer to Upbit
3. Sell for KRW on Upbit
4. Buy USDT with KRW
5. Transfer USDT back to Binance

## 🖥️ Web Dashboard

Access the real-time monitoring dashboard at `http://localhost:8050`

### Dashboard Features:
- **Premium Monitor**: Live charts showing price differences
- **Balance Tracker**: Real-time balance updates for both exchanges
- **Trade History**: Recent trades with profit/loss information
- **Performance Metrics**: Daily volume, profit, success rate
- **System Alerts**: Important notifications and warnings

## 🛡️ Safety Features

1. **Pre-trade Validation**:
   - Sufficient balance checks
   - Minimum profit verification
   - Slippage estimation

2. **Risk Limits**:
   - Maximum trade size enforcement
   - Daily volume restrictions
   - Concurrent trade limitations

3. **Emergency Controls**:
   - Automatic stop on critical errors
   - Balance anomaly detection
   - Network failure handling

4. **Paper Trading Mode**:
   - Full simulation with virtual balances
   - Realistic 1-minute transfer delays
   - Performance tracking without risk

## 📈 Performance Monitoring

### Paper Trading Reports
After running in paper trading mode, the bot generates comprehensive reports:
- `paper_trading_report.txt`: Human-readable performance summary
- `paper_trading_report.json`: Detailed JSON metrics

### Key Metrics Tracked:
- Total trades and success rate
- Net profit and ROI
- Sharpe ratio and maximum drawdown
- Performance breakdown by cryptocurrency
- Daily returns analysis

## 🔧 Development

### Project Structure
```
crypto-arbitrage-bot/
├── main.py                 # Entry point and orchestration
├── config/
│   └── config.py          # Configuration management
├── src/
│   ├── api/               # Exchange API clients
│   ├── strategies/        # Arbitrage strategies
│   ├── utils/             # Core utilities
│   ├── monitoring/        # Dashboard and monitoring
│   └── simulation/        # Paper trading components
└── logs/                  # Application logs
```

### Key Components:
- **PremiumCalculator**: Calculates real-time premiums using actual market prices
- **ForwardArbitrageStrategy**: Implements 5-step forward arbitrage logic
- **ReverseArbitrageStrategy**: Implements reverse arbitrage (not yet fully implemented)
- **VirtualBalanceManager**: Manages paper trading with realistic constraints
- **RiskManager**: Enforces all safety limits and risk controls

### Running Tests
```bash
pytest tests/  # Not yet implemented
mypy .        # Type checking
```

## ⚠️ Important Notes

1. **API Requirements**:
   - Upbit requires IP whitelisting for API access
   - Both exchanges require trading permissions enabled
   - Withdrawal permissions needed for live trading

2. **Network Fees**:
   - Each cryptocurrency has different withdrawal fees
   - USDT transfers use TRC20 network by default (lower fees)
   - Fees are calculated as percentage in the bot

3. **Market Risks**:
   - Cryptocurrency prices are highly volatile
   - Transfer times can vary significantly (1-30 minutes)
   - Exchange maintenance can interrupt operations
   - Slippage can reduce profits

4. **Compliance**:
   - Ensure compliance with local regulations
   - Be aware of tax implications
   - Some jurisdictions restrict arbitrage trading

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚡ Performance Tips

1. **Optimal Configuration**:
   - Start with small trade amounts
   - Use paper trading to find optimal parameters
   - Monitor the dashboard for system performance
   - Adjust safety margin based on volatility

2. **Network Optimization**:
   - Ensure stable internet connection
   - Consider running on a VPS near exchange servers
   - Use appropriate regional endpoints

3. **Risk Management**:
   - Never invest more than you can afford to lose
   - Start with paper trading
   - Gradually increase trade sizes
   - Monitor daily volumes and profits
   - Set appropriate emergency stop loss

## 🔍 Troubleshooting

### Common Issues:

1. **"Insufficient balance" errors in paper trading**: 
   - Check virtual balance initialization
   - Verify ticker parsing logic (KRW-BTC format)

2. **API connection errors**:
   - Verify API keys and secret keys
   - Check IP whitelist on Upbit
   - Ensure trading permissions are enabled

3. **No arbitrage opportunities detected**:
   - Normal during low volatility periods
   - Check if safety margin is too high
   - Verify USDT premium calculation

4. **Dashboard not loading**:
   - Check if port 8050 is available
   - Verify ENABLE_DASHBOARD is not set to false

5. **Orderbook access failures**:
   - Usually IP whitelist issue on Upbit
   - Bot will skip problematic coins after 5 failures

### Debug Mode:
```bash
LOG_LEVEL=DEBUG DRY_RUN=true python main.py
```

Check logs in `logs/trading.log` for detailed information.

## 📞 Support

For issues and questions:
- Check the logs in `logs/trading.log`
- Review CLAUDE.md for technical implementation details
- Submit issues on GitHub

## 🔄 Recent Updates

- Fixed USDT premium calculation to use actual Upbit market prices
- Implemented 1-minute transfer simulation for paper trading
- Fixed performance analyzer ROI calculation
- Improved dashboard to show virtual balances in paper trading
- Fixed Upbit ticker parsing (KRW-BTC format)
- Added dynamic coin list updates every 30 minutes