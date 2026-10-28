"""Verifica una búsqueda pública en Chromium, sin reintentos ni elusión de verificaciones."""
import json
from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout

URL = "https://www.unimarc.cl/search?q=leche%20descremada%201%20litro"

SCRIPT = """
() => {
  const txt = (document.body?.innerText || '').slice(0,14000);
  const sample = txt.slice(0,800).replace(/\\s+/g, ' ');
  const known = [
    'Shelf_nameProduct__CXI5M',
    'Shelf_brandText__sGfsS',
    'Shelf_', 'price', 'product-card'
  ];
  const count = Object.fromEntries(known.map(x =>
      [x, document.querySelectorAll('[class*="' + x.replace('__CXI5M','').replace('__sGfsS','') + '"]').length]
  ));
  const next = document.querySelector('#__NEXT_DATA__');
  let props = [];
  let route = '';
  try {
     const d = JSON.parse(next?.textContent || '{}');
     props = Object.keys(d.props?.pageProps || {}).slice(0,20);
     route = d.page || '';
  } catch(e) {}
  const hasPrice = /\\$\\s*[1-9][0-9.,]{2,7}/.test(txt);
  return {title:document.title, path:location.pathname, sample, count,
     hasPrice, hasColun:/Colun/i.test(txt), hasLeche:/Leche/i.test(txt),
     nextData:!!next, nextProps:props, route,
     hrefProductCount:document.querySelectorAll('a[href*="/product/"]').length,
     muestras:[...document.querySelectorAll('[class*="Shelf_nameProduct"]')].slice(0,3).map(el => {
       let p=el, niveles=[];
       for(let n=0;n<6 && p;n++,p=p.parentElement){
          const links=[...p.querySelectorAll('a[href*="/product/"]')].slice(0,2).map(a=>a.getAttribute('href'));
          niveles.push({n,tag:p.tagName,cls:String(p.className).slice(0,105),
            text:(p.innerText||'').replace(/\s+/g,' ').slice(0,240),links});
       }
       return {nombre:el.innerText,niveles};
     }),
     intelliProps:typeof (next && (() => {try{return JSON.parse(next.textContent).props?.pageProps?.intelliSearchData}catch(e){return null}})()),
   };
}
"""

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page=browser.new_page(locale="es-CL")
            try:
                resp=page.goto(URL,wait_until="domcontentloaded",timeout=25000)
                status=resp.status if resp else 0
                if status in (401,403,429):
                    print(json.dumps({"status":status,"estado":"denegado"}),flush=True)
                    return
                if status!=200:
                    print(json.dumps({"status":status,"estado":"http_error"}),flush=True)
                    return
                for delay in (0,5):
                    if delay: page.wait_for_timeout(delay*1000)
                    info=page.evaluate(SCRIPT)
                    sample=info.get("sample","").lower()
                    if any(x in sample for x in ("robot or human","access denied","captcha","px-captcha")):
                        print(json.dumps({"status":status,"estado":"verificacion"}),flush=True)
                        break
                    print(json.dumps({"espera_s":delay,"http":status,**info},ensure_ascii=False),flush=True)
            except BrowserTimeout:
                print(json.dumps({"estado":"timeout"}),flush=True)
            finally:
                page.close()
        finally:
            browser.close()

if __name__=="__main__":
    main()
