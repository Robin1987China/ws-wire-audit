# LBank Public API Contract Findings

> English translation of the Chinese original kept as `contract-audit.md` in this repository.
> Finding IDs, numbers, URLs, field names and API names are preserved verbatim; the wording is a faithful rendering, not a summary.
> Translated on 2026-09-23.

> A public findings list for the exchange's engineering team. It covers only public documentation and public market-data endpoints, and contains no non-public interfaces.

**Document nature**: A public findings list for the exchange's engineering team and third-party integrators.
**Scope**: LBank's spot and futures **public** API (public market-data endpoints and public technical documentation). This list **does not cover** signed, account, trading, or funding interfaces.
**Observation time**: 2026-09-21 (UTC+8); L-21 was additionally re-tested on 2026-09-23. Measurement methods and environment are given in Appendix A.
**Evidence levels**: **[A]** official documentation text / measured on official endpoints (reproducible) | **[B]** third-party public sources (open-source library source code, institutional-grade connector documentation) | **[C]** self-media and aggregator leads (**not used** in this pass).
**Traceable numbers**: every number in this document states how it was obtained; citations that readers cannot independently reproduce are marked "**to be published**" at each occurrence and collected in Appendix C.

---

## 1. Summary

**Total numbered findings: 23.**

| Category | Count | IDs |
|---|---|---|
| Documentation–implementation mismatch | 7 | L-01, L-02, L-03, L-05, L-06, L-07, L-11 |
| Documentation gap (content not written) | 10 | L-04, L-08, L-09, L-10, L-13, L-15, L-16, L-17, L-19, L-20 |
| Reachability / repo maintenance (not contract) | 3 | L-14, L-22, L-23 |
| Behavioural observation (this observation, n=1) | 1 | L-21 |
| Undetermined (this list draws no conclusion) | 1 | L-18 |
| Closed (not a defect, kept as background) | 1 | L-12 |
| **Total** | **23** | |

> **Counting basis**: the title of draft v1.1 of this list once said "24 in total"; counting item by item by ID gives **23**. This version takes the item-by-item count as authoritative.

**4 findings recommended for priority handling (L-08, L-13, L-01, L-02, in 3 groups)**

1. **L-08 | Daily/weekly/monthly K-line bucket boundaries are aligned to UTC+8, but the returned timestamps are UTC epoch seconds, and the documentation does not declare the boundary time zone.**
   This kind of problem returns no error at all: interpreting K-lines under the wrong time zone only makes downstream silently compute 8 hours off, and it is not easy to notice during the trading session.
2. **L-13 | The rate-limiting section gives only two global quotas; it lacks per-endpoint quotas, rate-limit dimensions, `429`/`Retry-After` semantics, and backoff guidance.**
   Clients can hardly determine the boundary, and can hardly implement a backoff consistent with the official tempo; for market-making/signal clients this is an observability gap.
3. **L-01 / L-02 | The type of the `result` field in the response envelope is inconsistent within the same API set; on some endpoints `msg` is `null`.**
   Strongly typed clients will fail to parse on some endpoints, or will misjudge by using `msg` to decide success.

The remaining **19** distribute by nature as: documentation–implementation mismatch 5 (L-03, L-05, L-06, L-07, L-11), documentation gap 8 (L-04, L-09, L-10, L-15, L-16, L-17, L-19, L-20), reachability and repo maintenance 3 (L-14, L-22, L-23), behavioural observation 1 (L-21), undetermined 1 (L-18), closed 1 (L-12). **This list does not claim that the above problems are equally important, nor does it assess your team's overall quality**; each item states "what it means for developers", and priority is for your side to judge.

> **Count self-consistency**: 4 (priority) + 19 (remaining) = **23**, matching the item-by-item count in the table above; each item appears in exactly one category (this version has eliminated the arithmetic gap in draft v1.1, where "L-12 was counted twice and L-09/L-10/L-11 were not listed").

---

## 2. How to verify what we say

The purpose of this section: so that readers need not believe this document, but can reproduce it themselves.

### 2.1 Prerequisites for reproduction

- All endpoints covered in this document are **public market-data endpoints**: no `api_key`, no `sign`, no registration, no account opening required. Documentation text: "To protect API communication from unauthorized change, all **non-public** API calls are required to be signed."
- Any network egress able to reach `api.lbank.info` plus `curl` (or any HTTP client) is enough to reproduce the REST part; for the WebSocket part, use any client conforming to RFC6455.
- The documentation requires API calls to be initiated from a **non-mainland-China egress** (original text: *"Please initiate API calls with non-China IP"*). Different egress regions change the reachability conclusion (see L-23), but do not affect contract-type conclusions.
- The official documentation has two entry points: `https://www.lbank.info/docs/index.html` (spot) and `https://www.lbank.info/docs/contract.html` (futures). Quotations of documentation text in this document always give the **subsection name**, which can be searched directly on that page.

### 2.2 Three kinds of evidence, and how each is verified

| Level | Meaning | How the reader verifies |
|---|---|---|
| **A** (documentation text) | We quote sentences/tables directly from the official documentation | Open the corresponding subsection and compare word by word. Quotations in this document are marked as quoted text or as the original sentence, and the subsection name is given |
| **A** (endpoint measurement) | We send **read-only** requests to public market-data endpoints | Copy the `curl` in this document, run it as is, and compare the response fields |
| **B** (third-party public source) | Open-source library source code, institutional-grade connector documentation | Search the open-source project repository by **symbol name** (line numbers vary with version, so this document locates by symbol name) |

### 2.3 Reproduction discipline (we follow it, and recommend that reproducers follow it too)

- Read-only GET/POST to **public** endpoints only; no signing, no account, no trading, no funding operations;
- Executed singly and sequentially, with intervals ≥1.2 seconds; **no concurrency, no retries, no scanning, no load testing**;
- No bypassing of any access control (the location-restriction page of L-23 is one example: we switched to another official entry point and performed no bypass whatsoever).

### 2.4 If your results differ from ours

- **Market values change over time**, so conclusions such as L-01/L-02/L-03/L-13/L-15~L-20 are independent of specific values; only field types, field presence, and documentation wording matter;
- **Time-zone conclusions (L-08/L-09/L-10) are judged solely by bucket boundaries**, independent of specific prices: you need only compare the conversion relationship between "request time" and "the timestamp of the first returned bucket";
- Different regional egress changes the conclusion of L-23;
- If some item has already been fixed, please let us know, and we will mark it as closed in the review record.

