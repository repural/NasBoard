import json, urllib.request, urllib.parse, datetime, os, re, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=os.path.dirname(os.path.dirname(__file__))
PATH=os.path.join(ROOT,'data','dashboard.json')
NY=ZoneInfo('America/New_York')
CNBC_BASE='https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol'
MEGACAPS=['AAPL','MSFT','AMZN','GOOGL','META','NVDA','TSLA']
BREADTH=['NVDA','AAPL','MU','MSFT','AMD','AMZN','TSLA','GOOGL','INTC','GOOG','AVGO','META','AMAT','WMT','LRCX','CSCO','COST','KLAC','SNDK','NFLX','PANW','TXN','PLTR','MRVL','LIN','WDC','STX','AMGN','QCOM','CRWD','ADI','PEP','ASML','TMUS','APP','GILD','ARM','ISRG','SHOP','BKNG','VRTX','SBUX','FTNT','CDNS','MAR','MNST','CEG','ADP','CSX','CMCSA','DDOG','MELI','SNPS','ADBE','ALAB','ORLY','DASH','TER','AEP','MDLZ','INTU','NXPI','HON','HONA','ROST','CTAS','MPWR','WBD','LITE','REGN','RBLX','NBIS','ABNB','RKLB','FAST','BKR','PDD','XEL','FANG','MCHP','FER','EXC','TTWO','AXON','ODFL','CCEP','CRWV','KDP','IDXX','ADSK','ALNY','PYPL','PAYX','ROP','TRI','GEHC','MSTR','KHC','CPRT','DXCM','WDAY','SPCX']
SYMBOLS=list(dict.fromkeys(['US10Y','US2Y','QQQ','NVDA','AMD','AVGO','TSM','.VIX','.VXN','.DXY','@CL.1','@LCO.1','HYG','LQD','S5FI']+MEGACAPS+BREADTH))

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

def is_intraday(q,now):
    t=str(q.get('last_time') or q.get('last_timedate') or '')
    return len(t)>10 and t[:10]==now.strftime('%Y-%m-%d')

def setrow(rows,name,latest,direction,signal,freshness,source='CNBC quote feed'):
    r=next(x for x in rows if x['factor']==name); r.update(latest=latest,direction=direction,signal=signal,freshness=freshness,source=source)

def treasury_10y_real(year):
    url='https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value='+str(year)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req,timeout=20) as r: raw=r.read()
    root=ET.fromstring(raw); points=[]
    for props in root.iter():
        if not str(props.tag).endswith('properties'): continue
        vals={str(x.tag).split('}')[-1]: (x.text or '').strip() for x in list(props)}
        date=vals.get('NEW_DATE') or vals.get('new_date')
        y10=vals.get('TC_10YEAR') or vals.get('tc_10year')
        if date and y10:
            try: points.append((datetime.datetime.fromisoformat(date.replace('Z','+00:00')).date(),float(y10)))
            except: pass
    if not points: raise ValueError('Treasury TC_10YEAR real yield not found in XML feed')
    points.sort(); return points[-1]

