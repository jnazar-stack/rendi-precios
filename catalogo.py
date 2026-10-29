"""Catálogo amplio de alimentos: lee una vez al día las páginas públicas de búsqueda de cada cadena
para ~150 alimentos y guarda todos los productos que aparecen (nombre, marca, precio, foto y código
de barras cuando la cadena lo publica). Escribe catalogo.json para que la app compare cualquier
producto de comida, no solo los del menú.

También lee los códigos de barras que la gente escaneó en Rendi (tabla pública en Supabase, sin datos
personales) y busca esos productos por su código, para tener su precio exacto en cada cadena.

Mismo criterio que actualizar.py: solo páginas públicas, una a la vez, ~1,5 s entre una y otra, el lector
se identifica, y si una cadena pide verificación anti-robots se deja de consultar ese día.

Cómo se reconoce el mismo producto en varias cadenas:
- Alvi publica el código de barras (EAN) de cada producto.
- Unimarc es de la misma empresa que Alvi y nombra igual sus productos: se le asigna el EAN por nombre.
- Jumbo y Santa Isabel comparten el número de producto. El EAN está en la página de cada producto; se
  lee una sola vez por producto (máximo EAN_POR_DIA al día) y se guarda en ean_vtex.json.
- Lider no publica un EAN real: se une por marca, tamaño y nombre cuando el calce es claro.
"""
import json
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import actualizar as A
from actualizar import get, ld_lists, next_data, walk, norm, num, size_of, BLOQUEO, log, LOG

EAN_POR_DIA = 450
CODIGOS_POR_DIA = 150
SUPABASE = "https://dxtokqsxhqqqcvzeohqu.supabase.co"
# Clave pública de la app (la misma que va dentro de Rendi). Solo permite leer la lista de códigos
# y registrar uno nuevo; no da acceso a nada más.
SUPABASE_KEY = "sb_publishable_Q5OPypm4EWMYt5vE5Tfcug_rSkcgOJ3"

# Alimentos a buscar, en orden de prioridad (lo más comprado primero).
TERMINOS = [
    # lácteos y huevos
    "leche descremada", "leche semidescremada", "leche entera", "leche sin lactosa", "leche en polvo", "leche cultivada",
    "yogurt natural", "yogurt griego", "yogurt proteina", "yoghurt batido", "huevos", "queso gauda", "queso mantecoso",
    "queso fresco", "quesillo", "queso parmesano", "queso crema", "queso laminado", "mantequilla", "margarina",
    "crema de leche", "manjar", "postre", "leche chocolatada",
    # carnes, aves y pescados
    "pechuga de pollo", "trutro de pollo", "pollo entero", "alitas de pollo", "filetitos de pollo", "carne molida",
    "posta negra", "lomo vetado", "lomo liso", "asiento", "sobrecostilla", "plateada", "punta de ganso", "carne para guisar",
    "chuleta de cerdo", "lomo de cerdo", "costillar de cerdo", "pavo", "pechuga de pavo", "hamburguesa", "vienesas",
    "longaniza", "chorizo", "jamon de pavo", "jamon de cerdo", "salame", "tocino", "salmon", "merluza", "reineta",
    "atun", "jurel", "sardinas", "camarones", "choritos",
    # despensa
    "arroz", "fideos", "spaghetti", "tallarines", "lentejas", "porotos", "garbanzos", "arvejas partidas", "quinoa",
    "avena", "harina", "azucar", "endulzante", "sal", "aceite vegetal", "aceite de oliva", "vinagre", "salsa de tomate",
    "pure de tomate", "mayonesa", "ketchup", "mostaza", "caldo", "sopa", "cereal", "granola", "mantequilla de mani",
    "mermelada", "miel", "cafe", "te", "chocolate", "galletas", "pan de molde", "pan integral", "tortillas", "pan pita",
    "tostadas", "galletas de arroz", "choclo", "palmitos", "aceitunas", "champiñones en conserva", "duraznos en conserva",
    "salsa de soya", "especias", "polvo de hornear", "levadura",
    # congelados
    "verduras congeladas", "papas prefritas", "frutillas congeladas", "pizza", "empanadas", "nuggets", "helado",
    # frutas y verduras
    "platano", "manzana", "naranja", "mandarina", "limon", "palta", "tomate", "lechuga", "zanahoria", "cebolla", "papa",
    "brocoli", "coliflor", "zapallo italiano", "pimenton", "pepino", "espinaca", "ajo", "champiñon", "frutilla", "uva",
    "pera", "kiwi", "pina", "melon", "betarraga", "apio", "repollo", "camote", "zapallo",
    # frutos secos y snacks
    "nueces", "almendras", "mani", "pasas", "frutos secos", "barra de cereal", "barra de proteina", "semillas de chia",
    # bebidas y suplementos
    "agua mineral", "agua con gas", "jugo", "nectar", "bebida zero", "leche de almendras", "bebida de avena",
    "proteina whey", "creatina",
]
STOP = set("de la el los las en con y al del para x un una unidad unidades un. pack bolsa caja botella frasco pote bandeja".split())


