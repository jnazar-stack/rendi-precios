"""Suplementos: lee una vez al día los catálogos públicos de tiendas de suplementos y de supermercados,
y guarda marca, nombre, tamaño, precio, foto y, cuando la tienda lo publica en texto, la porción, las
porciones por envase y la proteína por porción. Escribe suplementos.json para la app.

Fuentes:
- Tiendas hechas en Shopify (Allnutrition, Supletech si su tienda es Shopify): Shopify publica el catálogo en
  /products.json. Se leen como máximo PAGINAS páginas por tienda.
- Jumbo y Lider: sus páginas públicas de búsqueda, con los mismos lectores que usa el catálogo de alimentos.

Mismo criterio que actualizar.py: el lector se identifica, respeta robots.txt, va de a una página con pausa,
y si una tienda niega el acceso o pide verificación anti-robots se deja hasta el día siguiente.
"""
import json
import re
import sys
import urllib.robotparser
from datetime import datetime
from zoneinfo import ZoneInfo

import actualizar as A
from actualizar import get, norm, num, log, LOG, es_bloqueo, UA
import catalogo as C

PAGINAS = 20  # 250 productos por página

TIENDAS_SHOPIFY = [
    # id, nombre, dominios a probar (el primero que responda)
    ("allnutrition", "Allnutrition", ["https://allnutrition.cl"]),
    ("supletech", "Supletech", ["https://www.supletech.cl", "https://supletech.cl"]),
]
BUSQUEDAS = ["proteina whey", "proteina isolate", "creatina", "barra proteina", "proteina vegana"]

CATS = [  # (categoría, palabras), en orden: la primera que calza gana
    ("barra", ["barra", "bar ", "cookie", "galleta", "wafer", "brownie"]),
    ("creatina", ["creatin", "creapure"]),
    ("ganador", ["gainer", "ganador", "mass", "masa muscular"]),
    ("proteina", ["whey", "proteina", "protein", "isolate", "isolat", "hidroliz", "caseina", "casein", "iso "]),
    ("preentreno", ["pre-entreno", "preentreno", "pre entreno", "pre-workout", "preworkout", "c4", "cafeina", "caffeine"]),
    ("omega3", ["omega", "fish oil", "aceite de pescado"]),
    ("vitamina-d", ["vitamina d", "vitamin d", "d3"]),
    ("aminoacidos", ["bcaa", "amino", "glutamin", "eaa", "leucin"]),
    ("quemador", ["quemador", "burner", "termogen", "carnitin", "cla "]),
    ("multivitaminico", ["multivit", "multi vit", "vitamin", "magnesio", "zinc", "colageno", "collagen", "melatonin"]),
]
NO_SUPLE = ["shaker", "polera", "botella", "toalla", "guante", "cinturon", "mochila", "bolso", "straps", "muñequera", "gift card", "tarjeta de regalo"]


def categoria(texto):
    t = " " + norm(texto) + " "
    if any(w in t for w in NO_SUPLE):
        return None
    for c, ws in CATS:
        if any(w in t for w in ws):
            return c
    return None


