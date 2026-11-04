"""Diagnóstico de una vez: guarda la tabla nutricional de algunas páginas de Jumbo/Santa Isabel (diag_tablas.html)
y prueba Open Food Facts para Chile. Escribe diag_nutri.txt."""
import json, re, time
import requests
import actualizar as A
from actualizar import get

out, tablas = [], []
def w(*a): out.append(" ".join(str(x) for x in a))

for base, q in [("https://www.jumbo.cl", "avena"), ("https://www.jumbo.cl", "yogurt griego"), ("https://www.santaisabel.cl", "pechuga de pollo"), ("https://www.jumbo.cl", "platano"), ("https://www.jumbo.cl", "leche descremada")]:
    st, t = get(f"{base}/busqueda?ft={A.quote(q)}")
    slugs = list(dict.fromkeys(re.findall(r"\.cl/([^\"?#]*-\d+)/p\b", t or "")))[:2]
    for slug in slugs:
        st, t = get(f"{base}/{slug}/p"); time.sleep(1.5)
        i = (t or "").find("Información nutricional</span>")
        j = t.find("<table", i) if i >= 0 else -1
        k = t.find("</table>", j) if j >= 0 else -1
        w(base, slug, st, "tabla" if k > 0 else "sin tabla")
        if k > 0:
            tablas.append(f"<!-- {base}/{slug}/p -->\n" + t[j:k+8])
            m = re.search(r"Porci[oó]n[^<]{0,80}", t[i:j]); w("   ", m.group(0) if m else "")
for url, params in [("https://world.openfoodfacts.org/api/v2/search", {"countries_tags_en": "chile", "fields": "code,product_name,nutriments", "page_size": 3}),
                    ("https://world.openfoodfacts.org/cgi/search.pl", {"action": "process", "tagtype_0": "countries", "tag_contains_0": "contains", "tag_0": "chile", "json": 1, "page_size": 3, "fields": "code,product_name"})]:
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "rendi-precios/1.0 (github.com/jnazar-stack/rendi-precios)"}, timeout=60)
        w("OFF", url, r.status_code, r.text[:300].replace("\n", " "))
    except Exception as e:
        w("OFF error", url, e)
    time.sleep(7)
open("diag_tablas.html", "w").write("\n".join(tablas))
open("diag_nutri.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
