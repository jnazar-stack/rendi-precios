"""Una consulta de diagnóstico a una categoría pública de Líder; sin reintentos."""
import json
import re
import requests
from actualizar import ld_lists, next_data, walk, num, elegir, CAT

URL = "https://super.lider.cl/v/leches-descremadas-1-l"
UA = "RendiBot/1.0 (+https://github.com/jnazar-stack/rendi-precios; lector de precios publicos)"

def main():
    r = requests.get(URL, headers={"User-Agent":UA,"Accept-Language":"es-CL,es;q=0.9"},timeout=20)
    if r.status_code != 200:
        print(json.dumps({"status":r.status_code,"resultado":"no_disponible"}))
        return
    html = r.text
    lists = ld_lists(html)
    sample = []
    for lst in lists:
        for el in lst.get("itemListElement",[])[:10]:
            product = el.get("item",{}) if isinstance(el,dict) else {}
            if not isinstance(product,dict):
                product = {}
            offer = product.get("offers") or {}
            if isinstance(offer,list):
                offer=offer[0] if offer else {}
            name=product.get("name") or el.get("name") or ""
            price=offer.get("price") if isinstance(offer,dict) else None
            sample.append({"nombre":str(name)[:75],"precio":price})
    nd=next_data(html)
    candidates=[]
    if nd:
        walk(nd,lambda o: "usItemId" in o and "priceInfo" in o and "name" in o,candidates)
    prices=[]
    for x in candidates:
        pi=x.get("priceInfo") or {}
        raw=pi.get("linePrice") or pi.get("itemPrice")
        price=num(raw)
        if price:
            prices.append(dict(n=str(x.get("name") or ""),p=price,size=str(x.get("name") or ""),stock=True,
                img=None,u=None))
    chosen=elegir(prices,CAT["leche"])
    print(json.dumps({
      "status":r.status_code,
      "bytes":len(r.content),
      "jsonld_listas":len(lists),
      "jsonld_elementos":sum(len(x.get("itemListElement",[])) for x in lists),
      "jsonld_muestra":sample[:4],
      "next_data":bool(nd),
      "next_productos_con_priceinfo":len(prices),
      "next_muestra":[{"n":x["n"][:75],"p":x["p"]} for x in prices[:4]],
      "leche_seleccionada":bool(chosen),
      "leche_eq":(chosen or {}).get("eq"),
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
