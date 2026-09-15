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

## Known simplifications

This is a proof-of-concept connector; the following are deliberate
shortcuts, not bugs:

- **`place_order` fill data is asymmetric between the two exchanges.**
  Binance's `POST /api/v3/order` response carries real execution data, so
  `BinanceAdapter` returns the exchange's own `status` plus a true
  `filled_qty`/`avg_price`. OKX's `POST /api/v5/trade/order` is an
  acknowledgement only (`{ordId, clOrdId, tag, ts, sCode, sMsg}`) and
  carries no fill information, so `OkxAdapter` returns `status: "live"`
  (OKX's term for accepted-but-not-yet-filled) with `filled_qty: 0.0` and
  `avg_price: 0.0`. A caller that needs real fill status on OKX must call
  `get_positions` afterwards.
- **`get_positions` is not a true positions query on either exchange.**
  On Binance it queries `/api/v3/openOrders` (resting spot orders), not a
  positions endpoint. On OKX it queries `/api/v5/account/positions`, which
  reports derivatives positions only — while `place_order` submits with
  `tdMode: "cash"` (spot), so a spot order placed through this plugin will
  never show up in `get_positions` on the same OKX account.

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
cd plugins/exchange-connector
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
