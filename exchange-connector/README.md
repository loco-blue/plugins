# exchange-connector

Multi-exchange market data and order placement for Loco — Binance and OKX.

## Overview

**Type:** node
**Version:** 0.1.0
**Author:** loco

## Architecture

This plugin exposes 4 exchange-agnostic nodes, one per operation rather than
one per exchange:

- `get_klines` (`nodes/get_klines.py`) — recent OHLCV candlesticks
- `place_order` (`nodes/place_order.py`) — market order placement
- `get_positions` (`nodes/get_positions.py`) — open positions for a symbol
- `cancel_order` (`nodes/cancel_order.py`) — cancel a resting order

Each node is a thin wrapper that delegates to `nodes/_dispatch.py`, which
picks the adapter class at runtime from `context["auth"]["provider"]`
(`"binance"` or `"okx"`) — the provider of whichever credential the operator
connected to that node instance in the workflow editor. No `exchange` input
field exists on any node; the connected credential is what determines which
exchange a given node instance talks to, so the same `get_klines` node
definition can be dropped on the canvas twice, once wired to a Binance
credential and once to an OKX credential.

The two adapters implement the shared `ExchangeAdapter` contract
(`adapters/base.py`):

- `adapters/binance.py` — `BinanceAdapter`, against Binance's REST API
- `adapters/okx.py` — `OkxAdapter`, against OKX's v5 REST API

Both normalize their exchange's raw responses into the same shape, so
`_dispatch.py` never branches on exchange after construction.

## Configuration

Two auth providers are declared, one per exchange:

`auth/binance.yaml`:

```yaml
credentials_schema:
  - name: api_key
    type: secret
    required: true
  - name: api_secret
    type: secret
    required: true
```

`auth/okx.yaml`:

```yaml
credentials_schema:
  - name: api_key
    type: secret
    required: true
  - name: api_secret
    type: secret
    required: true
  - name: api_passphrase
    type: secret
    required: true
```

## Development

### Testing

```bash
cd exchange-connector
pytest tests/ -v
```

Or via the Loco CLI from the `loco/` directory:

```bash
uv run loco plugin validate ../plugins/exchange-connector
uv run loco plugin test ../plugins/exchange-connector
```

### Building

```bash
uv run loco plugin build ../plugins/exchange-connector
```

## License

MIT
