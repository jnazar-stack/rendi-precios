"""Diagnóstico de lectura de páginas con Chromium normal, SIN eludir bloqueos.

Una sola búsqueda por cadena; si aparece control antibot, termina.
No se guarda HTML, cookies, identidades ni datos del usuario.
"""
import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

CONSULTA = "leche descremada 1 litro"
CADENAS = {
    "lider": "https://super.lider.cl/search?q=" + quote(CONSULTA),
    "unimarc": "https://www.unimarc.cl/search?q=" + quote(CONSULTA),
    "tottus": "https://www.tottus.cl/tottus-cl/buscar?Ntt=" + quote(CONSULTA),
}
MARCAS_BLOQUEO = ("robot or human", "access denied", "captcha", "px-captcha", "perimeterx", "acceso denegado")

def revisar(page, nombre, url):
    try:
        respuesta = page.goto(url, wait_until="domcontentloaded", timeout=20000)
        codigo = respuesta.status if respuesta else 0
        if codigo in (401, 403, 429):
            return {"cadena": nombre, "http": codigo, "resultado": "acceso denegado"}
        if codigo != 200:
            return {"cadena": nombre, "http": codigo, "resultado": "http inesperado"}
        page.wait_for_timeout(1300)
        cuerpo = page.locator("body").inner_text(timeout=5000)[:2500].lower()
        if any(marca in cuerpo for marca in MARCAS_BLOQUEO):
            return {"cadena": nombre, "http": codigo, "resultado": "verificacion antibot"}
        ld = page.locator('script[type="application/ld+json"]').count()
        nd = page.locator('script#__NEXT_DATA__').count()
        return {"cadena": nombre, "http": codigo, "resultado": "pagina accesible",
                "json_ld_scripts": ld, "next_data_scripts": nd}
    except PlaywrightTimeout:
        return {"cadena": nombre, "resultado": "timeout"}
    except Exception as exc:
        return {"cadena": nombre, "resultado": "error",
                "tipo": type(exc).__name__}


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for nombre, url in CADENAS.items():
                page = browser.new_page(locale="es-CL")
                try:
                    print(json.dumps(revisar(page, nombre, url), ensure_ascii=False), flush=True)
                finally:
                    page.close()
        finally:
            browser.close()

if __name__ == "__main__":
    main()
