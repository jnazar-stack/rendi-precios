"""Diagnóstico de una sola vez: qué campos publica cada cadena en sus páginas públicas (¿EAN?),
si la búsqueda acepta un EAN y qué páginas de categoría de Lider existen. No modifica nada."""
import json, re, sys, time
sys.path.insert(0, ".")
import actualizar as A

def show(t, *a): print(t, *a, flush=True)

# Jumbo y Santa Isabel (VTEX): JSON-LD y estado embebido
for base in ("https://www.jumbo.cl", "https://www.santaisabel.cl"):
    st, t = A.get(f"{base}/busqueda?ft=leche%20descremada")
    show("\n=====", base, "http", st, "bytes", len(t))
    L = A.ld_lists(t)
    if L:
        el = (L[0].get("itemListElement") or [{}])[0]
        it = el.get("item") or {}
        show("ld item keys:", sorted(it.keys()))
        show("ld offers:", json.dumps(it.get("offers"), ensure_ascii=False)[:400])
        show("ld sample:", json.dumps({k: it.get(k) for k in ("name","sku","gtin","gtin13","gtin8","mpn","productID","brand")}, ensure_ascii=False)[:400])
        show("ld items en página:", sum(len(x.get("itemListElement") or []) for x in L))
    raw = t.replace('\\"', '"')
    eans = re.findall(r'"ean"\s*:\s*"(\d{8,14})"', raw)
    show("ean en estado:", len(eans), eans[:5])
    for k in ("gtin13", "referenceId", "productReference", "itemId", "skuId"):
        m = re.findall(r'"%s"\s*:\s*"?([^",}]{1,40})' % k, raw)
        show(k, len(m), m[:3])
    i = raw.find('"ean"')
    if i > 0: show("contexto ean:", raw[max(0, i-400):i+200])
    if eans:
        e = eans[0]
        st2, t2 = A.get(f"{base}/busqueda?ft={e}")
        L2 = A.ld_lists(t2)
        names = [((x.get("item") or {}).get("name")) for l in L2 for x in (l.get("itemListElement") or [])]
        show("búsqueda por EAN", e, "http", st2, "resultados", len(names), names[:3])
        st3, t3 = A.get(f"{base}/{e}?_q={e}&map=ft")
        show("ruta alternativa EAN http", st3, len(t3))

# Alvi (SMU, __NEXT_DATA__)
st, t = A.get("https://www.alvi.cl/search?q=leche%20descremada")
show("\n===== alvi http", st)
d = A.next_data(t); found = []
if d: A.walk(d, lambda o: "sellers" in o and ("nameComplete" in o or "name" in o) and "detailUrl" in o, found)
show("alvi productos:", len(found))
if found:
    x = found[0]; show("alvi keys:", sorted(x.keys())); show("alvi muestra:", json.dumps({k: x.get(k) for k in x if k in ("ean","sku","itemId","refId","productId","brand","nameComplete","netContent","detailUrl")}, ensure_ascii=False)[:500])
    e = x.get("ean") or ""
    if e:
        st2, t2 = A.get(f"https://www.alvi.cl/search?q={e}"); d2 = A.next_data(t2); f2 = []
        if d2: A.walk(d2, lambda o: "sellers" in o and "detailUrl" in o, f2)
        show("alvi búsqueda por EAN", e, st2, len(f2), [y.get("nameComplete") for y in f2[:3]])

# Unimarc (SMU): ¿la página de búsqueda trae __NEXT_DATA__ con EAN?
st, t = A.get("https://www.unimarc.cl/search?q=leche%20descremada")
show("\n===== unimarc http", st, "bytes", len(t))
d = A.next_data(t); found = []
if d: A.walk(d, lambda o: "sellers" in o and ("nameComplete" in o or "name" in o) and "detailUrl" in o, found)
show("unimarc next_data productos:", len(found), "eans:", [x.get("ean") for x in found[:5]])
show("unimarc ean en html:", re.findall(r'"ean"\s*:\s*"(\d{8,14})"', t)[:5])

# Lider: robots, sitemap y una categoría
for u in ("https://super.lider.cl/robots.txt",):
    st, t = A.get(u); show("\n===== lider robots", st); show(t[:1500])
    for sm in re.findall(r"(?im)^sitemap:\s*(\S+)", t)[:6]:
        st2, t2 = A.get(sm); locs = re.findall(r"<loc>([^<]+)</loc>", t2)
        show("sitemap", sm, st2, len(locs), locs[:8])
st, t = A.get("https://super.lider.cl/v/leche-descremada-colun")
L = A.ld_lists(t); show("lider categoría http", st, "listas", len(L))
if L:
    it = (L[0].get("itemListElement") or [{}])[0].get("item") or {}
    show("lider ld keys:", sorted(it.keys())); show(json.dumps({k: it.get(k) for k in ("name","sku","gtin13","gtin","mpn","url")}, ensure_ascii=False)[:400])
