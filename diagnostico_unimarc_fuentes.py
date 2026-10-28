"""Diagnóstico acotado de fuentes públicas de Unimarc.

Una solicitud por URL, identificada, sin cookies de clientes ni reintentos.
No modifica el catálogo de Rendi ni publica precios.
"""
import json
import re
import time
from urllib.parse import quote
import requests

import actualizar as a

UA = "RendiBot/1.0 (+https://github.com/jnazar-stack/rendi-precios; lectura de precios publicos)"

RUTAS = [
    ("ficha_huevos", "https://www.unimarc.cl/product/huevos-medianos-omega3-30-un"),
    ("ficha_leche", "https://www.unimarc.cl/product/leche-semidescremada-sin-lactosa-surlat-plus-1-l"),
    ("busqueda", "https://www.unimarc.cl/search?q=" + quote("leche descremada 1 litro")),
    ("vtex_catalogo_publico", "https://www.unimarc.cl/api/catalog_system/pub/products/search/leche?_from=0&_to=4"),
    ("vtex_busqueda_publica", "https://www.unimarc.cl/api/io/_v/api/intelligent-search/product_search/?query=leche"),
]
BLOCK = re.compile(r"robot or human|are you a robot|access denied|px-captcha|perimeterx", re.I)

def extract_product_descriptors(doc):
    products = []
    for item_list in a.ld_lists(doc):
        for el in item_list.get("itemListElement", [])[:8]:
            item = (el or {}).get("item") or {}
            if not isinstance(item, dict):
                continue
            offer = item.get("offers") or {}
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            products.append({"nombre": str(item.get("name") or "")[:80],
                             "precio": (offer or {}).get("price")})
    return products

def main():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"})
    for index, (label, url) in enumerate(RUTAS):
        if index:
            time.sleep(1.5)
        try:
            r = s.get(url, timeout=18)
            ct = r.headers.get("content-type", "")[:70]
            out = {"prueba":label, "http":r.status_code, "content_type":ct,
                   "bytes":len(r.content)}
            if r.status_code in (401, 403, 429):
                out["estado"] = "acceso_denegado"
            elif r.status_code == 200 and BLOCK.search(r.text[:20000]):
                out["estado"] = "posible_verificacion"
            elif r.status_code == 200:
                out["estado"] = "accesible"
                if "json" in ct:
                    try:
                        d=r.json()
                        out["raiz"] = list(d.keys())[:10] if isinstance(d, dict) else type(d).__name__
                        out["elementos"] = len(d) if isinstance(d, list) else None
                    except ValueError:
                        out["estado"] = "json_invalido"
                else:
                    nd=a.next_data(r.text)
                    out["next_data"] = bool(nd)
                    out["next_page"] = str((nd or {}).get("page", ""))[:70]
                    out["next_props"] = list(((nd or {}).get("props") or {}).get("pageProps", {}).keys())[:15]
                    out["listas_jsonld"] = len(a.ld_lists(r.text))
                    out["productos_jsonld"] = extract_product_descriptors(r.text)[:4]
                    out["marca_precio"] = bool(re.search(r"\$\s*[0-9][0-9.,]{2,8}",r.text))
            else:
                out["estado"] = "http_no_200"
            print(json.dumps(out,ensure_ascii=False),flush=True)
        except requests.RequestException as e:
            print(json.dumps({"prueba":label,"estado":"error_red","tipo":type(e).__name__}),flush=True)

if __name__ == "__main__":
    main()
