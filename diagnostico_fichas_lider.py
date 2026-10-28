"""Diagnóstico de lectura normal de páginas públicas de Líder.

No intenta reintentar denegaciones ni modificar cabeceras para aparentar una persona.
Solo prueba rutas de ficha/categoría disponibles públicamente.
"""
import re
import time
import json
import requests

UA = "RendiBot/1.0 (+https://github.com/jnazar-stack/rendi-precios; lector de precios publicos)"
URLS = [
    "https://super.lider.cl/v/leches-descremadas-1-l",
    "https://super.lider.cl/ip/leche/00780292000008",
]
BLOCK = re.compile(r"robot or human|are you a robot|captcha|access denied|perimeterx|px-captcha", re.I)

def main():
    session = requests.Session()
    session.headers.update({"User-Agent":UA,"Accept-Language":"es-CL,es;q=0.9"})
    for index, url in enumerate(URLS):
        if index:
            time.sleep(1.5)
        try:
            r=session.get(url, timeout=20)
            blocked = r.status_code in (401,403,429) or bool(BLOCK.search(r.text[:30000]))
            result = {
                "ruta": url.split("lider.cl",1)[1],
                "status":r.status_code,
                "bloqueado":blocked,
                "tamano_html":len(r.content),
                "menciona_colun":bool(re.search(r"Colun",r.text,re.I)),
                "menciona_precio":bool(re.search(r"\$\s*1[.,]?[0123456789]{3}|CLP\$",r.text,re.I)),
                "jsonld":len(re.findall(r'application/ld\+json',r.text,re.I))
            }
            print(json.dumps(result,ensure_ascii=False),flush=True)
            if blocked:
                break
        except requests.RequestException as e:
            print(json.dumps({"ruta":url.split("lider.cl",1)[1],"error":type(e).__name__}),flush=True)
            break

if __name__=="__main__":
    main()
