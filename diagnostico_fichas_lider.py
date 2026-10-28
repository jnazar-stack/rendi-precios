"""Validación única de siete categorías públicas de Líder.

Prueba producto y precio estructurados sin editar precios.json.
No reintenta denegaciones.
"""
import json
import time
import requests
import re
from actualizar import ld_lists, num, elegir, CAT

SITIOS={
 "leche":"leches-descremadas-1-l",
 "huevo":"huevos",
 "pechuga":"pechuga-de-pollo",
 "atun":"atun",
 "arroz":"arroz",
 "aceite":"aceite-vegetal",
 "papas":"papas"
}
UA="RendiBot/1.0 (+https://github.com/jnazar-stack/rendi-precios; lector de precios publicos)"
BLOCK=re.compile(r"robot or human|are you a robot|access denied|px-captcha",re.I)

def items_de_pagina(html,pid):
    resultado=[]
    for collection in ld_lists(html):
        for el in collection.get("itemListElement",[]):
            it=(el.get("item") or {}) if isinstance(el,dict) else {}
            if not isinstance(it,dict):
                continue
            o=it.get("offers") or {}
            if isinstance(o,list):
                o=o[0] if o else {}
            p=num(o.get("price")) if isinstance(o,dict) else None
            n=it.get("name") or el.get("name") or ""
            if pid in ("papas","nueces","manzana","tomate","cebolla","palta","zanahoria","platano") and n.lower().startswith("multi marca "):
                n=n[len("multi marca "):]
            if p and n:
                resultado.append(dict(n=n,p=p,img=it.get("image"),u=it.get("url"),size=n,
                  stock="OutOfStock" not in str(o.get("availability",""))))
    return resultado

def main():
    s=requests.Session()
    s.headers.update({"User-Agent":UA,"Accept-Language":"es-CL,es;q=0.9"})
    for i,(pid,slug) in enumerate(SITIOS.items()):
        if i:
            time.sleep(1.5)
        try:
            r=s.get("https://super.lider.cl/v/"+slug,timeout=20)
            if r.status_code in (401,403,429) or (r.status_code==200 and BLOCK.search(r.text[:15000]) and not ld_lists(r.text)):
                print(json.dumps({"producto":pid,"http":r.status_code,"estado":"bloqueado"}),flush=True)
                break
            if r.status_code!=200:
                print(json.dumps({"producto":pid,"http":r.status_code,"estado":"http_invalido"}),flush=True)
                continue
            items=items_de_pagina(r.text,pid)
            chosen=elegir(items,CAT[pid])
            print(json.dumps({"producto":pid,"http":r.status_code,"items":len(items),
             "coincide":bool(chosen),
             "eq":(chosen or {}).get("eq",{}).get("n"),
             "precio_eq":(chosen or {}).get("eq",{}).get("p")},ensure_ascii=False),flush=True)
        except requests.RequestException as e:
            print(json.dumps({"producto":pid,"error":type(e).__name__}),flush=True)
            break

if __name__=="__main__":
    main()