### 2.5 What we can provide

- The **full original HTTP/WS response** for any item (including handshake headers), provided item by item;
- The complete request list of the above 20 accesses (Appendix A already lists the endpoints and parameters);
- Line numbers in the verbatim documentation copies on which we based our locating (the externalised carrier format is **to be published**, see Appendix C).

---

## 3. Findings

> Structure of each item: **problem → reproduction steps → observed behaviour → impact → recommended fix** (with evidence level).
> "This observation" = a single observation, not a general characterisation; for the judging method of "undetermined" items see §5.

### Group A | Response envelope

#### L-01 The `result` field type is inconsistent within the same set of public APIs

**Evidence level**: A (official documentation text + live testing against official endpoints)

**Problem**
The Response Format table in the official documentation lists the type of the `result` field as `String`. Live testing shows two types coexisting under the same domain: some endpoints return a JSON boolean, while others return a JSON string.

**Reproduction steps**
1. `curl "https://api.lbank.info/v2/supplement/ticker/price.do?symbol=btc_usdt"`
2. `curl "https://api.lbank.info/v2/ticker/24hr.do?symbol=btc_usdt"`
3. `curl "https://api.lbank.info/v2/depth.do?symbol=btc_usdt&size=5"`
4. Compare the JSON type of the `result` field (boolean or string) in the three response root objects

**Observed behaviour (this observation)**
- Step 1 → `{"result": true, ...}`: JSON **boolean**;
- Steps 2 and 3 → `{"result": "true", ...}`: JSON **string**;
- `supplement/ticker/bookTicker.do` and `kline.do` match step 2 (string form);
- The type listed in the Response Format table in the official documentation is `String`.

**Impact**
Statically typed clients (struct bindings in Go/Rust/Java, Pydantic/dataclass validation) will fail to parse at **some endpoints**, or be forced to write a dual-type compatibility layer for `result`; if downstream code tests with `if result:`, the string `"true"` is silently treated as true and the error is swallowed.

**Suggested fix**
Standardise on JSON boolean. If a backward-compatible transition is needed, list the actual type per endpoint in the Response Format table and note the change plan in the changelog.

---

#### L-02 The `msg` field is `null` on some endpoints

**Evidence level**: A (official documentation text + live testing against official endpoints)

**Problem**
The Response Format table in the official documentation states that the response contains a `msg` field; live testing shows that on some public endpoints `msg` is `null` or missing.

**Reproduction steps**
1. `curl "https://api.lbank.info/v2/supplement/ticker/price.do?symbol=btc_usdt"`
2. `curl -X POST "https://api.lbank.info/v2/supplement/system_ping.do"`
3. Inspect the `msg` field of the two response root objects

**Observed behaviour (this observation)**
- Both requests return HTTP 200 and `error_code: 0`, but `"msg": null`;
- The Response Format table in the official documentation lists this field as present.

**Impact**
Clients that determine success via `msg == "Success"` will treat a successful response as a failure; the inverse form (`if msg: treat as failure`) may also miss cases.

**Suggested fix**
Always return a non-empty string for `msg` (`"Success"` on success); or state explicitly in the documentation that "`msg` may be null, please rely on `error_code`", and write this convention into the examples of each language SDK.

---

#### L-03 The message text of error code 10003 does not match the documentation

**Evidence level**: A (official documentation text + live testing against official endpoints)

**Problem**
The error code table in the official documentation lists the message text for `10003` as `Invalid parameter`; the `msg` actually returned is `Illegal parameter`.

**Reproduction steps**
```
curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=3&type=minute1"
```
(`time` is deliberately omitted: `time` is the required parameter marked as such in the documentation)

**Observed behaviour (this observation)**
HTTP 200, response body `{"result":"false","error_code":10003,"msg":"Illegal parameter"}`; whereas the message text for 10003 in the documentation's error code table is `Invalid parameter`.

**Impact**
String matching based on the documented message text (log alerts, automatic retry rules, error classification mappings) will fail; SDK error mappings keyed on the message text will misclassify.

**Suggested fix**
Standardise the message text. A more fundamental approach is to state in the documentation that "**only `error_code` is authoritative; `msg` is for human reading only**", and have the examples in each language follow that convention.

---

#### L-04 The error code table has block gaps in numbering

**Evidence level**: A (official documentation text; method is reproducible)

**Problem**
The error code table has large gaps within its ranges, so clients cannot exhaustively enumerate error branches.

**Reproduction steps**
1. Open the `Error Code` subsection of the spot documentation;
2. Copy out all the 5-digit numbers in the first column of the table (or search the browser for `^1[0-9]{4}`);
3. After sorting, look at the differences between adjacent values and the missing numbers within the ranges.

**Observed behaviour**
- The table contains **84** codes in total, ranging from 10000–10801;
- After `10039` it jumps directly to `10066` (missing **10040–10065**, 26 numbers);
- After `10067` it jumps directly to `10100` (missing **10068–10099**, 32 numbers);
- The same method reveals smaller gaps: `10115`, `10124`, `10129–10131`, `10204`, `10602–10605`, etc.

**Impact**
Clients can only write `default: unknown_error`, and any code not listed falls into the fallback branch. For automated trading systems this means "unknown error" may simultaneously cover situations that should be handled differently, such as "insufficient funds" and "insufficient permissions".

**Suggested fix**
Fill in placeholder notes (which ranges are deprecated, which are reserved); or provide a complete machine-readable code table (JSON/CSV) so that clients and SDKs can generate from it.

---

#### L-05 The descriptions of error codes 10014 and 10016 are duplicated

**Evidence level**: A (official documentation text)

**Problem**
In the error code table, `10014` and `10016` have exactly the same description (both are `Currency is not enough`); at the documentation level the two codes carry no distinguishing semantics.

**Reproduction steps**
Open the `Error Code` subsection of the spot documentation, locate the `10014` and `10016` rows, and compare the description column.

**Observed behaviour**
The two rows have character-for-character identical descriptions, both `Currency is not enough`.

**Impact**
Clients cannot determine whether the two codes correspond to different preconditions (for example "insufficient available balance" versus "insufficient total after freezing"), and can only handle them together.

