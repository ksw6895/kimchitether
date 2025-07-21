# pyupbit API Response Format Changes

## Investigation Date: 2025-07-21
## pyupbit Version: 0.2.33

### Important Change Detected
The `pyupbit.get_orderbook()` function now returns different data types depending on the input:

## 1. Single Ticker Input
When called with a single ticker string:
```python
orderbook = pyupbit.get_orderbook('KRW-BTC')
```

**Returns:** `dict` (NOT a list!)

**Dictionary Structure:**
```python
{
    'market': 'KRW-BTC',
    'timestamp': 1753101227772,
    'total_ask_size': 10.78325195,
    'total_bid_size': 1.04357911,
    'orderbook_units': [...],  # List of order book entries
    'level': 0
}
```

## 2. Multiple Ticker Input
When called with a list of tickers:
```python
orderbook = pyupbit.get_orderbook(['KRW-BTC', 'KRW-ETH'])
```

**Returns:** `list` of dictionaries

Each item in the list has the same structure as the single ticker response.

## 3. Error Handling
- Invalid ticker raises `UpbitError` exception with message "Code not found"
- No longer returns None or error dict

## Code Impact
Our current code expects `get_orderbook()` to always return a list, even for single ticker:
```python
# Current code (WRONG):
if isinstance(orderbook, list) and len(orderbook) > 0:
    ob = orderbook[0]

# Should be:
if isinstance(orderbook, dict):
    ob = orderbook
elif isinstance(orderbook, list) and len(orderbook) > 0:
    ob = orderbook[0]
```

## Other pyupbit Functions (No Changes)
- `get_tickers()`: Returns list of ticker strings
- `get_current_price()`: Returns float
- `get_ticker()`: Function doesn't exist (use get_ticker**s** instead)

## Migration Strategy
1. Update `get_orderbook()` handling to check for both dict and list types
2. When dict is returned, use it directly (don't try to access [0])
3. When list is returned, access the first element as before
4. Add proper error handling for UpbitError exceptions