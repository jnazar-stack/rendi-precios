"""Diagnóstico acotado de páginas públicas de Tottus sin evadir denegaciones."""
import json
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
from actualizar import ld_lists, num

RUTAS = {
  "categoria_leche": "https://www.tottus.cl/tottus-cl/lista/CATG27526/Leches-Descremadas",
  "categoria_aceite": "https://www.tottus.cl/tottus-cl/lista/CATG27056/Aceites",
  "ficha_leche": "https://www.tottus.cl/tottus-cl/articulo/144788181",
  "busqueda": "https://www.tottus.cl/tottus-cl/buscar?Ntt=leche%20descremada",
}
UA="RendiBot/1.0 (+https://github.com/jnazar-stack/rendi-precios; lector de precios publicos)"

def extraer(html):
    productos=[]
    for lista in ld_lists(html):
        for el in lista.get("itemListElement",[]):
            if not isinstance(el,dict):
                continue
            it=el.get("item") or {}
            if not isinstance(it,dict):
                continue
            off=it.get("offers") or {}
            if isinstance(off,list):
                off=off[0] if off else {}
            if not isinstance(off,dict):
                off={}
            name=it.get("name") or el.get("name") or ""
            price=num(off.get("price"))
            if name:
                productos.append({"nombre":str(name)[:65],"precio":price})
    return productos

def diagnostico_requests():
    s=requests.Session()
    s.headers.update({"User-Agent":UA,"Accept-Language":"es-CL,es;q=0.9"})
    for nombre,url in RUTAS.items():
        try:
            r=s.get(url,timeout=18)
            p=extraer(r.text) if r.status_code==200 else []
            print(json.dumps({"modo":"requests","ruta":nombre,"http":r.status_code,
              "bytes":len(r.content),"jsonld_productos":len(p),"con_precio":sum(bool(x["precio"]) for x in p),
              "muestra":p[:2]},ensure_ascii=False),flush=True)
            if r.status_code in (401,403,429):
                # No seguir insistiendo sobre el mismo host si se deniega el acceso.
                break
        except requests.RequestException as ex:
            print(json.dumps({"modo":"requests","ruta":nombre,"error":type(ex).__name__}),flush=True)
            break

def diagnostico_chromium():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page(locale="es-CL")
            nombre="categoria_leche"
            try:
                response=page.goto(RUTAS[nombre],wait_until="domcontentloaded",timeout=22000)
                status=response.status if response else 0
                if status in (401,403,429):
                    print(json.dumps({"modo":"chromium","ruta":nombre,"http":status,"estado":"denegado"}),flush=True)
                    return
                if status!=200:
                    print(json.dumps({"modo":"chromium","ruta":nombre,"http":status,"estado":"http_no_200"}),flush=True)
                    return
                page.wait_for_timeout(3500)
                data=page.evaluate("""() => ({
                  text: (document.body?.innerText || '').slice(0,3200),
                  title: document.title,
                  ldScripts:document.querySelectorAll('script[type="application/ld+json"]').length,
                  productLinks:document.querySelectorAll('a[href*="/articulo/"]').length
                })""")
                body=data["text"].lower()
                if any(b in body for b in ("robot or human","captcha","access denied","perimeterx")):
                    print(json.dumps({"modo":"chromium","ruta":nombre,"http":status,"estado":"verificacion"}),flush=True)
                    return
                products=extraer(page.content())
                print(json.dumps({"modo":"chromium","ruta":nombre,"http":status,
                   "titulo":data["title"],"jsonld_scripts":data["ldScripts"],
                   "enlaces_articulos":data["productLinks"],"jsonld_productos":len(products),
                   "con_precio":sum(bool(x["precio"]) for x in products),
                   "muestra":products[:4],
                   "texto_productos":bool(re.search("leche descremada",body))},ensure_ascii=False),flush=True)
            except BrowserTimeout:
                print(json.dumps({"modo":"chromium","ruta":nombre,"estado":"timeout"}),flush=True)
            except Exception as ex:
                print(json.dumps({"modo":"chromium","ruta":nombre,"error":type(ex).__name__}),flush=True)
            finally:
                page.close()
        finally:
            browser.close()

if __name__=="__main__":
    diagnostico_requests()
    diagnostico_chromium()