**Suggested fix**
Give the two codes distinguishable definitions; if there is no difference, merge them into one code.

---

### Group B | Signature and authentication documentation

#### L-06 The spelling `HmacSHA556` in the contract documentation's signature example is wrong

**Evidence level**: A (official documentation text)

**Problem**
In the signature string example in the contract documentation, the signature algorithm name is written as `HmacSHA556` (**1 occurrence**); elsewhere in the document there are **11 occurrences** of the correct `HmacSHA256`.

**Reproduction steps**
1. Open the signature example subsection of the contract documentation at `https://www.lbank.info/docs/contract.html`;
2. Search within the page for `HmacSHA` (or use the browser's "View page source" and then search);
3. Count the digits following `HmacSHA`.

**Observed behaviour**
- `HmacSHA256` × **11**;
- `HmacSHA556` × **1**, appearing in the signature string example: `string parameters="...&signature_method=HmacSHA556&timestamp=91654"`.

**Impact**
Clients that copy the example will obtain an invalid signature algorithm name, the signature request will inevitably fail, and the returned error message will not point at this spelling — this is integration friction that can be eliminated in place.

**Suggested fix**
Change 1 character.

---

#### L-07 The timestamp in the contract signature example is truncated

**Evidence level**: A (verbatim official documentation)

**Finding**
In the same example signature string, the `timestamp` has only 5 digits, while a real millisecond timestamp has 13 digits.

**Reproduction steps**
In the signature subsection of the contract documentation, compare the value of `timestamp` in the "string to be signed example" and in the "submitted signature parameters".

**Observed behaviour**
- String-to-be-signed example: `...&timestamp=91654` (**5 digits**);
- Submitted-parameters example: `...&timestamp=1665990154559` (**13 digits**, milliseconds).

**Impact**
The example **cannot be copied and run as-is**. Combined with L-06, the path of "copy the example" does not work, and integrators can only determine the correct form by trial and error.

**Suggested fix**
Replace the example signature string with a complete, directly verifiable sample; it is recommended to also provide a test vector of "known secret → known sign", which is the single most time-saving addition for integrators.

---

### Group C | Time and granularity semantics

#### L-08 Daily/weekly/monthly k-line bucket boundaries are aligned to UTC+8, but the returned values are UTC epoch seconds

**Evidence level**: A (measured against official endpoints; arithmetic reproducible)

**Finding**
The k-line timestamps returned by `kline.do` are standard Unix epoch seconds (UTC semantics), but the bucket boundaries of `day1` are split by UTC+8. The documentation does not declare the boundary time zone in the k-line return description.

**Reproduction steps**
1. Take the current second-level timestamp (or use the `time` from the documentation example directly):
   `curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=3&type=day1&time=1769914800"`
2. Take the first element of the first bar of the returned array (the bucket start timestamp);
3. Convert that timestamp according to **UTC** and **UTC+8** respectively, and compare with the requested `time`;
4. Control group: perform the same conversion for `type=minute1`.
   `curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=3&type=minute1&time=1789984246"`

**Observed behaviour (this observation)**
- Daily (step 1): request `time=1769914800` = 2026-02-01 **03:00 UTC** = 2026-02-01 **11:00 UTC+8**; returned first bucket `1769875200` = 2026-01-31 **16:00 UTC** = 2026-02-01 **00:00 UTC+8**.
  → The request moment is 11:00 UTC+8, and the first returned daily bar starts at **midnight UTC+8 of that same day**: **bucket boundaries are aligned to UTC+8**, while the timestamps themselves are UTC epoch seconds.
- Minute bars (step 4): request `time=1789984246` (UTC+8 17:50:46) → returned first bucket `1789984200` (UTC+8 17:50:00).
  → Minute-level buckets are minute-aligned, with **no time-zone offset**.

**Impact**
When aligning daily bars across exchanges, interpreting LBank's daily epoch seconds as "UTC day" will be off by 8 hours from exchanges that split buckets by UTC; deriving the daily index backwards from "local date → epoch seconds" will fetch the wrong bucket. The whole process returns no error at all.

**Suggested fix**
Explicitly state in the k-line return description that "the bucket boundaries of `day1`/`week1`/`month1` are UTC+8 midnight"; or provide a `utcOffset` / `tz` field.

**Scope limitation**
The bucket-boundary conclusion above is limited to `day1`; the sibling `week1`/`month1` were **not tested individually** (see §V).

---

#### L-09 The `start` of a one-shot WS request accepts a time-zone-less ISO string, and the documentation explicitly states it is interpreted as Beijing time

**Evidence level**: A (verbatim official documentation)

**Finding**
The one-shot WS request parameter `start` accepts two formats at the same time, and the two formats have different time-zone semantics.

**Reproduction steps**
Open the `WebSocket API (Market Data)` section of the spot documentation, and locate the description line of the `start` parameter and the example message.

**Observed behaviour**
Documentation text (`start` parameter description):

> Start time. Accept 2 formats, such as 2018-08-03T17:32:00 (beijing time), another timestamp, such as 1533288720 (Accurate to second)

That is: the ISO string is interpreted as **Beijing time**, and the number is interpreted as **epoch seconds (UTC semantics)**.

**Impact**
If a client passes in a locally generated `2026-02-01T03:00:00` (intended as UTC), it will be treated as Beijing time, producing an 8-hour offset; moreover, the direction of the offset varies with the client's time zone.

**Suggested fix**
Accept only ISO 8601 with an explicit time zone (`Z` or `+08:00`); or uniformly switch to epoch seconds.

---

#### L-10 The `TS` field pushed over WS has no time-zone marker

**Evidence level**: A (verbatim official documentation)

**Finding**
Every channel push over WS carries a top-level `TS` (a human-readable string, of the form `"2019-06-28T17:49:22.722"`); the field table only writes `TS | String | Deal time` and does not note the time zone. Within the same push there are other business time fields (such as `trade.TS`, `kbar.t`), whose origin and time zone are likewise undeclared.

**Reproduction steps**
1. Open the push-sample subsection of `WebSocket API (Market Data)` in the spot documentation, and look at the top-level `TS` value of the `kbar` push sample;
2. In the field table of the same subsection, locate the `TS` row and the description column.

**Observed behaviour**
- Sample value: `"TS":"2019-06-28T17:49:22.722"` (no `Z`, no time-zone offset);
- Field table: `TS | String | Deal time`.

**Status limitation**
This WS session did not persist the actual value of `TS` in business frames, therefore **the time-zone attribution of `TS` is "undetermined"**; what has been verified is only the point "no time-zone marker" (see §V for the determination method).

**Impact**
Mixing `TS` with epoch-second fields introduces a systematic deviation of 0 or 8 hours, and it is not easy to spot during the daytime session (the prices look reasonable).

**Suggested fix**
Make `TS` uniformly ISO 8601 with `Z`; or add a time-zone note in the field table.

---

#### L-11 REST's `type` and WS's `kbar` use two different sets of time-granularity naming

**Evidence level**: A (verbatim official documentation) + B (source code of a third-party open-source library)

**Finding**
The two channels of the same exchange use two sets of granularity enums, so a single local configuration cannot be shared.

**Reproduction steps**
1. Spot documentation `Query K Bar Data` section → the enum of the `type` parameter;
2. Spot documentation `WebSocket` section → the `kbar` subscription sample and values;
3. Compare against the LBank implementation of the third-party open-source library CCXT: the REST granularity table is located in `timeframes` in `ccxt/pro/lbank.py`, and the WS granularity table is located in `options.watchOHLCV.timeframes` in `ccxt/pro_lbank.py` (locating them by searching the symbol names is sufficient).

**Observed behaviour**
- REST `type` enum has 11 values: `minute1 / minute5 / minute15 / minute30 / hour1 / hour4 / hour8 / hour12 / day1 / week1 / month1` (**no yearly bar**);
- WS `kbar` values: `1min / 5min / 15min / 30min / 1hr / 4hr / day / week / month / year` (**has yearly bar**);
- CCXT maintains a separate mapping table for WS: `1m→1min`, `5m→5min`, `15m→15min`, `30m→30min`, `1h→1hr`, `4h→4hr`, `1d→day`, `1w→week`, `1M→month`, `1y→year`.

**Impact**
The same local configuration cannot be reused between REST and WS; aligning k-lines across channels requires maintaining two sets of mappings (which is exactly why the third-party library was forced to implement it this way).

**Suggested fix**
Unify the naming (for example, REST and WS share a style such as `1m/1h/1d`), or provide a comparison table of the two channels in the documentation.

---

#### L-12 `kline.do`'s `time` is a required parameter (closed, not a defect)

**Evidence level**: A (official documentation text + official endpoint measurement)
**Characterization**: **closed, not counted as a defect** — the documentation and the implementation are self-consistent. This entry is retained because it is the most common parameter pitfall in integration, and can serve as background.

**Issue**
The `time` parameter of `kline.do` is required (the documentation's parameter table marks `Required = Yes`, type `String`, description `Timestamp (of Seconds)`); omitting it returns `10003`.

**Reproduction steps**
1. The documentation's URL verbatim: `curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=3&type=day1&time=1769914800"`
2. Remove `time`: `curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=3&type=minute1"`

**Observed behaviour (this observation)**
- Step 1 → HTTP 200, `error_code 0`, returns 3 klines (**the documentation example can be copied and run verbatim**);
- Step 2 → HTTP 200, `error_code 10003`.

**Impact**
Omitting `time` only yields `10003 Illegal parameter`; the error message does not point to the missing parameter name, and it is easily misjudged as an "endpoint failure" or a "documentation–implementation mismatch" (our own initial verification round did list this endpoint as a suspected contract discrepancy for this reason). The documentation and the implementation are themselves self-consistent, so this entry is not counted as a defect.

**Suggested fix (optional, only to reduce integration friction)**
Mark required items prominently in the parameter table; indicate the missing parameter name in the error message.

---

### Group D | Error codes and rate limiting

#### L-13 The rate limiting section has only two global quotas, lacking a quota table and `429` semantics

**Evidence level**: A (official documentation text)

**Issue**
The rate limiting section gives only two global quotas; **at the public level, none is seen** of per-endpoint (or per-weight) quotas, rate limiting dimensions, remaining-quota feedback, `429`/`Retry-After` semantics, or the ban policy after exceeding limits.

**Reproduction steps**
Open the spot documentation's `Endpoint Rate Limit` subsection and read its entire body.

**Observed behaviour**
The body of that subsection has only two lines:

> Create order and cancel order Request 500/10s
> The other Request 200/10s

Not seen at the public level: a per-endpoint weight table, rate limiting dimensions (IP / UID / api_key), a quota query endpoint, `429` / `Retry-After` descriptions, a ban or degradation policy after exceeding limits.

**Impact**
A client can only learn the boundary when it "hits an error"; without `Retry-After`, a client can only back off at a pace of its own assumption, and in high-frequency scenarios it easily slides from "being rate limited" to "being banned". For market-making/signal-type clients, this is an observability gap rather than a mere documentation blemish.

**Suggested fix**
1. Provide a per-endpoint (or per-weight) quota table;
2. Return an **explicit HTTP status code and `Retry-After`** when limits are exceeded;
3. Return the remaining quota in response headers;
4. Provide an endpoint to query the current quota.

**Cross-reference note**
Some mainstream exchanges publish finer rate limiting details and response header conventions. This list **did not re-verify** these cross-reference items in this measurement, so they are listed as "to be published" (Appendix C) and no factual assertion is made here.

---

#### L-14 No test environment description is seen at the public level

**Evidence level**: A (official documentation text) + B (third-party open-source library source code)

**Issue**
In the public documentation, **no** independent testnet / sandbox domain and test asset description is seen.

**Reproduction steps**
1. Search the spot documentation and the contract documentation for `test` / `sandbox` / `testnet`, and examine the context of the hits;
2. Examine the `sandbox`-related configuration in the third-party open-source library CCXT's LBank implementation (`ccxt/pro/lbank.py`, searched by symbol name).

**Observed behaviour**
- The spot documentation has only one occurrence: `POST /v2/supplement/create_order_test.do`, and the documentation does not state its scope of effect;
- The contract documentation has a section `test account`, which gives **plaintext example credentials** (of the form `String privateKey = "…"`), closer to a signature demonstration than a usable environment;
- In CCXT's LBank implementation, `'sandbox': False`.

**Wording limitation**
This list only asserts that "**at the public level, no** usable test environment description is seen". Whether an independent environment is provided to institutional clients is within a scope we cannot see, and this list makes no inference.

**Impact**
In the absence of a public test environment, changes to order placement, order cancellation, reconnection, and risk control logic can usually only be verified on the mainnet, which is one of the integration frictions most often mentioned by integrators.

**Suggested fix**
Publish a testnet domain and test assets; or clarify the semantics and scope of application of `create_order_test.do` in the documentation.

---

### Group E | Documentation completeness of endpoints and paths

#### L-15 Several still-used public endpoints are undocumented

**Evidence level**: A (official documentation search) + B (third-party open-source library source code)

**Issue**
The following endpoints are still used by third-party libraries (some measured as usable), but the official documentation has **no parameter table and no return description**: `/v2/usdToCny.do`, `/v2/incrDepth.do`, `/v2/trades.do` (without the `supplement/` prefix), `/v2/ticker.do`.

**Reproduction steps**
Search the entire spot documentation for the following strings and record the hit locations and context: `usdToCny`, `incrDepth`, `trades.do`, `ticker.do`.

**Observed behaviour**
- `usdToCny` → 0 hits; `incrDepth` → 0 hits;
- `ticker.do` → only **2** hits, both in the changelog: one is "recommended to replace `ticker.do` with `ticker/24hr.do`", the other is an Update entry dated 2022.11.03; **neither has a parameter table or return description**;
- The third-party open-source library CCXT still lists `usdToCny`, `incrDepth`, `trades`, `ticker` as public endpoints.

**Impact**
Third-party libraries depending on **undocumented** endpoints means the contract makes no commitment: they may be taken down at any time with no one notified.

**Suggested fix**
Add documentation; or list them in the documentation's existing `Abandoned Endpoints` section with a deprecation schedule (that section currently has only 1 entry). This list does not assert that these endpoints must be retained; what it asserts is that **the contract must be public**.

---

#### L-16 The second spot REST domain `api.lbkex.com` is not mentioned in the documentation

**Evidence level**: A (official endpoint measurement + official documentation search)

**Issue**
`https://api.lbkex.com/` is functionally equivalent to the primary domain `https://api.lbank.info/` stated in the documentation, but the documentation text never mentions the former.

**Reproduction steps**
1. `curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=3&type=minute1&time=<current second-level timestamp>"`
2. Change the domain of the same URL to `https://api.lbkex.com/` and request again;
3. Compare the kline data of the two responses (timestamp, price, quantity);
4. Search the entire spot documentation for `lbkex`.

**Observed behaviour (this observation)**
- The data returned by the two requests is **byte-for-byte identical** (same millisecond, same price, same quantity);
- `lbkex` has **0 hits** in the documentation text.

**Impact**
Developers cannot tell from the documentation whether the second domain is supported, whether it has an SLA, or whether it will be retained long-term; multiple domains also mean that the basis for "failover" and latency comparison must be figured out on one's own.

**Suggested fix**
List all supported domains and their relationships in the documentation (primary / backup / alias), and state whether they share the same contract and quota.

**Limitation**
This entry is a single same-parameter comparison (n=1), and only asserts that "for that request, the two returned consistent results".

---

#### L-17 WS access domain inconsistent between documentation and third-party implementation

**Evidence level**: A (official documentation text) + B (third-party open-source library source code)

**Problem**
The documentation states that the spot WS endpoint is `wss://api.lbank.info/ws/V2/`, whereas the WS implementation of the third-party open-source library CCXT points to a different domain, `wss://www.lbkex.net/ws/V2/`; the latter is not mentioned in the documentation.

**Reproduction steps**
1. Spot documentation `WebSocket` section → access address;
2. Third-party open-source library CCXT `ccxt/pro_lbank.py` → `urls.api.ws` (retrieved by symbol name);
3. Full-text search of the spot documentation for `lbkex.net`.

**Observed behaviour**
- Documentation: `wss://api.lbank.info/ws/V2/`;
- CCXT: `'ws': 'wss://www.lbkex.net/ws/V2/'`;
- `lbkex.net` has **0 hits** in the full documentation text.

**Impact**
Two different edge paths may bring different rate-limiting regimes, behaviour, and statistics; results across clients are not directly comparable (our own measurements must therefore pin the domain).

**Suggested fix**
List all available WS access domains in the documentation; if `www.lbkex.net` is deprecated, give a decommissioning notice in the changelog (third-party libraries still use it).

---

#### L-18 Whether the granularities `hour2` / `hour6` are usable — undetermined

**Evidence level**: A (official documentation enumeration) + B (third-party open-source library source code)
**Status**: **undetermined; these findings draw no conclusion.**

**Problem**
The REST granularity declaration of the third-party open-source library CCXT contains `2h→hour2`, `6h→hour6` (the `timeframes` of `ccxt/pro/lbank.py`), whereas the 11 enumerated values of `type` in the documentation **do not** contain `hour2`/`hour6`. The two are inconsistent, but **these findings draw no conclusion as to which side is correct**.

**Reproduction steps**
1. Open the `Query K Bar Data` section of the spot documentation, read the enumerated values of the `type` parameter;
2. Go to `ccxt/pro/lbank.py` of the third-party open-source library CCXT, search for `timeframes`, read its values;
3. Compare whether both sides contain the 2-hour / 6-hour granularity.

**Observed behaviour**
- The documentation enumerates 11 values, **excluding** `hour2` / `hour6`;
- CCXT declares `2h→hour2`, `6h→hour6`;
- We did **not** issue a live test for `type=hour2` (this measurement did not cover that parameter).

**Impact**
As things stand, developers cannot determine from the documentation whether 2-hour / 6-hour K lines are usable: writing it into a configuration may return `10003`, while not writing it may mean giving up a granularity that is in fact usable.

**Suggested fix**
Supplement the documentation enumeration (if it is indeed supported); or annotate the `type` parameter table with "only the following values are supported" and explain the return behaviour of other values. The determination method for these findings is as follows.

**Why undetermined**
Neither interpretation can be ruled out: it may be that "the documentation enumeration is incomplete", or that "the third-party library over-declares". Documentation and source code alone cannot distinguish them.

**Determination method (a single request suffices)**
```
curl "https://api.lbank.info/v2/kline.do?symbol=btc_usdt&size=2&type=hour2&time=<current second-level timestamp-7200>"
```
- Returns `error_code 0` → the documentation enumeration is incomplete (reclassify as "documentation gap");
- Returns `error_code 10003` → the third-party library over-declares (the documentation is correct).

---

#### L-19 `etfTicker/24hr.do` requires `symbol`, but the documentation gives no way to enumerate leveraged token trading pairs

**Evidence level**: A (official documentation text + official endpoint measurement)

**Problem**
The `symbol` of `etfTicker/24hr.do` is required; when stating "excluding leveraged tokens", the method the documentation gives **points back to that endpoint itself**, and no legitimate source for ETF trading pairs is given.

**Reproduction steps**
1. `curl "https://api.lbank.info/v2/etfTicker/24hr.do"` (without `symbol`);
2. Open the `24hr Ticker` section of the spot documentation, read the note in parentheses in that section's body.

**Observed behaviour**
- Step 1 → HTTP 200, `error_code 10001`, `msg "Parameter can not be null"` (consistent with the documentation's requirement that `symbol` is mandatory);
- Original text of the body of the `24hr Ticker` section of the documentation:

> GET the LBank coin quote data, excluding Leveraged Tokens trading pairs (get Leveraged Tokens trading pairs GET /v2/etfTicker/24hr.do)

That is: the method given there to "get leveraged token trading pairs" is to call `etfTicker/24hr.do` itself; and that endpoint in turn requires `symbol`. The documentation **gives no enumeration source for ETF trading pairs** (whether `currencyPairs.do` includes ETF pairs is likewise unstated in the documentation).

**Impact**
Developers know that an ETF quote endpoint exists, but do not know where a legitimate `symbol` comes from, and can only proceed by trial and error.

**Suggested fix**
In the `etfTicker/24hr.do` section, explain the source endpoint for ETF trading pairs, and the semantics of `symbol=all`.

---

#### L-20 The WS documentation does not cover subscription limits, compression, reconnection, or dropped-frame detectability

**Evidence level**: A (official documentation search)

**Problem**
The documentation gives no per-connection subscription entry limit, message count limit, connection lifetime, dropped-frame detectability (sequence number/checksum), reconnection and backfill semantics, or compression support.

**Reproduction steps**
Perform a **case-insensitive** full-text search of the spot documentation and the contract documentation, and count the hits for the following keywords: `compress`, `permessage`, `gzip`, `reconnect`, `sequence`, `seq`, `checksum`, `shutdown`.

**Observed behaviour**
- The 8 keywords above have **0 hits** in both documents;
- `subscri` has **58** hits in the documentation that describes subscriptions, but no upper limit co-occurring with `limit`/`max` appears;
- The only connection-liveness constraint given in the documentation is one item (original text): if the client does not respond to the server's Ping within 1 minute, the server closes the connection.

**Impact**
Clients must design reconnection and backpressure themselves; the documentation provides no sequence number or checksum mechanism, so dropped frames are hard to identify directly from protocol fields — the completeness of the local order book must be inferred by the client itself (e.g. periodic snapshot rebuild or comparison of business fields), and the mispricing risk of market-making clients is borne by the client.

**Suggested fix**
Publish the subscription / message / connection limits and the connection lifetime; add a sequence number or checksum to the push; explain whether a reconnection "backfills" or "jumps to the latest"; provide advance notification of server-initiated shutdowns (e.g. a `serverShutdown`-type event).

---

#### L-21 Observed in this run: the spot WS handshake did not negotiate `permessage-deflate`

**Evidence level**: A (measured on the official endpoint; **n=1** originally, **n≥3** after the targeted re-runs on 2026-09-23)

**Problem**
In the single WS handshake on 2026-09-21, no `Sec-WebSocket-Extensions` appeared in the response headers, i.e. this run did not negotiate a compression extension.

**Reproduction steps**
1. Connect to `wss://api.lbank.info/ws/V2/` with any RFC6455 WebSocket client;
2. Record the full handshake response headers;
3. Check whether a `Sec-WebSocket-Extensions` line is present.

**Observed behavior (observed in this run)**
- The handshake returned `HTTP/1.1 101 Switching Protocols` and `Sec-WebSocket-Accept: 8Io10aL1YgoXzF/gH4kWHT3yoIE=`;
- The `Sec-WebSocket-Extensions` response header **did not appear**.

**Wording constraint (important)**
n=1, so we may only write "**not negotiated in this run**". We **must not** infer from this that "the server does not support compression": determining whether the server supports it requires the client to **actively offer** the extension and then observe the response headers. This findings list did not perform that active-offer test (for the determination method see §5). **That active-offer test was subsequently performed on 2026-09-22**, with the conclusion given in `examples/02-permessage-deflate-negotiation.md` and `examples/03-lbank-deflate-ladder-probe.json`: LBank **refused all** three offer variants (including the `client_max_window_bits` and `server_max_window_bits=15` variants), `deflate_status = server_refused`. That is: this item's "not negotiated" **at the time** has been narrowed by the follow-up experiment to "server refused" and is no longer a suspended item.

**Targeted re-runs on 2026-09-23 (n≥3)**
Two further independent handshakes were performed on 2026-09-23 (18:50:53 and 18:56:51 GMT+8), each explicitly offering `Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits`: both returned `HTTP/1.1 101 Switching Protocols` with **no** `Sec-WebSocket-Extensions` response header (`deflate_status = server_refused`). Each run was a single connection with no subscription and no retry, closed as soon as the response headers were read (under 1 second). The direction matches the three-variant ladder of 2026-09-22 → **three independent observations agree, so this item now stands at n≥3**.
**Still undetermined**: whether the refusal happens at the Cloudflare edge or at the origin is not concluded here (locating the responsible layer would require separate evidence).

**Impact (conditional)**
If the server supports it while the client did not offer it, this discrepancy can be eliminated by a client fix; if the server does not support it, then the wire-level byte count of high-frequency trade streams will be markedly higher than that of comparable interfaces which support compression.

**Suggested fix**
The documentation should state explicitly whether `permessage-deflate` is supported; if it is, give the way to enable it.

**Appendix (other observations within the same connection)**
After actively sending `{"action":"ping","ping":"<uuid>"}`, we **immediately** received `{"action":"pong","pong":"<same uuid>"}`; after subscribing to the `tick` channel we received **107** `tick` pushes within 8 seconds (plus 1 frame from the aforementioned pong). This connection **required no key of any kind**.

---

### Group F | Repository and portal operations (non-contract)

#### L-22 The "official documentation repository" appearing in search-engine indexes returns 404

**Evidence level**: A (observed in this run)

**Problem**
`github.com/LBank-exchange/lbank-official-api-docs`, which appears in search results, returns **404**.

**Reproduction steps**
1. Open `https://github.com/LBank-exchange/lbank-official-api-docs`;
2. Use the GitHub API to list the public repositories under the `LBank-exchange` account.

**Observed behavior (observed in this run)**
- That repository returns 404;
- **4** repositories currently exist under the same account, all of the connector type.

**Impact**
Developers following search indexes in search of the "official documentation repository" hit a 404, which lowers trust in the documentation's authority; at the same time there is no issue feedback channel.

**Suggested fix**
Restore that repository (or put up a README pointing back to the official site documentation), and provide a clear documentation feedback channel (an issue template or an email address).

---

#### L-23 The official documentation portal `www.lbank.com/docs/index.html` returns a region-restriction page

**Evidence level**: A (observed in this run)
**Classification**: **a reachability issue, not a contract defect.**

**Problem**
`https://www.lbank.com/docs/index.html` (including `/zh-CN/docs/`) returns a **403** region-restriction page.

**Reproduction steps**
1. `curl -i "https://www.lbank.com/docs/index.html"`;
2. Open `https://www.lbank.info/docs/index.html` and compare the content.

**Observed behavior (observed in this run)**
- Step 1 → HTTP **403**, page text `LBank is currently unavailable in your country or region`;
- Step 2 → HTTP 200, page title likewise `Introduction – LBank API`, and the body paragraphs are word-for-word identical to the portal version.

**Impact**
Documentation reachability varies with the egress region, making it hard for third parties to give a stable URL when citing the documentation (we therefore treat `lbank.info` as authoritative). This is unfavorable for stable citation by the developer community and by AI training corpora.

**Suggested fix**
Do not apply the region policy to documentation pages (or provide a region-neutral documentation domain); and explain the difference in region policy between the documentation entry point and the business portal.

**Statement**
We **did not** attempt any means of circumventing access controls; we merely switched to another official entry point.

---

## 4. Suggested priority order

Ordered by "cost to developers", for your reference (non-binding).

| Priority | Item | Reason |
|---|---|---|
| 1 | L-08 / L-09 / L-10 (timestamp and timezone semantics) | No error is returned and only numeric semantics are affected: interpreting in the wrong timezone is silently off by 8 hours |
| 2 | L-13 (rate-limit semantics) | Determines whether a client can implement correct backoff and backpressure; the absence of this description constitutes an observability gap |
| 3 | L-01 / L-02 (response envelope types) | Strongly typed clients will fail to parse, or will misjudge success via `msg` |
| 4 | L-14 (test environment) | Determines "whether a change can be verified without using real funds" |
| 5 | L-20 / L-21 (WS limits / sequence numbers / compression) | Determines whether a client can build a verifiable local book and backpressure |
| 6 | L-06 / L-07 (signature examples) | The change is minimal and the benefit is immediate |
| 7 | L-03 / L-04 / L-05 (error code tables) | A machine-readable code table is a one-time investment with long-term benefit |
| 8 | L-15 ~ L-19, L-22, L-23 (documentation completeness and reachability) | Affects integration friction and community trust |

---

## 5. Undetermined (this findings list draws no conclusion)

| Item | Status | Single operation required for determination |
|---|---|---|
| Whether WS supports `permessage-deflate` | As of 2026-09-21 this findings list marked it **undetermined** (only "not negotiated in this run" was observed); **a follow-up test was performed on 2026-09-22 → `server_refused`** (see `examples/02`, `examples/03`) | The client **actively offers** the extension and checks whether the response headers return that extension |
| Whether `type=hour2` / `hour6` are available | undetermined | `curl "…/kline.do?symbol=btc_usdt&size=2&type=hour2&time=<now-7200>"` |
| Bucket boundaries of `week1`/`month1` other than `day1` | undetermined (only `day1` was measured) | Request `type=week1` / `type=month1` the same way and compare the first bucket's date |
| The actual timezone attribution of the `TS` field | undetermined (only "no timezone marker" has been verified) | Capture one business push and compare it against the return value of `timestamp.do` |
| The behavior of the futures WS `wss://lbkperpws.lbank.com/ws` | not measured | A single handshake + subscription |
| The legal enumerations of `productGroup` for the futures `instrument` | undetermined (passing `productGroup=1` returned an empty array) | Re-test `instrument` / `marketData` with the documented example value `SwapU` |
| The upper limit on spot WS subscription entries | not determined | Requires staged probing with multiple subscriptions; beyond this run's "single, low-frequency" discipline, so we suggest asking via a support ticket |
| `429` and actual rate-limiting behavior | not determined (for discipline reasons) | Requires written official permission + an isolated environment |

---

## Appendix A: Measurement method and environment

| Item | Content |
|---|---|
| Date and time | 2026-09-21 (UTC+8) |
| Egress | The HTTP(S) proxy configured on this machine (a non-mainland-China egress). The documentation requires calls to be made from a non-China IP. **The specific egress IP was not recorded this time**, so the conclusion involving egress (L-23) is stated only as "this observation" |
| Documentation source 1 | `https://www.lbank.info/docs/index.html` → HTTP 200; verbatim body copy **300,374 bytes / 4,697 lines** (spot documentation) |
| Documentation source 2 | `https://www.lbank.info/docs/contract.html` → HTTP 200; **44,767 bytes** (contract documentation) |
| Total number of requests | **20** (19 HTTP + 1 WS connection), request interval ≥1.2 seconds, **no concurrency / no retries / no scanning / no load testing** |
| Sample size | 2 verbatim documentation copies; 19 public endpoint calls; 1 WS session (8 seconds) |
| Tools | `curl`, Python `requests`, a standard RFC6455 WebSocket client, opening the documentation pages directly in a browser |
| Evidence level | A (verbatim official documentation / live tests against official endpoints), B (third-party public sources); C not used |
| Not touched | Any signed API, account API, trading API, or funding API; no load testing was performed; no access control was bypassed |

**List of endpoints for the 19 HTTP requests (reproducible item by item)**

| # | Endpoint / parameters | Result |
|---|---|---|
| 1 | `GET /v2/kline.do?symbol=btc_usdt&size=3&type=day1&time=1769914800` (as-is from the documentation) | 200, `error_code 0`, returns 3 daily candles |
| 2 | `GET /v2/kline.do?symbol=btc_usdt&size=3&type=minute1&time=1789984246` | 200, `error_code 0`, 3 one-minute candles |
| 3 | `GET /v2/kline.do?symbol=btc_usdt&size=3&type=minute1` (no `time`) | 200, `error_code 10003`, `msg "Illegal parameter"` |
| 4 | Same as #2, with the domain changed to `api.lbkex.com` | 200, `error_code 0`, **byte-for-byte identical** to #2 |
| 5 | `GET /v2/supplement/ticker/price.do?symbol=btc_usdt` | 200, `result` is the **boolean** `true`, `msg` is `null` |
| 6 | `GET /v2/supplement/ticker/bookTicker.do?symbol=btc_usdt` | 200, `result` is the string `"true"` |
| 7 | `GET /v2/ticker/24hr.do?symbol=btc_usdt` | 200, `result` is the string `"true"` |
| 8 | `GET /v2/etfTicker/24hr.do` (no `symbol`) | 200, `error_code 10001`, `msg "Parameter can not be null"` |
| 9 | `GET /v2/supplement/trades.do?symbol=btc_usdt&size=3` | 200, `error_code 0` |
| 10 | `GET /v2/depth.do?symbol=btc_usdt&size=5` | 200, `error_code 0` |
| 11 | `GET /v2/currencyPairs.do` | 200, returns **1361** trading pairs |
| 12 | `GET /v2/accuracy.do` | 200, returns **1361** precision records |
| 13 | `GET /v2/assetConfigs.do` (no `assetCode`) | 200, `error_code 10001` |
| 14 | `GET /v2/timestamp.do` | 200, millisecond timestamp |
| 15 | `POST /v2/supplement/system_ping.do` (no parameters) | 200, `data {}`, `msg` is `null` |
| 16 | `GET https://lbkperp.lbank.com/cfd/openApi/v1/pub/getTime` | 200, `error_code 0` |
| 17 | `GET .../cfd/openApi/v1/pub/instrument?productGroup=1` | 200, but `data` is an empty array (see §5) |
| 18 | `GET .../cfd/openApi/v1/pub/marketOrder?symbol=BTCUSDT&depth=5` | 200, returns `symbol/asks/bids` |
| 19 | `GET https://api.lbank.com/` (connectivity check) | Connection reset (no service on this domain; not counted in the findings) |

**1 WS session**

- Target: `wss://api.lbank.info/ws/V2/` (through the same egress proxy);
- Handshake: `HTTP/1.1 101 Switching Protocols`, `Sec-WebSocket-Accept: 8Io10aL1YgoXzF/gH4kWHT3yoIE=`, no `Sec-WebSocket-Extensions`;
- Sent: an unsolicited `{"action":"ping","ping":"<uuid>"}` + subscription `{"action":"subscribe","subscribe":"tick","pair":"btc_usdt"}`;
- Received: 108 frames within 8 seconds (1 pong frame + 107 `tick` frames);
- End: single connection, no reconnection.

---

## Appendix B: Notes on wording and evidence levels

This checklist follows the conventions below in its wording, so that readers can distinguish **facts** from **judgments**:

| Term | Meaning |
|---|---|
| "verbatim official documentation" | A sentence or table quoted directly from the official documentation; readers can compare it character by character on the documentation page |
| "this observation" | A result we observed in a **single** request on 2026-09-21; not asserted as a general characterization |
| "not found at the public level" | Not found **within the scope of the public materials we searched**; we do not claim that it does not exist (institutional or private materials are not within our visibility) |
| "not determined" | The available materials are insufficient to distinguish among multiple explanations; this checklist draws no conclusion, and gives a method for deciding |
| "0 hits" | The result of a case-insensitive search across the **full text of the two specified official documents**; the method is given in the original text and is reproducible |
| Evidence level A / B / C | Respectively "verbatim official documentation or live tests against official endpoints" / "third-party public sources" / "leads from self-media and aggregator sites (not used this time)" |

**Wording we avoid**: we do not make an overall assessment of the exchange (such as "poor quality", "unprofessional", etc.), and we do not use absolute assertions without sample-size support. Negative conclusions are always rewritten in definable terms such as "not found at the public level".

---

## Appendix C: Publication Handling of Citations

The following citation forms need to be replaced with reader-verifiable forms; the handling recommendations are as follows:

| # | Current state in this version | Content to be published | Handling recommendation |
|---|---|---|---|
| C-1 | Source-document quotes are located by **section name** | The **line numbers** in our verbatim document copy (used for precise location, e.g. line numbers of the error-code table, line numbers of parameter descriptions) | Publish together with the document copy, or change to the form "section name + quoted fragment" (**this version is already written in the latter form**) |
| C-2 | Endpoint test results are described by **request + field** | The full text of the raw HTTP/WS responses and the archive of handshake headers | Publish as a sanitized attachment to the checklist |
| C-3 | Third-party library citations are located by **symbol name** (e.g. `timeframes`, `pro_urls.api.ws` in `ccxt/pro/lbank.py`) | The specific version number / commit id | Record the version before release, so that readers can reproduce with a pinned version |
| C-4 | ~~The 3 third-party statements in §IV~~ | A **publicly citable source** for that institutional-level connector documentation | **Handled (2026-09-23): the entire section was removed.** That source has no public origin, so keeping it would constitute an unsourced assertion; the 3 items concerned were in any case marked "not independently reproduced", and removing them loses no Grade-A conclusion, therefore they are not included in the numbered entry count of this checklist |
| C-5 | The industry comparison item in L-13 | The comparison exchange's rate-limit rules and response-header conventions (**not re-verified** this time) | If the comparison is retained, it must be re-verified item by item with live tests before being written in; otherwise keep the current state (stating only that "some exchanges have more detailed public rules") |
| C-6 | The "egress IP not archived" item in Appendix A | Egress IP / ASN | If needed, it can be recorded later; this version explicitly states that this item was not archived, and the related conclusions are presented only as "this observation" |

---

**Status of this document**: public release. This document concerns only public documentation and public market-data endpoints; it uses no signing, account, trading, or funds interfaces, and no stress testing, scanning, or access-control bypass was performed.
