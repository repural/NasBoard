import json, urllib.request, csv, io, datetime, os
from zoneinfo import ZoneInfo

ROOT=os.path.dirname(os.path.dirname(__file__))
PATH=os.path.join(ROOT,'data','dashboard.json')
NY=ZoneInfo('America/New_York')

def fred_csv(series):
    url=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'
    with urllib.request.urlopen(url,timeout=20) as r:
        rows=list(csv.DictReader(io.StringIO(r.read().decode())))
    for row in reversed(rows):
        v=row[series]
        if v not in ('','.','NA'):
            return float(v),row['DATE']
    raise RuntimeError('No FRED observation for '+series)

def setrow(rows,name,latest,direction,signal,freshness,source=None,explanation=None):
    r=next(x for x in rows if x['factor']==name)
    r.update(latest=latest,direction=direction,signal=signal,freshness=freshness)
    if source: r['source']=source
    if explanation: r['explanation']=explanation

def main():
    with open(PATH,encoding='utf-8') as f:d=json.load(f)
    now=datetime.datetime.now(NY)
    # Official/free daily Treasury/FRED observations. These are intentionally labelled daily, not real-time.
    series=[('DGS10','10Y nominal yield'),('DGS2','2Y Treasury yield'),('DFII10','10Y real yield')]
    for sid,name in series:
        try:
            value,date=fred_csv(sid)
            if name=='10Y real yield': sig='negative' if value>=2.0 else ('mixed' if value>=1.5 else 'positive')
            elif name=='10Y nominal yield': sig='negative' if value>=4.5 else ('mixed' if value>=4.0 else 'positive')
            else: sig='negative' if value>=4.5 else ('mixed' if value>=4.0 else 'positive')
            setrow(d['rows'],name,f'{value:.2f}%', 'Elevated' if sig=='negative' else 'Moderate',sig,f'FRED observation {date}')
        except Exception as e:
            r=next(x for x in d['rows'] if x['factor']==name);r['freshness']='STALE — refresh failed'
    # The remaining rows retain their last verified values until their dedicated adapters are available.
    # This is deliberate: never replace unavailable research with invented values.
    d['updatedET']=now.strftime('%b %d, %Y · %H:%M ET')
    d['nextUpdateET']='09:30 / 10:30 ET on trading weekdays'
    with open(PATH,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2)

if __name__=='__main__':main()