# ---------------------------------------------------------------- lectura por cadena
def vtex(base, q, page=1):
    """Jumbo y Santa Isabel: lista pública (JSON-LD) de la página de búsqueda, con marca y número de producto."""
    st, t = get(f"{base}/busqueda?ft={A.quote(q)}" + (f"&page={page}" if page > 1 else ""))
    if st != 200:
        return None, f"http {st}"
    if BLOQUEO.search(t[:20000]) and "ItemList" not in t:
        return None, "bloqueado"
    out = []
    for L in ld_lists(t):
        for el in L.get("itemListElement", []):
            it = el.get("item") or {}
            off = it.get("offers") or {}
            off = off[0] if isinstance(off, list) and off else off
            p = num(off.get("price"))
            url = it.get("url") or off.get("url") or ""
            m = re.search(r"\.cl/([^?#]*-(\d+))/p\b", url)
            if not p or not m:
                continue
            img = it.get("image")
            img = img[0] if isinstance(img, list) and img else img
            out.append(dict(n=it.get("name") or "", b=((it.get("brand") or {}).get("name") if isinstance(it.get("brand"), dict) else it.get("brand")) or "",
                            p=p, img=img, vid=m.group(2), slug=m.group(1), stock="InStock" in str(off.get("availability", "InStock"))))
    return out, "ok" if out else "sin resultados"


def alvi(q):
    st, t = get(f"https://www.alvi.cl/search?q={A.quote(q)}")
    if st != 200:
        return None, f"http {st}"
    d = next_data(t)
    if not d:
        return None, "bloqueado" if BLOQUEO.search(t[:20000]) else "sin datos"
    found = []
    walk(d, lambda o: "sellers" in o and ("nameComplete" in o or "name" in o) and "detailUrl" in o, found)
    out = []
    for x in found:
        sel = (x.get("sellers") or [{}])[0] or {}
        p = num(sel.get("price"))
        if not p:
            continue
        out.append(dict(n=x.get("nameComplete") or x.get("name") or "", b=x.get("brand") or "", p=p,
                        img=(x.get("images") or [None])[0], ean=str(x.get("ean") or "") or None,
                        stock=(sel.get("availableQuantity", 1) or 0) > 0))
    return out, "ok" if out else "sin resultados"


def lider_slugs():
    slugs = set()
    for n in (0, 1, 2):
        st, t = get(f"https://super.lider.cl/v/nc/sitemap/keyword-{n}.xml")
        if st == 200:
            slugs.update(re.findall(r"<loc>https://super\.lider\.cl/v/([^<]+)</loc>", t))
    return slugs


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", norm(t)).strip("-")


def lider_v(slug):
    st, t = get(f"https://super.lider.cl/v/{slug}")
    if st != 200:
        return None, f"http {st}"
    L = ld_lists(t)
    if not L:
        return None, "bloqueado" if BLOQUEO.search(t[:20000]) else "sin datos"
    out = []
    for lista in L:
        for el in lista.get("itemListElement", []):
            it = (el or {}).get("item") or {}
            off = it.get("offers") or {}
            off = off[0] if isinstance(off, list) and off else off
            p = num((off or {}).get("price")) if isinstance(off, dict) else None
            if not p:
                continue
            img = it.get("image")
            img = img[0] if isinstance(img, list) and img else img
            img = img.get("url") if isinstance(img, dict) else img
            name = it.get("name") or ""
            granel = bool(re.search(r"\bgranel\b", norm(name)))
            out.append(dict(n=name, b="", p=p, img=img, granel=granel, stock="OutOfStock" not in str(off.get("availability", ""))))
    return out, "ok" if out else "sin resultados"


def vtex_ean(slug, bases):
    """EAN de un producto de Jumbo/Santa Isabel desde su página pública (una sola vez por producto)."""
    for base in bases:
        st, t = get(f"{base}/{slug}/p")
        if st == 200:
            raw = t.replace('\\"', '"')
            m = re.search(r'"ean"\s*:\s*"(\d{8,14})"', raw) or re.search(r'"gtin"\s*:\s*"(\d{8,14})"', raw)
            return m.group(1) if m else ""
        if st in (403, 429):
            return None
    return ""


# ---------------------------------------------------------------- unir el mismo producto entre cadenas
def tokens(name):
    t = norm(name)
    t = re.sub(r"(\d)[,.](\d)", r"\1\2", t)
    return {w for w in re.findall(r"[a-z0-9%]+", t) if w not in STOP and len(w) > 1}


