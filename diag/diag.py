"""Diagnóstico 2: EAN en Jumbo (página de producto y búsqueda), Unimarc con Chromium, mapa de Lider."""
import json, re, sys
sys.path.insert(0, ".")
import actualizar as A
def show(*a): print(*a, flush=True)

st, t = A.get("https://www.jumbo.cl/leche-descremada-surlat-b-a-1l-1991552/p")
show("== jumbo producto http", st, len(t))
raw = t.replace('\\"','"')
for k in ("ean", "gtin13", "gtin", "referenceId", "EAN"):
    m = re.findall(r'"%s"\s*:\s*"?([0-9]{8,14})' % k, raw); show(k, len(m), m[:3])
i = raw.find("7800"); show("contexto 7800:", raw[max(0,i-200):i+100] if i>0 else "-")
for base in ("https://www.jumbo.cl", "https://www.santaisabel.cl"):
    for e in ("7802920009865", "7802920000008"):
        st, t = A.get(f"{base}/busqueda?ft={e}")
        names = [((x.get("item") or {}).get("name")) for l in A.ld_lists(t) for x in (l.get("itemListElement") or [])]
        show("busqueda EAN", base, e, st, len(names), names[:3])

st, t = A.get("https://www.alvi.cl/search?q=leche%20descremada%20colun")
d = A.next_data(t); f = []
if d: A.walk(d, lambda o: "sellers" in o and "detailUrl" in o and "ean" in o, f)
show("== alvi colun:", [(x.get("nameComplete","")[:50], x.get("ean")) for x in f[:8]])

st, t = A.get("https://super.lider.cl/v/nc/sitemap/keyword-0.xml"); locs = re.findall(r"<loc>([^<]+)</loc>", t)
show("== lider keyword-0", st, len(locs), locs[:15])
for n in (1, 2):
    st, t = A.get(f"https://super.lider.cl/v/nc/sitemap/keyword-{n}.xml"); show("keyword", n, st, len(re.findall(r"<loc>", t)))
st, t = A.get("https://super.lider.cl/productSitemap.xml"); locs = re.findall(r"<loc>([^<]+)</loc>", t)
show("== lider productSitemap", st, len(locs), locs[:6])
st, t = A.get("https://super.lider.cl/ip/leche/leche-descremada-natural-caja-1-l/00780292000008")
show("== lider producto http", st, len(t), "bloqueo" if A.BLOQUEO.search(t[:20000]) else "")
raw = t.replace('\\"','"')
for k in ("gtin13","upc","gtin","ean"):
    m = re.findall(r'"%s"\s*:\s*"?([0-9]{8,14})' % k, raw); show(k, m[:3])

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(locale="es-CL")
    r = pg.goto("https://www.unimarc.cl/search?q=leche%20descremada", wait_until="domcontentloaded", timeout=25000)
    pg.wait_for_timeout(5000)
    show("== unimarc chromium", r.status if r else None)
    nd = pg.evaluate("() => { const s = document.getElementById('__NEXT_DATA__'); return s ? s.textContent.length : 0 }")
    show("next_data bytes", nd)
    eans = pg.evaluate("() => { const t = (document.getElementById('__NEXT_DATA__')||{}).textContent || ''; return (t.match(/\"ean\":\"(\\d{8,14})\"/g)||[]).slice(0,8) }")
    show("unimarc eans", eans)
    links = pg.evaluate("() => [...document.querySelectorAll('a[href*=\"/product/\"]')].slice(0,5).map(a=>a.getAttribute('href'))")
    show("unimarc links", links)
    r2 = pg.goto("https://www.unimarc.cl/search?q=7802920009865", wait_until="domcontentloaded", timeout=25000); pg.wait_for_timeout(5000)
    show("unimarc busqueda EAN", r2.status if r2 else None, pg.evaluate("() => [...document.querySelectorAll('[class*=\"Shelf_nameProduct\"]')].slice(0,3).map(x=>x.innerText)"))
    b.close()
