import json, urllib.request, urllib.parse, datetime, os
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(__file__))
PATH = os.path.join(ROOT, 'data', 'dashboard.json')
NY = ZoneInfo('America/New_York')

CNBC_BASE = 'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol'

def cnbc_quotes(symbols):
    params = {
        'symbols': '|'.join(symbols),
        'requestMethod': 'itv',
        'noform': '1',
        'partnerId': '2',
        'fund': '1',
        'exthrs': '1',
        'output': 'json',
        'events': '1',
    }
    url = CNBC_BASE + '?' + urllib.parse.urlencode(params, safe='|')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36',
        'Accept': 'application/json,text/plain,*/*',
        'Referer': 'https://www.cnbc.com/',
    })
    print('CNBC endpoint:', CNBC_BASE)
    print('CNBC symbols:', ', '.join(symbols))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode('utf-8', errors='replace')
            print('CNBC HTTP status:', r.status)
            print('CNBC content-type:', r.headers.get('content-type'))
            print('CNBC response preview:', raw[:500].replace('\n', ' '))
    except Exception as e:
        print('CNBC REQUEST ERROR:', type(e).__name__, str(e))
        if hasattr(e, 'code'):
            print('CNBC HTTP error code:', e.code)
        try:
            body = e.read().decode('utf-8', errors='replace')
            print('CNBC error response preview:', body[:500].replace('\n', ' '))
        except Exception:
            pass
        raise

    data = json.loads(raw)
    result = data.get('FormattedQuoteResult', {})
    quotes = result.get('FormattedQuote', result.get('formattedQuote', []))
    if isinstance(quotes, dict):
        quotes = [quotes]
    if not isinstance(quotes, list) or not quotes:
        print('CNBC JSON top-level keys:', list(data.keys()))
        print('CNBC FormattedQuoteResult keys:', list(result.keys()) if isinstance(result, dict) else 'not-a-dict')
        raise RuntimeError('CNBC response did not contain a quote list')
    out = {}
    for q in quotes:
        sym = q.get('symbol')
        if sym:
            out[sym] = q
            print('CNBC parsed', sym, 'last=', q.get('last'), 'prev=', q.get('previous_day_closing'), 'time=', q.get('last_time'))
    return out

def number(v):
    if v is None:
        return None
    s = str(v).replace(',', '').replace('%', '').strip()
    if s in ('', '--', 'N/A', 'null'):
        return None
    return float(s)

def setrow(rows, name, latest, direction, signal, freshness, source=None):
    r = next(x for x in rows if x['factor'] == name)
    r.update(latest=latest, direction=direction, signal=signal, freshness=freshness)
    if source:
        r['source'] = source

def yield_signal(value):
    return 'negative' if value >= 4.5 else ('mixed' if value >= 4.0 else 'positive')

def main():
    with open(PATH, encoding='utf-8') as f:
        d = json.load(f)
    now = datetime.datetime.now(NY)

    # CNBC is the primary intraday source for nominal Treasury yields. No FRED is used.
    try:
        quotes = cnbc_quotes(['US10Y', 'US2Y'])
        for symbol, name in [('US10Y', '10Y nominal yield'), ('US2Y', '2Y Treasury yield')]:
            q = quotes.get(symbol)
            if not q:
                raise RuntimeError(f'Missing {symbol} in CNBC response')
            value = number(q.get('last'))
            if value is None:
                raise RuntimeError(f'No usable last value for {symbol}')
            prev = number(q.get('previous_day_closing'))
            bp = (value - prev) * 100 if prev is not None else None
            sig = yield_signal(value)
            move = f" ({bp:+.1f} bp vs prev close)" if bp is not None else ''
            stamp = q.get('last_time') or q.get('last_timedate') or 'timestamp unavailable'
            setrow(d['rows'], name, f'{value:.3f}%{move}',
                   'Rising' if bp is not None and bp > 0 else ('Falling' if bp is not None and bp < 0 else 'Flat/unknown'),
                   sig, f'CNBC intraday · {stamp}', 'CNBC intraday quote feed')
    except Exception as e:
        print('CNBC ADAPTER FAILED:', repr(e))
        for name in ('10Y nominal yield', '2Y Treasury yield'):
            r = next(x for x in d['rows'] if x['factor'] == name)
            r['freshness'] = 'STALE — CNBC refresh failed'

    # CNBC does not provide a directly equivalent 10Y real/TIPS yield quote here.
    # Keep the prior value but explicitly mark it unavailable rather than silently using FRED.
    real = next(x for x in d['rows'] if x['factor'] == '10Y real yield')
    real['freshness'] = 'STALE — live source not yet connected'
    real['source'] = 'Live real-yield source pending (FRED disabled)'

    d['updatedET'] = now.strftime('%b %d, %Y · %H:%M ET')
    d['nextUpdateET'] = '09:30 / 10:30 ET on trading weekdays'
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