def cboe_put_call(day=None):
    url='https://www.cboe.com/markets/us/options/market-statistics/daily'
    if day is not None: url += '?dt='+day.isoformat()
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html,*/*'})
    with urllib.request.urlopen(req,timeout=20) as r: html=r.read().decode('utf-8',errors='replace')
    labels={'total':r'TOTAL PUT/CALL RATIO','index':r'INDEX PUT/CALL RATIO','equity':r'EQUITY PUT/CALL RATIO'}
    out={}
    for k,label in labels.items():
        m=re.search(label+r'.{0,500}?([0-9]+\.[0-9]+)',html,re.I|re.S)
        if not m: raise ValueError('Cboe '+k+' put/call ratio not found')
        out[k]=float(m.group(1))
    return out

def cboe_put_call_5d(now):
    vals=[]; day=now.date(); attempts=0
    while len(vals)<5 and attempts<12:
        attempts+=1
        if day.weekday()<5:
            try:
                x=cboe_put_call(day)
                vals.append((day,x))
            except Exception:
                pass
        day-=datetime.timedelta(days=1)
    if len(vals)<5: raise ValueError('Fewer than 5 Cboe trading sessions available')
    return vals

def main():
    with open(PATH,encoding='utf-8') as f:d=json.load(f)
    now=datetime.datetime.now(NY); rows=d['rows']
    try:
        q=cnbc_quotes(SYMBOLS)
        # S5FI probe: S&P 500 stocks above 50-day moving average breadth index.
        # Keep this as a source test until CNBC symbol availability is verified in a real Action run.
        if 'S5FI' in q:
            sx=q['S5FI']
            print('S5FI CNBC probe:', json.dumps({k:sx.get(k) for k in ['symbol','name','last','previous_day_closing','last_time','last_timedate','code']}))
        else:
            print('S5FI CNBC probe: symbol not returned')

        # Treasury yields
        for sym,name in [('US10Y','10Y nominal yield'),('US2Y','2Y Treasury yield')]:
            x=q[sym]; v=num(x.get('last')); p=num(x.get('previous_day_closing')); bp=(v-p)*100 if v is not None and p is not None else None
            sig='negative' if v>=4.5 else ('mixed' if v>=4.0 else 'positive')
            setrow(rows,name,f'{v:.3f}%'+(f' ({bp:+.1f} bp vs prev close)' if bp is not None else ''),'Rising' if bp and bp>0 else ('Falling' if bp and bp<0 else 'Flat'),sig,fresh(x),'CNBC / Tradeweb quote feed')

        # Leadership calculations only run when CNBC supplies current-session equity timestamps.
        semis=['NVDA','AMD','AVGO','TSM']
        equity_live='QQQ' in q and is_intraday(q['QQQ'],now)
        if equity_live and all(sym in q and is_intraday(q[sym],now) for sym in semis):
            moves={sym:pct(q[sym]) for sym in semis}; qqq=pct(q['QQQ'])
            valid=[v for v in moves.values() if v is not None]
            if valid and qqq is not None:
                avg=sum(valid)/len(valid); rel=avg-qqq
                sig='positive' if rel>0.25 else ('negative' if rel<-0.25 else 'mixed')
                direction='Leading QQQ' if rel>0.25 else ('Lagging QQQ' if rel<-0.25 else 'In line with QQQ')
                text=' | '.join(f'{k} {v:+.2f}%' for k,v in moves.items())+f' | QQQ {qqq:+.2f}% | basket vs QQQ {rel:+.2f} pp'
                setrow(rows,'Semiconductor leadership',text,direction,sig,fresh(q['QQQ']),'CNBC quotes; equal-weight NVDA/AMD/AVGO/TSM vs QQQ calculation')
        else:
            stamp=(q.get('QQQ',{}).get('last_time') or q.get('QQQ',{}).get('last_timedate') or 'unavailable')
            setrow(rows,'Semiconductor leadership',f'Awaiting current-session equity quotes — latest equity stamp {stamp}','Awaiting session','mixed',fresh(q['QQQ']) if 'QQQ' in q else 'STALE — QQQ unavailable','CNBC quotes; calculation suppressed when only previous-close data are available')

        # Mega-cap leadership: equal-weight basket versus QQQ, current session only.
        if equity_live:
            mm={sym:pct(q[sym]) for sym in MEGACAPS if sym in q and is_intraday(q[sym],now)}
            vals=[v for v in mm.values() if v is not None]; qqq=pct(q['QQQ'])
            if len(vals)>=5 and qqq is not None:
                avg=sum(vals)/len(vals); rel=avg-qqq; pos=sum(v>0 for v in vals)
                sig='positive' if rel>0.20 and pos>=4 else ('negative' if rel<-0.20 and pos<=3 else 'mixed')
                direction='Leading QQQ' if rel>0.20 else ('Lagging QQQ' if rel<-0.20 else 'In line with QQQ')
                setrow(rows,'Mega-cap leadership',f'{len(vals)}-stock basket {avg:+.2f}% | {pos}/{len(vals)} positive | QQQ {qqq:+.2f}% | relative {rel:+.2f} pp',direction,sig,fresh(q['QQQ']),'CNBC quotes; equal-weight AAPL/MSFT/AMZN/GOOGL/META/NVDA/TSLA basket vs QQQ')
        else:
            setrow(rows,'Mega-cap leadership','Awaiting current-session mega-cap quotes','Awaiting session','mixed',fresh(q['QQQ']) if 'QQQ' in q else 'STALE — QQQ unavailable','CNBC quotes; calculation suppressed outside current equity session')

        # Nasdaq-100 day breadth using the current constituent set. Multiple share classes mean the quote count can exceed 100.
        if equity_live:
            bm={sym:pct(q[sym]) for sym in BREADTH if sym in q and is_intraday(q[sym],now)}
            vals=[v for v in bm.values() if v is not None]
            if len(vals)>=80:
                adv=sum(v>0 for v in vals); dec=sum(v<0 for v in vals); flat=len(vals)-adv-dec; ratio=adv/len(vals)*100
                sig='positive' if ratio>=65 else ('negative' if ratio<=35 else 'mixed')
                direction='Broadening' if ratio>=65 else ('Weakening' if ratio<=35 else 'Mixed')
                setrow(rows,'Market breadth',f'Nasdaq-100 breadth: {adv}/{len(vals)} advancing ({ratio:.0f}%) · {dec} declining · {flat} flat',direction,sig,fresh(q['QQQ']),'CNBC quotes; Nasdaq-100 constituent day breadth')
        else:
            setrow(rows,'Market breadth','Awaiting current-session quotes for Nasdaq-100 breadth','Awaiting session','mixed',fresh(q['QQQ']) if 'QQQ' in q else 'STALE — QQQ unavailable','CNBC quotes; Nasdaq-100 constituent breadth; calculation suppressed outside current equity session')

        # Volatility: VXN is Nasdaq-specific; VIX is included as confirmation.
        vx=q.get('.VXN'); vi=q.get('.VIX')
        if vx and vi:
            vxn=num(vx.get('last')); vix=num(vi.get('last')); vxnp=pct(vx); vixp=pct(vi)
            sig='positive' if (vxnp is not None and vxnp<-2 and vixp is not None and vixp<-2) else ('negative' if (vxnp is not None and vxnp>2) else 'mixed')
            direction='Falling' if vxnp is not None and vxnp<0 else ('Rising' if vxnp is not None and vxnp>0 else 'Flat')
            setrow(rows,'Nasdaq volatility (VXN / VIX)',f'VXN {vxn:.2f} ({vxnp:+.2f}%) | VIX {vix:.2f} ({vixp:+.2f}%)',direction,sig,fresh(vx),'CNBC / Cboe quotes')

        # Credit conditions: HYG risk credit versus investment-grade LQD confirmation.
        hy=q.get('HYG'); lq=q.get('LQD')
        if hy and lq:
            hm=pct(hy); lm=pct(lq)
            if hm is not None and lm is not None:
                rel=hm-lm
                sig='positive' if rel>=0.25 else ('negative' if rel<=-0.25 else 'mixed')
                direction='Easing / risk-on' if rel>=0.25 else ('Tightening / risk-off' if rel<=-0.25 else 'Stable')
                setrow(rows,'Credit conditions',f'HYG {hm:+.2f}% | LQD {lm:+.2f}% | HYG vs LQD {rel:+.2f} pp',direction,sig,fresh(hy),'CNBC quotes; HYG high-yield ETF vs LQD investment-grade ETF proxy')

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

    except Exception as e:
        print('CNBC refresh failed:',repr(e))
        for name in ('10Y nominal yield','2Y Treasury yield','Semiconductor leadership','Nasdaq volatility (VXN / VIX)','U.S. Dollar (DXY)','Oil (WTI / Brent)'):
            next(x for x in rows if x['factor']==name)['freshness']='STALE — CNBC refresh failed'

    # Official Cboe options-volume put/call ratios. This is sentiment/positioning, not dealer gamma exposure.
    try:
        hist=cboe_put_call_5d(now)
        day,pc=hist[0]; eq,ix,tot=pc['equity'],pc['index'],pc['total']
        avg=sum(x['equity'] for _,x in hist)/len(hist)
        delta=eq-avg
        trend='↑ defensive' if delta>=0.08 else ('↓ call-heavy' if delta<=-0.08 else '→ stable')
        # Level is primary; deviation from the 5-session average adjusts borderline readings.
        score=0
        if eq>=0.90: score-=2
        elif eq>=0.75: score-=1
        elif eq<=0.50: score+=2
        elif eq<=0.60: score+=1
        if delta>=0.08: score-=1
        elif delta<=-0.08: score+=1
        sig='positive' if score>=2 else ('negative' if score<=-2 else 'mixed')
        direction='Defensive / put-heavy' if score<=-2 else ('Call-heavy' if score>=2 else 'Balanced')
        setrow(rows,'Options positioning / sentiment',
          f'Equity P/C {eq:.2f} | 5D avg {avg:.2f} | {trend} | Index {ix:.2f} | Total {tot:.2f}',
          direction,sig,
          f'Cboe daily · latest session {day.isoformat()} · checked {now.strftime("%Y-%m-%d %H:%M ET")}',
          'Cboe Daily Market Statistics — 5-session equity put/call trend; index/total context; not dealer gamma exposure')
    except Exception as e:
        print('Cboe put/call refresh failed:',repr(e))
        r=next(x for x in rows if x['factor']=='Options positioning / sentiment')
        r['freshness']='STALE — Cboe put/call refresh failed'
        r['source']='Cboe Daily Market Statistics — options volume put/call ratios'

    # Scheduled macro/Fed event risk from official 2026 calendars. This is event timing, not a market-implied probability model.
    events=[
      (datetime.datetime(2026,9,29,10,0,tzinfo=NY),'JOLTS (Aug)','BLS'),
      (datetime.datetime(2026,9,30,8,30,tzinfo=NY),'PCE / Personal Income & Outlays (Aug)','BEA'),
      (datetime.datetime(2026,10,2,8,30,tzinfo=NY),'Employment Situation (Sep)','BLS'),
      (datetime.datetime(2026,10,7,14,0,tzinfo=NY),'FOMC Minutes (Sep 15–16 meeting)','Federal Reserve'),
      (datetime.datetime(2026,10,14,8,30,tzinfo=NY),'CPI (Sep)','BLS'),
      (datetime.datetime(2026,10,15,8,30,tzinfo=NY),'PPI (Sep)','BLS'),
      (datetime.datetime(2026,10,27,0,0,tzinfo=NY),'FOMC meeting begins (Oct 27–28)','Federal Reserve'),
      (datetime.datetime(2026,10,28,14,0,tzinfo=NY),'FOMC decision / press conference','Federal Reserve'),
      (datetime.datetime(2026,10,29,8,30,tzinfo=NY),'GDP advance Q3 + PCE (Sep)','BEA'),
      (datetime.datetime(2026,10,30,8,30,tzinfo=NY),'Employment Cost Index Q3','BLS')
    ]
    future=[e for e in events if e[0]>now]
    if future:
        et,name,agency=min(future,key=lambda e:e[0]); hours=(et-now).total_seconds()/3600
        urgency='High event risk' if hours<=24 else ('Event approaching' if hours<=72 else 'Scheduled')
        esig='negative' if hours<=24 else 'mixed'
        setrow(rows,'Economic / inflation data',f'Next: {name} · {et.strftime("%b %d, %H:%M ET")}',urgency,esig,f'Official calendar · checked {now.strftime("%Y-%m-%d %H:%M ET")}',f'{agency} official release calendar')
    fomc=[e for e in events if e[2]=='Federal Reserve' and e[0]>now]
    if fomc:
        et,name,_=min(fomc,key=lambda e:e[0])
        setrow(rows,'Fed path / rate expectations',f'Next Fed catalyst: {name} · {et.strftime("%b %d, %H:%M ET")}','Event risk','mixed',f'Federal Reserve calendar · checked {now.strftime("%Y-%m-%d %H:%M ET")}','Federal Reserve FOMC calendar; market-implied rate probabilities not yet connected')

    # Official Treasury TIPS par real yield curve: daily, not intraday.
    real=next(x for x in rows if x['factor']=='10Y real yield')
    try:
        rd,rv=treasury_10y_real(now.year)
        real.update(latest=f'{rv:.2f}%',direction='Elevated' if rv>=2.0 else ('Moderate' if rv>=1.0 else 'Low'),signal='negative' if rv>=2.0 else ('mixed' if rv>=1.0 else 'positive'),freshness=f'U.S. Treasury daily · {rd.isoformat()}',source='U.S. Department of the Treasury — Daily Treasury Par Real Yield Curve Rates (10Y TIPS)')
    except Exception as e:
        print('Treasury real-yield refresh failed:',repr(e))
        real['freshness']='STALE — U.S. Treasury daily feed refresh failed'
        real['source']='U.S. Department of the Treasury — Daily Treasury Par Real Yield Curve Rates (10Y TIPS)'
    d['updatedET']=now.strftime('%b %d, %Y · %H:%M ET'); d['nextUpdateET']='09:30 / 10:30 ET on trading weekdays'
    with open(PATH,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2)

if __name__=='__main__':main()
