# Example 2 — permessage-deflate negotiation: LBank refuses, Binance accepts

**Tool:** `measure_ws.py` v1.3 · **Observed:** 2026-09-22 · **Interval:** 180 s per venue
**Offers sent (identical header, same order, both venues):**

```
permessage-deflate
permessage-deflate; client_max_window_bits
permessage-deflate; client_max_window_bits=15; server_max_window_bits=15
```

`--deflate-ladder` walks these three variants so that a refusal can be
attributed to the *server's policy* rather than to a malformed offer.

## Result

| Venue | Offer accepted | `deflate_status` | Compressed frames | Inflate failures | `wire_bytes` | `payload_bytes` |
|---|---|---|---|---|---|---|
| LBank | none of 3 | `server_refused` | 0 | 0 | 3,906,417 | 3,825,357 |
| Binance | `permessage-deflate` | `accepted` | 62,058 | 0 | 6,440,029 | 8,194,506 |

- LBank probe ladder: [{"offer": "permessage-deflate", "status": "server_refused"}, {"offer": "permessage-deflate; client_max_window_bits", "status": "server_refused"}, {"offer": "permessage-deflate; client_max_window_bits=15; server_max_window_bits=15", "status": "server_refused"}]
- Binance probe ladder: [{"offer": "permessage-deflate", "status": "accepted"}]
- LBank `Sec-WebSocket-Extensions` values in the 101 response: [] (empty = none sent)

## Why this matters

For Binance, `payload_bytes` (8,194,506) is **larger** than
`wire_bytes` (6,440,029) — i.e. the payload figure is *decompressed*
size and the wire figure is *compressed* size. A client that reports only one of
the two, without saying which, will state a byte count for Binance that differs
from the wire by roughly 27% on this sample.

For LBank, compression is refused, so payload and wire sizes track each other.

**Therefore:** any cross-venue statement of the form "venue X pushes more bytes
than venue Y" must declare (a) whether compression was offered, and (b) whether
the reported byte count is pre- or post-inflate. Without both, the comparison is
between two different physical quantities.

## What this does *not* say

- It does not say LBank is "worse". Compression refusal can be a deliberate
  server-side choice (CPU/memory trade-off), and RFC 7692 makes negotiation
  optional. The finding is a **caliber fact needed to compare correctly**.
- n = 1 session per venue. Server policy is expressed as a handshake response
  and is therefore comparatively stable, but this is still one observation.

## Reproduce

```console
python3 measure_ws.py --venue lbank   --deflate --deflate-ladder --duration 180
python3 measure_ws.py --venue binance --deflate --deflate-ladder --duration 180
```