def gramos(texto):
    """Tamaño del envase en gramos, desde el nombre: 5 lb, 2,2 lbs, 1 kg, 300 g, 908gr."""
    t = norm(texto).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lb|lbs|libras?)\b", t)
    if m:
        return round(float(m.group(1)) * 453.6)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilo)", t)
    if m:
        return round(float(m.group(1)) * 1000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(g|gr|grs|gramos)\b", t)
    if m and float(m.group(1)) >= 20:
        return round(float(m.group(1)))
    return None


def porciones(texto):
    t = norm(texto)
    m = re.search(r"(\d{2,3})\s*(servicios|servings|serv|porciones|svs|sv)\b", t)
    return int(m.group(1)) if m else None


def texto_plano(html):
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    return re.sub(r"\s+", " ", t)


def nutricion(texto):
    """Porción (g), proteína y kcal por porción, solo si la ficha los trae en texto y son verosímiles."""
    t = norm(texto).replace(",", ".")
    sv = re.search(r"(?:porcion|tamano de la porcion|serving size)[^0-9]{0,30}(\d+(?:\.\d+)?)\s*(?:g|gr)\b", t)
    pr = re.search(r"proteinas?[^0-9a-z]{0,25}(\d+(?:\.\d+)?)\s*g\b", t)
    kc = re.search(r"(?:energia|calorias)[^0-9]{0,30}(\d+(?:\.\d+)?)\s*(?:kcal|cal)\b", t)
    out = {}
    if sv and 2 <= float(sv.group(1)) <= 150:
        out["sv"] = float(sv.group(1))
    if pr and 1 <= float(pr.group(1)) <= 60:
        out["ps"] = float(pr.group(1))
    if kc and 5 <= float(kc.group(1)) <= 900:
        out["ks"] = float(kc.group(1))
    # La proteína por porción no puede ser más que la porción.
    if "ps" in out and "sv" in out and out["ps"] > out["sv"]:
        out.pop("ps")
    return out


def robots_ok(base, ruta):
    rp = urllib.robotparser.RobotFileParser()
    st, t = get(base + "/robots.txt")
    if st != 200:
        return True  # sin robots.txt: no hay reglas
    rp.parse(t.splitlines())
    return rp.can_fetch(UA, base + ruta)


def shopify(tid, nombre, dominios):
    for base in dominios:
        st, t = get(base + "/products.json?limit=1")
        if st != 200 or not t.lstrip().startswith("{"):
            log(f"  {nombre}: {base} no responde como tienda Shopify (http {st})")
            continue
        if not robots_ok(base, "/products.json"):
            log(f"  {nombre}: robots.txt no permite leer el catálogo; se omite")
            return [], "robots"
        out = []
        for page in range(1, PAGINAS + 1):
            st, t = get(f"{base}/products.json?limit=250&page={page}")
            if st != 200:
                estado = f"http {st}"
                log(f"  {nombre}: página {page} -> {estado}")
                return out, estado if es_bloqueo(estado) else "parcial"
            try:
                prods = json.loads(t).get("products") or []
            except ValueError:
                return out, "bloqueado"
            if not prods:
                break
            for pr in prods:
                titulo = pr.get("title") or ""
                cuerpo = texto_plano(pr.get("body_html"))
                cat = categoria(" ".join([titulo, pr.get("product_type") or "", " ".join(pr.get("tags") or []) if isinstance(pr.get("tags"), list) else str(pr.get("tags") or "")]))
                if not cat:
                    continue
                nu = nutricion(cuerpo)
                img = ((pr.get("images") or [{}])[0] or {}).get("src")
                for v in pr.get("variants") or []:
                    p = num(v.get("price"))
                    if not p:
                        continue
                    vt = v.get("title") or ""
                    n = titulo if vt in ("", "Default Title") else f"{titulo} · {vt}"
                    g = gramos(n) or (round(v["grams"]) if (v.get("grams") or 0) >= 20 and cat not in ("barra",) else None)
                    it = dict(t=tid, n=n, b=pr.get("vendor") or "", cat=cat, p=p, g=g,
                              serv=porciones(n) or porciones(cuerpo), img=img,
                              u=f"{base}/products/{pr.get('handle')}" + (f"?variant={v.get('id')}" if len(pr.get("variants") or []) > 1 else ""),
                              disp=bool(v.get("available", True)))
                    pc = num(v.get("compare_at_price"))
                    if pc and pc > p:
                        it["antes"] = pc
                    it.update(nu)
                    out.append(it)
            log(f"  {nombre}: página {page}, {len(out)} suplementos hasta ahora")
        return out, "ok" if out else "sin resultados"
    return [], "sin tienda"


def supers():
    out, estados = [], {}
    for tid, base in (("jumbo", "https://www.jumbo.cl"),):
        n0 = len(out)
        for q in BUSQUEDAS:
            items, est = C.vtex(base, q)
            if items is None:
                estados[tid] = est
                if es_bloqueo(est):
                    break
                continue
            for x in items:
                cat = categoria(x["n"])
                if cat:
                    out.append(dict(t=tid, n=x["n"], b=x.get("b") or "", cat=cat, p=x["p"], g=gramos(x["n"]), serv=porciones(x["n"]),
                                    img=x.get("img"), u=f"{base}/{x['slug']}/p", disp=x.get("stock", True)))
        estados.setdefault(tid, "ok" if len(out) > n0 else "sin resultados")
    n0 = len(out)
    for q in BUSQUEDAS:
        items, est = A.lider(q)
        if items is None:
            estados["lider"] = est
            if es_bloqueo(est):
                break
            continue
        for x in items:
            cat = categoria(x["n"])
            if cat:
                out.append(dict(t="lider", n=x["n"], b="", cat=cat, p=x["p"], g=gramos(x["n"]), serv=porciones(x["n"]),
                                img=x.get("img"), u=x.get("u"), disp=x.get("stock", True)))
    estados.setdefault("lider", "ok" if len(out) > n0 else "sin resultados")
    return out, estados


def metricas(it):
    """Lo que de verdad sirve para comparar: costo por gramo de proteína y por dosis de creatina (5 g)."""
    if it["cat"] in ("proteina", "ganador") and it.get("ps") and it.get("serv"):
        it["pg"] = round(it["p"] / (it["ps"] * it["serv"]), 1)
    elif it["cat"] in ("proteina",) and it.get("g") and it.get("ps") and it.get("sv"):
        it["pg"] = round(it["p"] / (it["g"] / it["sv"] * it["ps"]), 1)
    if it["cat"] == "creatina" and it.get("g"):
        it["pd"] = round(it["p"] / (it["g"] / 5))
    return it


def main():
    ahora = datetime.now(ZoneInfo("America/Santiago"))
    log(f"Suplementos {ahora:%Y-%m-%d %H:%M}")
    items, tiendas = [], {}
    for tid, nombre, doms in TIENDAS_SHOPIFY:
        xs, est = shopify(tid, nombre, doms)
        tiendas[tid] = {"n": nombre, "estado": est, "cuantos": len(xs)}
        items += xs
    xs, ests = supers()
    for tid, est in ests.items():
        tiendas[tid] = {"n": {"jumbo": "Jumbo", "lider": "Lider"}[tid], "estado": est, "cuantos": sum(1 for x in xs if x["t"] == tid)}
    items += xs
    # Sin repetidos (misma tienda y mismo nombre: queda el más barato).
    vistos = {}
    for it in items:
        k = (it["t"], norm(it["n"]))
        if k not in vistos or it["p"] < vistos[k]["p"]:
            vistos[k] = it
    items = [metricas(x) for x in vistos.values()]
    items.sort(key=lambda x: (x["cat"], x.get("pg") or x.get("pd") or 9e9, x["p"]))
    for tid, d in tiendas.items():
        log(f"  {d['n']}: {d['estado']}, {d['cuantos']} productos")
    with open("suplementos.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": ahora.strftime("%Y-%m-%d %H:%M"), "tiendas": tiendas, "items": items}, f, ensure_ascii=False, separators=(",", ":"))
    with open("registro_suplementos.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(LOG) + "\n")
    log(f"Listo: {len(items)} suplementos")


if __name__ == "__main__":
    main()
