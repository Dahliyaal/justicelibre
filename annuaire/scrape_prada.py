import re,html,csv,urllib.request,concurrent.futures as cf
U="https://www.cada.fr/particulier/personnes-responsables-resultatss?p={}"
def get(p):
    for _ in range(3):
        try:
            req=urllib.request.Request(U.format(p),headers={'User-Agent':'Mozilla/5.0'})
            return urllib.request.urlopen(req,timeout=30).read().decode('utf-8','replace')
        except Exception: pass
    return ''
def clean(x):
    x=re.sub(r'<br\s*/?>','\n',x)          # d'abord les sauts de ligne
    x=re.sub(r'</?p[^>]*>','\n',x)
    x=re.sub(r'<[^>]+>','',x)              # ensuite le reste des balises
    lines=[' '.join(l.split()) for l in html.unescape(x).split('\n')]
    return ' | '.join(l for l in lines if l)
def parse(t):
    out=[]
    for blk in re.findall(r'<div class="views-row">(.*?)</article>',t,re.S):
        nom=re.search(r'<h2 class="title">\s*<span>(.*?)</span>',blk,re.S)
        prada=re.search(r'field-name-pr-nom-prada.*?field-item[^>]*>(.*?)</div>',blk,re.S)
        adr=re.search(r'field-name-field-adresse-complete.*?<div><p>(.*?)</p>',blk,re.S)
        mails=re.findall(r'mailto:([^"\']*)"',blk)
        mails=[m for m in mails if m]
        out.append({'organisme':clean(nom.group(1)) if nom else '','prada':clean(prada.group(1)) if prada else '','adresse':clean(adr.group(1)) if adr else '','courriel':';'.join(dict.fromkeys(mails))})
    return out
rows=[]
with cf.ThreadPoolExecutor(6) as ex:
    for r in ex.map(lambda p: parse(get(p)), range(1,251)):
        rows+=r
seen=set(); uniq=[]
for r in rows:
    k=(r['organisme'],r['adresse'])
    if k not in seen: seen.add(k); uniq.append(r)
with open('prada_full.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['organisme','prada','courriel','adresse'],delimiter=';');w.writeheader();w.writerows(uniq)
print("PRADA récupérées:",len(uniq))
print("avec courriel:",sum(1 for r in uniq if r['courriel']),"| SANS courriel:",sum(1 for r in uniq if not r['courriel']))
print("\n===== TOUT CE QUI TOUCHE À LA JUSTICE =====")
for r in uniq:
    blob=(r['organisme']+' '+r['adresse']).lower()
    if any(k in blob for k in ['justice','sceaux','cassation','tribunal',"conseil d'état",'conseil d etat','cour d appel',"cour d'appel"]):
        print(f"\n • {r['organisme']}\n   PRADA: {r['prada']}\n   MAIL : {r['courriel'] or '— AUCUN —'}\n   ADR  : {r['adresse'][:200]}")
