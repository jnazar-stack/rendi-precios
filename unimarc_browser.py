"""Lector de productos visibles en páginas públicas de Unimarc con Chromium.

Usa los precios normales que están en las tarjetas públicas. No inicia sesión,
ni resuelve verificaciones, ni utiliza APIs ocultas. Una página por consulta.
"""
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

DOM_PRODUCTS = r"""
() => {
  const nodes = [...document.querySelectorAll('[class*="Shelf_nameProduct"]')];
  const results = [];
  for (const el of nodes) {
    let card = el;
    let text = "";
    for (let depth=0; depth<7 && card; depth++, card=card.parentElement) {
      const t=(card.innerText||'').replace(/\s+/g,' ').trim();
      if (t.length>10 && t.length<1200 && /\$\s*[\d.]{3,}/.test(t)
          && card.querySelector('a[href*="/product/"]')) {
        text=t;
        break;
      }
    }
    if (!card) continue;
    const money=(text.match(/\$\s*([0-9.]{3,})/)||[])[1]||"";
    const price=Number(money.replace(/\./g,''));
    const name=(el.innerText||'').trim();
    if (!name || !price || price>1000000) continue;
    const brand=(card.querySelector('[class*="Shelf_brandText"]')?.innerText||'').trim();
    const link=card.querySelector('a[href*="/product/"]')?.getAttribute('href')||"";
    const img=card.querySelector('img')?.getAttribute('src')||null;
    const stock=!/sin stock|agotado|no disponible/i.test(text);
    results.push({name,brand,price,href:link,img,stock,raw:text.slice(0,280)});
  }
  return results;
}
"""

BLOCK = ("robot or human", "captcha", "access denied", "px-captcha", "perimeterx")


class UnimarcBrowser:
    def __init__(self):
        self.manager = None
        self.browser = None
        self.page = None

    def __enter__(self):
        self.manager = sync_playwright().start()
        self.browser = self.manager.chromium.launch(headless=True)
        self.page = self.browser.new_page(locale="es-CL")
        return self

    def __exit__(self, *_):
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.manager:
            self.manager.stop()

    def consultar(self, q):
        url = "https://www.unimarc.cl/search?q=" + quote(q)
        try:
            response = self.page.goto(url,wait_until="domcontentloaded",timeout=22000)
            code = response.status if response else 0
            if code in (401,403,429):
                return None, "http " + str(code)
            if code != 200:
                return None, "http " + str(code)
            try:
                self.page.locator('[class*="Shelf_nameProduct"]').first.wait_for(timeout=12000)
            except PlaywrightTimeout:
                body=self.page.locator("body").inner_text(timeout=5000).lower()[:5000]
                if any(x in body for x in BLOCK):
                    return None,"bloqueado"
                return [],"sin resultados"
            objects = self.page.evaluate(DOM_PRODUCTS)
            items=[]
            for x in objects:
                href=x.get("href") or ""
                name=(x.get("name") or "").strip()
                brand=(x.get("brand") or "").strip()
                full=(" ".join([name,brand])).strip()
                text=x.get("raw") or ""
                p=float(x.get("price") or 0)
                if not p:
                    continue
                items.append({
                    "n":full, "p":p,
                    "size":full + " " + text[:160],
                    "img":x.get("img"),
                    "u":"https://www.unimarc.cl"+href if href.startswith("/") else href,
                    "stock":x.get("stock",True)
                })
            return items, "ok" if items else "sin resultados"
        except PlaywrightTimeout:
            return None, "timeout"
        except Exception:
            return None, "error lectura"


if __name__=="__main__":
    from actualizar import elegir, CAT
    pruebas = {
        "leche":"leche descremada",
        "huevo":"huevos 30",
        "arroz":"arroz grado 2",
        "pechuga":"pechuga deshuesada",
        "tomate":"tomate",
        "aceite":"aceite vegetal",
    }
    import json
    with UnimarcBrowser() as b:
        for pid,q in pruebas.items():
            it,status=b.consultar(q)
            picked=elegir(it,CAT[pid]) if it else None
            print(json.dumps({"producto":pid,"consulta":q,"estado":status,
                 "leidos":len(it or []),"coincidencias":(picked or {}).get("n",0),
                 "eq":(picked or {}).get("eq",{}).get("n"),
                 "precio":(picked or {}).get("eq",{}).get("p"),
                 "muestra":[{"n":x["n"][:70],"p":x["p"]} for x in (it or [])[:3]]},ensure_ascii=False),flush=True)
            if status=="bloqueado" or (status or "").startswith("http 403"):
                break
