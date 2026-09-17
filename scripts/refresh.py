import json, urllib.request, urllib.parse, datetime, os
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(__file__))
PATH = os.path.join(ROOT, 'data', 'dashboard.json')
PROBE_PATH = os.path.join(ROOT, 'data', 'cnbc_probe.json')
NY = ZoneInfo('America/New_York')
CNBC_BASE = 'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol'

# Known-good Treasury symbols plus candidate CNBC symbols for the next NasBoard feeds.
# Probe results are saved so we can verify exact symbols before wiring them into signals.
PROBE_SYMBOLS = [
    'US10Y', 'US2Y', 'QQQ', 'NVDA', 'AMD', 'AVGO', 'TSM',
    '.VIX', 'VIX', '.VXN', 'VXN', '.DXY', 'DXY',
    '@CL.1', 'CL.1', '@LCO.1', 'LCO.1', '@CO.1', 'CO.1'
]

def cnbc_quotes(symbols):
    params = {'symbols':'|'.join(symbols),'requestMethod':'itv','noform':'1','partnerId':'2','fund':'1','exthrs':'1','output':'json','events':'1'}
    url = CNBC_BASE + '?' + urllib.parse.urlencode(params, safe='|@.')
    req = urllib.request.Request(url, headers={
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36',
        'Accept':'application/json,text/plain,*/*','Referer':'https://www.cnbc.com/'})
    print('CNBC endpoint:', CNBC_BASE)
    print('CNBC symbols:', ', '.join(symbols))
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode('utf-8', errors='replace')
        print('CNBC HTTP status:', r.status)
        print('CNBC content-type:', r.headers.get('content-type'))
    data = json.loads(raw)
    result = data.get('FormattedQuoteResult', {})
    quotes = result.get('FormattedQuote', result.get('formattedQuote', []))
    if isinstance(quotes, dict): quotes=[quotes]
    if not isinstance(quotes, list): raise RuntimeError('CNBC response did not contain a quote list')
    out={}
    for q in quotes:
        sym=q.get('symbol')
        if sym:
            out[sym]=q
            print('CNBC parsed', sym, 'code=', q.get('code'), 'name=', q.get('name'), 'last=', q.get('last'), 'prev=', q.get('previous_day_closing'), 'time=', q.get('last_time'))
    return out

def number(v):
    if v is None: return None
    s=str(v).replace(',','').replace('%','').replace('$','').strip()
    if s in ('','--','N/A','null'): return None
    try: return float(s)
    except ValueError: return None

def setrow(rows,name,latest,direction,signal,freshness,source=None):
    r=next(x for x in rows if x['factor']==name)
    r.update(latest=latest,direction=direction,signal=signal,freshness=freshness)
    if source: r['source']=source

def yield_signal(value):
    return 'negative' if value>=4.5 else ('mixed' if value>=4.0 else 'positive')

def main():
    with open(PATH,encoding='utf-8') as f: d=json.load(f)
    now=datetime.datetime.now(NY)
    quotes={}
    try:
        quotes=cnbc_quotes(PROBE_SYMBOLS)
        probe=[]
        for requested in PROBE_SYMBOLS:
            q=quotes.get(requested)
            probe.append({'requested':requested,'found':bool(q),'symbol':q.get('symbol') if q else None,'code':q.get('code') if q else None,'name':q.get('name') if q else None,'last':q.get('last') if q else None,'previous_close':q.get('previous_day_closing') if q else None,'change':q.get('change') if q else None,'change_pct':q.get('change_pct') if q else None,'last_time':q.get('last_time') if q else None,'type':q.get('type') if q else None,'exchange':q.get('exchange') if q else None,'source':q.get('source') if q else None})
        with open(PROBE_PATH,'w',encoding='utf-8') as f: json.dump({'testedET':now.isoformat(),'results':probe},f,ensure_ascii=False,indent=2)

        for symbol,name in [('US10Y','10Y nominal yield'),('US2Y','2Y Treasury yield')]:
            q=quotes.get(symbol)
            if not q: raise RuntimeError(f'Missing {symbol} in CNBC response')
            value=number(q.get('last'))
            if value is None: raise RuntimeError(f'No usable last value for {symbol}')
            prev=number(q.get('previous_day_closing'))
            bp=(value-prev)*100 if prev is not None else None
            move=f' ({bp:+.1f} bp vs prev close)' if bp is not None else ''
            stamp=q.get('last_time') or q.get('last_timedate') or 'timestamp unavailable'
            setrow(d['rows'],name,f'{value:.3f}%{move}','Rising' if bp is not None and bp>0 else ('Falling' if bp is not None and bp<0 else 'Flat/unknown'),yield_signal(value),f'CNBC intraday · {stamp}','CNBC intraday quote feed')
    except Exception as e:
        print('CNBC ADAPTER/PROBE FAILED:',repr(e))
        for name in ('10Y nominal yield','2Y Treasury yield'):
            next(x for x in d['rows'] if x['factor']==name)['freshness']='STALE — CNBC refresh failed'

    real=next(x for x in d['rows'] if x['factor']=='10Y real yield')
    real['freshness']='STALE — live source not yet connected'
    real['source']='Live real-yield source pending (FRED disabled)'
    d['updatedET']=now.strftime('%b %d, %Y · %H:%M ET')
    d['nextUpdateET']='09:30 / 10:30 ET on trading weekdays'
    with open(PATH,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)

if __name__=='__main__': main()
