# exchange-connector

Multi-exchange market data and order placement for Loco — Binance and OKX,
spot and USDT-margined futures (one-way/net position mode, cross margin).

## Overview

**Type:** node
**Version:** 0.1.0
**Author:** loco

## Architecture

This plugin exposes 6 exchange-agnostic nodes, one per operation rather than
one per exchange:

- `get_klines` — recent OHLCV candlesticks (spot or futures)
- `place_order` — market, stop-market, or take-profit-market order placement (spot or futures)
- `cancel_order` — cancel a resting order (spot or futures)
- `get_balance` — account asset balances (spot or futures)
- `get_positions` — open futures positions for a symbol (**futures only**)
- `set_leverage` — set leverage for a symbol (**futures only**)

Each node is a thin wrapper that delegates to `nodes/_dispatch.py`, which
picks the adapter class at runtime from two things: `context["auth"]
["provider"]` (`"binance"` or `"okx"` — the connected credential) and the
node's own `market_type` input (`"spot"` or `"futures"`, where present).
`get_positions` and `set_leverage` have no `market_type` input at all —
they always resolve `"futures"`, since spot has no position/leverage
concept to select in the first place.

Four adapter classes implement a shared, split contract
(`adapters/base.py`):

- `ExchangeAdapter` — `get_klines`, `place_order`, `cancel_order`,
  `get_balance` — common to spot and futures
- `FuturesAdapter(ExchangeAdapter)` — adds `get_positions`, `set_leverage`
- `adapters/binance_spot.py` — `BinanceSpotAdapter`
- `adapters/binance_futures.py` — `BinanceFuturesAdapter(FuturesAdapter)`
- `adapters/okx_spot.py` — `OkxSpotAdapter`
- `adapters/okx_futures.py` — `OkxFuturesAdapter(FuturesAdapter)`

Shared HMAC/header mechanics live in `adapters/binance_signing.py` /
`adapters/okx_signing.py`, reused by both of each exchange's adapters so
neither the spot nor the futures class duplicates signing code.

## Stop-loss / take-profit orders

`place_order`'s `order_type`/`stop_price`/`reduce_only` fields are
deliberately NOT bundled into one "bracket order" call — Binance requires a
separate `STOP_MARKET`/`TAKE_PROFIT_MARKET` order call after the entry
(there is no single API call that places both), while OKX can bundle a
trigger into the entry call. To keep both exchanges' behavior equally
visible and avoid a hidden multi-call sequence where a stop-loss could
silently fail to attach after a filled entry, a workflow author wires 3
explicit `place_order` node instances: entry (`market`), stop-loss
(`stop_market`, `reduce_only: true`), take-profit
(`take_profit_market`, `reduce_only: true`).

## Known simplifications

This is a proof-of-concept connector; the following are deliberate
shortcuts, not bugs:

- **`place_order` fill data is asymmetric between the two exchanges.**
  Binance's order response carries real execution data, so both Binance
  adapters return the exchange's own `status` plus a true
  `filled_qty`/`avg_price`. OKX's order response is an acknowledgement only
  (`{ordId, clOrdId, tag, ts, sCode, sMsg}`) and carries no fill
  information, so both OKX adapters return `status: "live"` (OKX's term for
  accepted-but-not-yet-filled) with `filled_qty: 0.0` and `avg_price: 0.0`.
  A caller that needs real fill status on OKX must call `get_positions`
  (futures) afterwards.
- **One-way/net position mode only.** Hedge mode (simultaneous long and
  short on the same symbol) is not supported by either futures adapter.
- **Cross margin only** on OKX futures — isolated margin mode is not
  exposed.
- **Balance/positions/set-leverage endpoint shapes are implementation-time
  assumptions**, not verified against a live account at the time this was
  written — see the design doc's "Open verification items" before trusting
  them beyond testnet.
- **`get_balance`'s `locked` field is not a uniform concept across the 4
  adapters.** It always means "not available for placing a new order right
  now," but on Binance Spot and OKX that's funds held by resting orders
  (plus, on OKX, other frozen account funds), while on Binance Futures it is
  `max(total - free, 0.0)`, which also folds in margin already committed to
  open positions.
- **On OKX futures/swaps, `quantity` is OKX's native contract count
  (`sz`), not a base-currency amount** — unlike the other 3 adapters, which
  all take a base-currency quantity. OKX perpetual swaps quote size in
  whole contracts (e.g. one BTC-USDT-SWAP contract might equal 0.01 BTC),
  and this plugin has no access to the per-instrument contract multiplier
  needed to convert between the two, so callers must know the contract size
  for the instrument they're trading.

## Configuration

Two auth providers are declared, one per exchange (unchanged from spot-only —
the same connected account works for both `market_type: spot` and
`market_type: futures` node instances):

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