def size_key(name):
    s = size_of(name)
    if not s:
        return None
    q, base, n = s
    return f"{round(q)}{base}"


def similar(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0
    return len(ta & tb) / len(ta | tb)


def key_name(name, brand=""):
    return " ".join(sorted(tokens(name + " " + brand)))


def construir(registros):
    """Agrupa los registros de las 5 cadenas en productos únicos."""
    prods = {}      # clave -> producto
    por_ean = {}
    por_vid = {}
    por_nombre_smu = {}

    def nuevo(clave, r, termino):
        p = dict(k=clave, n=r["n"], b=r.get("b") or "", img=r.get("img"), e=r.get("ean") or None, t=termino, pr={}, sz=size_key(r["n"]))
        prods[clave] = p
        return p

    def poner(p, r):
        ci = str(r["ci"])
        if ci not in p["pr"] or r["p"] < p["pr"][ci]:
            p["pr"][ci] = round(r["p"])
        if not p.get("img") and r.get("img"):
            p["img"] = r["img"]
        if not p.get("b") and r.get("b"):
            p["b"] = r["b"]

    # 1) Alvi: EAN directo
    for r in [r for r in registros if r["ci"] == 5]:
        if r.get("ean"):
            p = por_ean.get(r["ean"]) or nuevo("e" + r["ean"], r, r["t"])
            por_ean[r["ean"]] = p
            por_nombre_smu.setdefault(key_name(r["n"]), p)
            poner(p, r)
    # 2) Jumbo y Santa Isabel: número de producto compartido; EAN si ya se conoce
    for r in [r for r in registros if r["ci"] in (2, 3)]:
        p = por_vid.get(r["vid"])
        if not p and r.get("ean"):
            p = por_ean.get(r["ean"])
        if not p:
            p = nuevo("e" + r["ean"] if r.get("ean") else "v" + r["vid"], r, r["t"])
            if r.get("ean"):
                por_ean[r["ean"]] = p
                if not p.get("e"):
                    p["e"] = r["ean"]
        por_vid[r["vid"]] = p
        poner(p, r)
    def precio_calza(p, r):
        """Al unir por nombre (sin código de barras), el precio tiene que ser parecido: evita juntar un pack con una unidad."""
        vs = sorted(p["pr"].values())
        if not vs:
            return True
        m = vs[len(vs) // 2]
        return m * 0.45 <= r["p"] <= m * 2.2

    # 3) Unimarc: mismo nombre que en Alvi; si no, por similitud
    # 4) Lider: por marca, tamaño y nombre
    por_t = {}
    for q in prods.values():
        por_t.setdefault(q["t"], []).append(q)
    for r in [r for r in registros if r["ci"] in (1, 0)]:
        p = por_nombre_smu.get(key_name(r["n"])) if r["ci"] == 1 else None
        if p and (str(r["ci"]) in p["pr"] or not precio_calza(p, r)):
            p = None
        if not p:
            sz = size_key(r["n"])
            best, bs = None, 0
            for q in por_t.get(r["t"], []):
                if str(r["ci"]) in q["pr"]:
                    continue
                if sz and q.get("sz") and sz != q["sz"]:
                    continue
                if q.get("b") and norm(q["b"]) not in norm(r["n"] + " " + (r.get("b") or "")):
                    continue
                if not precio_calza(q, r):
                    continue
                s = similar(r["n"], q["n"])
                if s > bs:
                    best, bs = q, s
            if best and bs >= 0.6:
                p = best
        if not p:
            p = nuevo(f"c{r['ci']}-" + slugify(r["n"])[:60], r, r["t"])
            por_t.setdefault(r["t"], []).append(p)
        poner(p, r)
    return list(prods.values())


# ---------------------------------------------------------------- códigos escaneados (Supabase)
def codigos_escaneados():
    try:
        r = A.S.get(f"{SUPABASE}/rest/v1/codigos", params={"select": "codigo,veces", "order": "veces.desc,ultima.desc", "limit": str(CODIGOS_POR_DIA)},
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=30)
        if r.status_code == 200:
            return [x["codigo"] for x in r.json() if re.fullmatch(r"\d{8,14}", str(x.get("codigo", "")))]
        log("   códigos escaneados: http", r.status_code)
    except Exception as e:
        log("   códigos escaneados: error", type(e).__name__)
    return []


# ---------------------------------------------------------------- principal
def main():
    ahora = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    try:
        cache = json.load(open("ean_vtex.json", encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    solo = int(sys.argv[1]) if len(sys.argv) > 1 else None
    terminos = TERMINOS[:solo] if solo else TERMINOS
    registros, estado, bloq = [], {k: {} for k in ("lider", "unimarc", "jumbo", "sisa", "alvi")}, set()
    nombres = {0: "lider", 1: "unimarc", 2: "jumbo", 3: "sisa", 5: "alvi"}
    vtex_slug = {}

    def anotar(ci, e):
        estado[nombres[ci]][e] = estado[nombres[ci]].get(e, 0) + 1
        if A.es_bloqueo(e):
            bloq.add(ci)
            log(f"   {nombres[ci]}: pidió verificación; no se consulta más hoy")

    slugs = lider_slugs()
    log(f"Lider: {len(slugs)} páginas de categoría públicas en su mapa del sitio")
    uni = None
    from contextlib import ExitStack
    pila = ExitStack()
    for t in terminos:
        for ci in (2, 3, 5, 0, 1):
            if ci in bloq:
                continue
            if ci in (2, 3):
                items, e = vtex("https://www.jumbo.cl" if ci == 2 else "https://www.santaisabel.cl", t)
            elif ci == 5:
                items, e = alvi(t)
            elif ci == 0:
                s = slugify(t)
                slug = s if s in slugs else next((x for x in sorted(slugs, key=len) if x.startswith(s + "-")), None)
                if not slug:
                    continue
                items, e = lider_v(slug)
            else:
                try:
                    if uni is None:
                        from unimarc_browser import UnimarcBrowser
                        uni = pila.enter_context(UnimarcBrowser())
                    items, e = uni.consultar(t)
                except Exception as err:
                    items, e = None, "error navegador"
                    log("   Unimarc:", type(err).__name__)
                    bloq.add(1)
            anotar(ci, e)
            for r in items or []:
                if not r.get("n") or not r.get("p") or not r.get("stock", True):
                    continue
                r = dict(r, ci=ci, t=t)
                if ci in (2, 3):
                    vtex_slug.setdefault(r["vid"], (r["slug"], set()))[1].add("https://www.jumbo.cl" if ci == 2 else "https://www.santaisabel.cl")
                    if cache.get(r["vid"]):
                        r["ean"] = cache[r["vid"]]
                registros.append(r)
        log(f"{t:28s} {len(registros):6d} registros")

    # EAN de Jumbo/Santa Isabel que aún no se conocen (pocos por día, quedan guardados)
    faltan = [v for v in dict.fromkeys(r["vid"] for r in registros if r["ci"] in (2, 3)) if v not in cache]
    leidos = 0
    for vid in faltan[:EAN_POR_DIA]:
        if 2 in bloq and 3 in bloq:
            break
        slug, bases = vtex_slug[vid]
        e = vtex_ean(slug, [b for b in ("https://www.jumbo.cl", "https://www.santaisabel.cl") if b in bases])
        if e is None:
            log("   Jumbo/Santa Isabel: acceso denegado a la página de producto; se sigue mañana")
            break
        cache[vid] = e
        leidos += 1
    for r in registros:
        if r["ci"] in (2, 3) and cache.get(r["vid"]):
            r["ean"] = cache[r["vid"]]
    log(f"EAN de Jumbo/Santa Isabel: {leidos} nuevos hoy, {sum(1 for v in cache.values() if v)} conocidos, faltan {max(0, len(faltan) - leidos)}")

    # Códigos escaneados en la app: búsqueda por código en Alvi y Unimarc (las que lo permiten)
    codigos = codigos_escaneados()
    conocidos = {r.get("ean") for r in registros if r.get("ean")}
    nuevos = [c for c in codigos if c not in conocidos]
    log(f"Códigos escaneados: {len(codigos)}; por buscar: {len(nuevos)}")
    for c in nuevos:
        if 5 not in bloq:
            items, e = alvi(c)
            anotar(5, e)
            for r in items or []:
                if r.get("ean") == c and r.get("p"):
                    registros.append(dict(r, ci=5, t="escaneado"))
        if 1 not in bloq and uni is not None:
            items, e = uni.consultar(c)
            anotar(1, e)
            for r in (items or [])[:1]:
                registros.append(dict(r, ci=1, t="escaneado", ean=c))
    pila.close()

    prods = construir(registros)
    # Productos escaneados que Unimarc encontró por código: unir por EAN directo
    out = []
    for p in prods:
        p.pop("sz", None)
        if not p["pr"]:
            continue
        out.append(p)
    multi = sum(1 for p in out if len(p["pr"]) >= 2)
    data = dict(fecha=ahora, n=len(out), estado=estado, p=out)
    with open("catalogo.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open("ean_vtex.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"))
    with open("registro_catalogo.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(LOG) + "\n")
    log(f"\nListo: {len(out)} productos de comida ({multi} con precio en 2 o más cadenas).")


if __name__ == "__main__":
    main()
