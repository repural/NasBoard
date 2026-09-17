import json, os, urllib.parse, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=os.path.dirname(os.path.dirname(__file__))
DATA=os.path.join(ROOT,'data','dashboard.json')
CNBC='https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol'

def fetch_cnbc(symbols):
    params={'symbols':'|'.join(symbols),'requestMethod':'itv','noform':'1','partnerId':'2','fund':'1','exthrs':'1','output':'json','events':'1'}
    req=urllib.request.Request(CNBC+'?'+urllib.parse.urlencode(params),headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.load(r)

def quotes(payload):
    # CNBC has used both Result/Quote and ExtendedQuoteResult/ExtendedQuote wrappers.
    candidates=[]
    if isinstance(payload,dict):
        for key in ('FormattedQuoteResult','ExtendedQuoteResult','QuickQuoteResult'):
            block=payload.get(key,{})
            for qkey in ('FormattedQuote','ExtendedQuote','QuickQuote'):
                v=block.get(qkey,[]) if isinstance(block,dict) else []
                if isinstance(v,dict): v=[v]
                candidates += v
    out={}
    for item in candidates:
        q=item.get('QuickQuote',item) if isinstance(item,dict) else {}
        sym=q.get('symbol') or item.get('symbol')
        if sym: out[sym]=q
    return out

def num(v):
    try: return float(str(v).replace(',','').replace('%','').strip())
    except: return None

def main():
    with open(DATA,encoding='utf-8') as f: d=json.load(f)
    now=datetime.now(ZoneInfo('America/New_York'))
    try:
        q=quotes(fetch_cnbc(['US10Y','US2Y']))
        mapping={'10Y nominal yield':'US10Y','2Y Treasury yield':'US2Y'}
        for row in d['rows']:
            sym=mapping.get(row['factor'])
            if not sym or sym not in q: continue
            x=q[sym]; last=num(x.get('last')); prev=num(x.get('previous_day_closing') or x.get('previous_day_closing_price') or x.get('prev_close'))
            if last is None: continue
            bp=(last-prev)*100 if prev is not None else None
            row['latest']=f'{last:.3f}%'+(f' ({bp:+.1f} bp vs prev close)' if bp is not None else '')
            row['direction']='Rising' if bp is not None and bp>0.5 else ('Falling' if bp is not None and bp<-0.5 else 'Stable')
            row['signal']='negative' if (bp is not None and bp>0.5) else ('positive' if (bp is not None and bp<-0.5) else 'mixed')
            row['freshness']=now.strftime('%b %d, %Y · %H:%M ET')
            row['source']='CNBC intraday quote feed'
        d['updatedET']=now.strftime('%b %d, %Y · %H:%M ET')
        d['refreshStatus']='CNBC Treasury refresh succeeded'
    except Exception as e:
        d['refreshStatus']='CNBC refresh failed; prior values retained: '+str(e)[:160]
    with open(DATA,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)

if __name__=='__main__': main()
