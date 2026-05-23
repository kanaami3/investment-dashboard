"""Minimal OANDA v20 REST client.

Uses ``requests`` (no third-party OANDA SDK) so the surface area is small
enough to audit. Authentication is a Bearer token; account id is part of
the URL path.

Environments:
    practice -> https://api-fxpractice.oanda.com
    live     -> https://api-fxtrade.oanda.com

Reference: https://developer.oanda.com/rest-live-v20/introduction/
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd
import requests


_LOG = logging.getLogger(__name__)

_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live":     "https://api-fxtrade.oanda.com",
}


class OandaError(RuntimeError):
    """Raised for non-2xx responses or transport errors after retries."""


@dataclass
class Candle:
    time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool


class OandaClient:
    def __init__(self, token: str, account_id: str, env: str = "practice",
                 timeout: float = 10.0, max_retries: int = 4) -> None:
        if env not in _BASE_URLS:
            raise ValueError(f"env must be one of {list(_BASE_URLS)}, got {env!r}")
        if not token:
            raise ValueError("API token is empty")
        if not account_id:
            raise ValueError("account_id is empty")
        self.base_url = _BASE_URLS[env]
        self.account_id = account_id
        self.env = env
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        })

    # ---- transport ------------------------------------------------------

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        backoff = 1.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self._session.request(method, url, params=params, json=json,
                                          timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                _LOG.warning("OANDA %s %s transport error (try %d): %s",
                             method, path, attempt + 1, e)
            else:
                if r.status_code < 400:
                    return r.json() if r.content else {}
                # Retry 429 and 5xx; surface 4xx immediately with body.
                if r.status_code in (429,) or 500 <= r.status_code < 600:
                    last_exc = OandaError(f"{r.status_code} {r.text[:300]}")
                    _LOG.warning("OANDA %s %s -> %d (try %d) %s",
                                 method, path, r.status_code, attempt + 1, r.text[:200])
                else:
                    raise OandaError(f"{r.status_code} {r.text[:500]}")
            if attempt < self.max_retries:
                time.sleep(backoff)
                backoff *= 2
        raise OandaError(f"OANDA {method} {path} failed after retries: {last_exc}")

    # ---- account / pricing ---------------------------------------------

    def get_account_summary(self) -> dict:
        return self._request("GET", f"/v3/accounts/{self.account_id}/summary")["account"]

    def get_pricing(self, instruments: str | Iterable[str]) -> list[dict]:
        if isinstance(instruments, str):
            ins = instruments
        else:
            ins = ",".join(instruments)
        data = self._request("GET", f"/v3/accounts/{self.account_id}/pricing",
                             params={"instruments": ins})
        return data.get("prices", [])

    def get_instrument(self, instrument: str) -> dict | None:
        data = self._request("GET", f"/v3/accounts/{self.account_id}/instruments",
                             params={"instruments": instrument})
        items = data.get("instruments", [])
        return items[0] if items else None

    # ---- candles -------------------------------------------------------

    def get_candles(self, instrument: str, granularity: str = "M5",
                    count: int | None = None,
                    from_time: pd.Timestamp | None = None,
                    to_time: pd.Timestamp | None = None,
                    price: str = "M",
                    smooth: bool = False,
                    include_incomplete: bool = False) -> pd.DataFrame:
        """Return a DataFrame indexed by UTC timestamp.

        ``price`` is one of ``M`` (mid), ``B`` (bid), ``A`` (ask), or any
        combination like ``MBA`` — we extract the requested column.
        """
        params: dict[str, Any] = {
            "granularity": granularity, "price": price, "smooth": str(smooth).lower(),
        }
        if count is not None:
            params["count"] = int(count)
        if from_time is not None:
            params["from"] = pd.Timestamp(from_time).tz_convert("UTC").isoformat().replace("+00:00", "Z") \
                             if pd.Timestamp(from_time).tzinfo else pd.Timestamp(from_time, tz="UTC").isoformat().replace("+00:00", "Z")
        if to_time is not None:
            params["to"]   = pd.Timestamp(to_time).tz_convert("UTC").isoformat().replace("+00:00", "Z") \
                             if pd.Timestamp(to_time).tzinfo else pd.Timestamp(to_time, tz="UTC").isoformat().replace("+00:00", "Z")
        data = self._request("GET", f"/v3/instruments/{instrument}/candles",
                             params=params)
        rows = []
        side_key = {"M": "mid", "B": "bid", "A": "ask"}[price[0]]
        for c in data.get("candles", []):
            if not include_incomplete and not c.get("complete", False):
                continue
            ohlc = c[side_key]
            rows.append({
                "datetime": pd.Timestamp(c["time"]).tz_convert("UTC"),
                "open":   float(ohlc["o"]),
                "high":   float(ohlc["h"]),
                "low":    float(ohlc["l"]),
                "close":  float(ohlc["c"]),
                "volume": float(c.get("volume", 0)),
                "complete": bool(c.get("complete", False)),
            })
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close",
                                         "volume", "complete"])
        df = pd.DataFrame(rows).set_index("datetime").sort_index()
        return df

    # ---- positions / orders -------------------------------------------

    def get_open_position(self, instrument: str) -> dict | None:
        try:
            data = self._request("GET",
                                 f"/v3/accounts/{self.account_id}/positions/{instrument}")
        except OandaError as e:
            if str(e).startswith("404"):
                return None
            raise
        pos = data.get("position", {})
        long_units  = float(pos.get("long",  {}).get("units", 0) or 0)
        short_units = float(pos.get("short", {}).get("units", 0) or 0)
        if long_units == 0 and short_units == 0:
            return None
        return pos

    def get_open_positions(self) -> list[dict]:
        data = self._request("GET", f"/v3/accounts/{self.account_id}/openPositions")
        return data.get("positions", [])

    def place_market_order(self, instrument: str, units: int,
                           sl_price: float | None = None,
                           tp_price: float | None = None,
                           client_tag: str | None = None) -> dict:
        """Place a market order. Positive ``units`` = long, negative = short.

        SL/TP are absolute prices; OANDA enforces ``sl_price`` is below
        entry for longs / above for shorts.
        """
        order: dict[str, Any] = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(int(units)),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
        }
        if sl_price is not None:
            order["stopLossOnFill"] = {"price": f"{sl_price:.5f}",
                                       "timeInForce": "GTC"}
        if tp_price is not None:
            order["takeProfitOnFill"] = {"price": f"{tp_price:.5f}",
                                         "timeInForce": "GTC"}
        if client_tag:
            order["clientExtensions"] = {"tag": client_tag, "id": client_tag}
        body = {"order": order}
        return self._request("POST", f"/v3/accounts/{self.account_id}/orders",
                             json=body)

    def close_position(self, instrument: str, long: bool = True, short: bool = True
                       ) -> dict:
        body: dict[str, Any] = {}
        if long:  body["longUnits"]  = "ALL"
        if short: body["shortUnits"] = "ALL"
        return self._request("PUT",
                             f"/v3/accounts/{self.account_id}/positions/{instrument}/close",
                             json=body)
