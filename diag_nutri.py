"""Diagnóstico de una vez: ¿qué páginas públicas traen la tabla nutricional? Escribe diag_nutri.txt."""
import json, re, time
import requests
import actualizar as A
from actualizar import get, next_data

out = []
def w(*a):
    out.append(" ".join(str(x) for x in a))

KW = re.compile(r"(calor[ií]as|energ[ií]a|kcal|prote[ií]nas?|informaci[oó]n nutricional|grasas totales|hidratos|carbohidratos|sodio)", re.I)
def snippets(t, n=6):
    res = []
    for m in KW.finditer(t):
        s = t[max(0, m.start()-120): m.end()+160].replace("\n", " ")
        if not any(s[:60] in r for r in res):
            res.append(s)
        if len(res) >= n:
            break
    return res

# 1) Jumbo / Santa Isabel: página de producto y API de catálogo VTEX
for base in ["https://www.jumbo.cl", "https://www.santaisabel.cl"]:
    st, t = get(f"{base}/busqueda?ft=avena")
    m = re.findall(r"\.cl/([^\"?#]*-\d+)/p\b", t or "")
    w("==", base, "busqueda", st, "productos", len(set(m)))
    for slug in list(dict.fromkeys(m))[:2]:
        st, t = get(f"{base}/{slug}/p"); time.sleep(1.5)
        raw = (t or "").replace('\\"', '"')
        w("-- pagina", slug, st, len(raw))
        for s in snippets(raw): w("   ", s[:300])
        pid = re.search(r"-(\d+)$", slug).group(1)
        for api in [f"{base}/api/catalog_system/pub/products/search?fq=productId:{pid}"]:
            try:
                r = requests.get(api, headers={"User-Agent": A.UA if hasattr(A, "UA") else "rendi-precios"}, timeout=20)
                w("-- api", r.status_code, len(r.text))
                if r.ok:
                    d = r.json()
                    if d:
                        p = d[0]
                        w("   claves", sorted(p.keys())[:60])
                        for k in p.get("allSpecifications", []) or []:
                            w("   spec", k, "=", str(p.get(k))[:200])
                        for g in p.get("specificationGroups", []) or []:
                            w("   grupo", g.get("name"), [(s.get("name"), str(s.get("values"))[:80]) for s in g.get("specifications", [])][:12])
                        for s in snippets(json.dumps(p, ensure_ascii=False)): w("   ", s[:300])
            except Exception as e:
                w("-- api error", e)
            time.sleep(1.5)

# 2) Alvi: página de producto
st, t = get("https://www.alvi.cl/search?q=avena")
d = next_data(t) or {}
urls = re.findall(r'"detailUrl"\s*:\s*"([^"]+)"', json.dumps(d))
w("== alvi busqueda", st, "urls", len(urls), urls[:2])
for u in urls[:2]:
    st, t = get("https://www.alvi.cl" + u if u.startswith("/") else u); time.sleep(1.5)
    w("-- alvi pagina", u, st, len(t or ""))
    nd = next_data(t or "")
    txt = json.dumps(nd, ensure_ascii=False) if nd else (t or "")
    for s in snippets(txt): w("   ", s[:300])

# 3) Lider: página de producto desde una página /v/
st, t = get("https://super.lider.cl/v/avena")
m = re.findall(r'https://super\.lider\.cl/ip/[^"\s<]+', t or "")
w("== lider v", st, "ip", len(m), m[:2])
for u in m[:1]:
    st, t = get(u); time.sleep(1.5)
    w("-- lider ip", st, len(t or ""))
    for s in snippets(t or ""): w("   ", s[:300])

# 4) Open Food Facts: productos de Chile con tabla nutricional
try:
    r = requests.get("https://world.openfoodfacts.org/api/v2/search", params={"countries_tags_en": "chile", "fields": "code,product_name,brands,nutriments", "page_size": 5, "states_tags": "en:nutrition-facts-completed"},
                     headers={"User-Agent": "rendi-precios/1.0 (github.com/jnazar-stack/rendi-precios)"}, timeout=40)
    j = r.json()
    w("== OFF chile con nutricion:", j.get("count"), [(p.get("code"), p.get("product_name"), (p.get("nutriments") or {}).get("energy-kcal_100g")) for p in j.get("products", [])])
    r = requests.get("https://world.openfoodfacts.org/api/v2/search", params={"countries_tags_en": "chile", "fields": "code", "page_size": 1}, headers={"User-Agent": "rendi-precios/1.0"}, timeout=40)
    w("== OFF chile total:", r.json().get("count"))
except Exception as e:
    w("OFF error", e)

open("diag_nutri.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
