import json, urllib.request, urllib.parse, datetime, os
from zoneinfo import ZoneInfo

ROOT=os.path.dirname(os.path.dirname(__file__))
PATH=os.path.join(ROOT,'data','dashboard.json')
NY=ZoneInfo('America/New_York')
CNBC_BASE='https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol'
SYMBOLS=['US10Y','US2Y','QQQ','NVDA','AMD','AVGO','TSM','.VIX','.VXN','.DXY','@CL.1','@LCO.1']

def cnbc_quotes(symbols):
    params={'symbols':'|'.join(symbols),'requestMethod':'itv','noform':'1','partnerId':'2','fund':'1','exthrs':'1','output':'json','events':'1'}
    url=CNBC_BASE+'?'+urllib.parse.urlencode(params,safe='|@.')
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Referer':'https://www.cnbc.com/'})
    with urllib.request.urlopen(req,timeout=20) as r: raw=r.read().decode('utf-8',errors='replace')
    data=json.loads(raw); qs=data.get('FormattedQuoteResult',{}).get('FormattedQuote',[])
    if isinstance(qs,dict): qs=[qs]
    return {q.get('symbol'):q for q in qs if q.get('symbol') and q.get('code')==0}

def num(v):
    if v is None:return None
    try:return float(str(v).replace(',','').replace('%','').replace('$','').strip())
    except:return None

def pct(q):
    v=num(q.get('last')); p=num(q.get('previous_day_closing'))
    return ((v/p)-1)*100 if v is not None and p not in (None,0) else None

def fresh(q):
    t=q.get('last_time') or q.get('last_timedate') or 'timestamp unavailable'
    # CNBC sometimes returns only YYYY-MM-DD for equities outside their active quote session.
    return ('CNBC previous close · '+t) if len(str(t))==10 else ('CNBC intraday · '+str(t))

def setrow(rows,name,latest,direction,signal,freshness,source='CNBC quote feed'):
    r=next(x for x in rows if x['factor']==name); r.update(latest=latest,direction=direction,signal=signal,freshness=freshness,source=source)

def main():
    with open(PATH,encoding='utf-8') as f:d=json.load(f)
    now=datetime.datetime.now(NY); rows=d['rows']
    try:
        q=cnbc_quotes(SYMBOLS)
        # Treasury yields
        for sym,name in [('US10Y','10Y nominal yield'),('US2Y','2Y Treasury yield')]:
            x=q[sym]; v=num(x.get('last')); p=num(x.get('previous_day_closing')); bp=(v-p)*100 if v is not None and p is not None else None
            sig='negative' if v>=4.5 else ('mixed' if v>=4.0 else 'positive')
            setrow(rows,name,f'{v:.3f}%'+(f' ({bp:+.1f} bp vs prev close)' if bp is not None else ''),'Rising' if bp and bp>0 else ('Falling' if bp and bp<0 else 'Flat'),sig,fresh(x),'CNBC / Tradeweb quote feed')

        # Semiconductor leadership versus QQQ. This is explicitly a daily/previous-close relative-strength check when CNBC has not supplied an intraday equity timestamp.
        semis=[('NVDA','NVDA'),('AMD','AMD'),('AVGO','AVGO'),('TSM','TSM')]
        moves={label:pct(q[sym]) for sym,label in semis if sym in q}
        qqq=pct(q['QQQ']) if 'QQQ' in q else None
        valid=[v for v in moves.values() if v is not None]
        if valid and qqq is not None:
            avg=sum(valid)/len(valid); rel=avg-qqq
            sig='positive' if rel>0.25 else ('negative' if rel<-0.25 else 'mixed')
            direction='Leading QQQ' if rel>0.25 else ('Lagging QQQ' if rel<-0.25 else 'In line with QQQ')
            text=' | '.join(f'{k} {v:+.2f}%' for k,v in moves.items())+f' | QQQ {qqq:+.2f}% | basket vs QQQ {rel:+.2f} pp'
            setrow(rows,'Semiconductor leadership',text,direction,sig,fresh(q['QQQ']),'CNBC quotes; equal-weight NVDA/AMD/AVGO/TSM vs QQQ calculation')

        # Volatility: VXN is Nasdaq-specific; VIX is included as confirmation.
        vx=q.get('.VXN'); vi=q.get('.VIX')
        if vx and vi:
            vxn=num(vx.get('last')); vix=num(vi.get('last')); vxnp=pct(vx); vixp=pct(vi)
            sig='positive' if (vxnp is not None and vxnp<-2 and vixp is not None and vixp<-2) else ('negative' if (vxnp is not None and vxnp>2) else 'mixed')
            direction='Falling' if vxnp is not None and vxnp<0 else ('Rising' if vxnp is not None and vxnp>0 else 'Flat')
            setrow(rows,'Nasdaq volatility (VXN / VIX)',f'VXN {vxn:.2f} ({vxnp:+.2f}%) | VIX {vix:.2f} ({vixp:+.2f}%)',direction,sig,fresh(vx),'CNBC / Cboe quotes')

        # Dollar
        dx=q.get('.DXY')
        if dx:
            v=num(dx.get('last')); m=pct(dx); sig='positive' if m is not None and m<-0.15 else ('negative' if m is not None and m>0.15 else 'mixed')
            setrow(rows,'U.S. Dollar (DXY)',f'DXY {v:.3f} ({m:+.2f}% vs prev close)','Rising' if m and m>0 else ('Falling' if m and m<0 else 'Flat'),sig,fresh(dx),'CNBC / ICE quote feed')

        # Oil
        w=q.get('@CL.1'); b=q.get('@LCO.1')
        if w and b:
            wv=num(w.get('last')); bv=num(b.get('last')); wm=pct(w); bm=pct(b); avg=(wm+bm)/2
            sig='positive' if avg<-1 else ('negative' if avg>1 else 'mixed')
            setrow(rows,'Oil (WTI / Brent)',f'WTI ${wv:.2f} ({wm:+.2f}%) | Brent ${bv:.2f} ({bm:+.2f}%)','Falling' if avg<0 else ('Rising' if avg>0 else 'Flat'),sig,fresh(w),'CNBC futures quotes')

        # Mega-cap leadership: QQQ itself is now live/previous-close sourced, but we do not yet have the mega-cap basket wired. Avoid pretending otherwise.
        if 'QQQ' in q:
            qm=pct(q['QQQ']); r=next(x for x in rows if x['factor']=='Mega-cap leadership')
            r['freshness']=fresh(q['QQQ'])+' · mega-cap basket pending'; r['source']='CNBC QQQ quote; mega-cap basket not yet connected'
    except Exception as e:
        print('CNBC refresh failed:',repr(e))
        for name in ('10Y nominal yield','2Y Treasury yield','Semiconductor leadership','Nasdaq volatility (VXN / VIX)','U.S. Dollar (DXY)','Oil (WTI / Brent)'):
            next(x for x in rows if x['factor']==name)['freshness']='STALE — CNBC refresh failed'

    real=next(x for x in rows if x['factor']=='10Y real yield'); real['freshness']='STALE — live source not yet connected'; real['source']='Live real-yield source pending (FRED disabled)'
    d['updatedET']=now.strftime('%b %d, %Y · %H:%M ET'); d['nextUpdateET']='09:30 / 10:30 ET on trading weekdays'
    with open(PATH,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2)

if __name__=='__main__':main()
