"""Lee una vez al día los precios que cada supermercado muestra en sus páginas públicas de búsqueda
y de categoría, y escribe precios.json para la app Rendi.

Solo lee páginas públicas, a ritmo lento (una página cada ~1,5 s). Si una cadena responde con una
verificación anti-robots, se marca como "bloqueada" ese día y no se intenta saltar.

Índices históricos de cadena: 0 Lider, 1 Unimarc, 2 Jumbo, 3 Santa Isabel, 4 reservado (Tottus retirado del piloto), 5 Alvi.
"""
import html
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from statistics import median
from urllib.parse import quote

import requests

# Se identifica como lo que es: el lector de precios de Rendi, con un link para saber quién lo opera.
UA = "RendiBot/1.0 (+https://github.com/jnazar-stack/rendi-precios; lector diario de precios publicos)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9",
                  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
PAUSA = 1.5
LOG = []
# Índices históricos fijos: 4 (Tottus) queda reservado pero no participa en el piloto.
CADENAS_ACTIVAS = {0: "lider", 1: "unimarc", 2: "jumbo", 3: "sisa", 5: "alvi"}


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print(msg, flush=True)


def es_bloqueo(estado):
    """No insistir ante denegaciones o limitaciones de acceso."""
    return estado in ("bloqueado", "http 401", "http 403", "http 429")


def get(url):
    time.sleep(PAUSA)
    try:
        r = S.get(url, timeout=30)
        return r.status_code, r.text
    except Exception as e:  # red, tiempo de espera, etc.
        return 0, str(e)


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def num(s):
    if isinstance(s, (int, float)):
        return float(s)
    d = re.sub(r"[^\d]", "", str(s or ""))
    return float(d) if d else None


BLOQUEO = re.compile(r"robot or human|are you a robot|captcha|px-captcha|access denied|perimeterx", re.I)

# ---------------------------------------------------------------- catálogo
# kind: "g"/"ml" = se normaliza al tamaño pkg; "kg" = fruta/verdura a granel (precio por pkg gramos);
#       "un" = por unidad (pkg unidades); "lata" = precio por lata (net entre 120 y 200 g).
# inc: todas deben aparecer en el nombre; exc: ninguna; brand: marca recomendada (plan equilibrado).
CAT = {
    "huevo": dict(q="huevos 30 unidades", kind="un", pkg=30, inc=[r"huevo"], exc=[r"codorniz|chocolate|pascua|liquid|clara|cocid|codorni|kinder"],
                  uni=["lacteos-huevos-y-refrigerados/huevos/huevos-gallina"]),
    "leche": dict(q="leche descremada 1 litro", kind="ml", pkg=1000, inc=[r"leche", r"descrem"], brand="colun",
                  exc=[r"polvo|lactosa|chocolate|frutilla|vainilla|cultivad|evaporad|condens|cereal|200 ?ml|proteina|batido|avena|almendra|soya"],
                  uni=["lacteos-huevos-y-refrigerados/leches-y-cremas/leches-blancas"]),
    "yogurt": dict(q="yogurt griego natural", kind="g", pkg=1000, inc=[r"griego"], lo=0.35,
                   exc=[r"frutilla|berr|vainilla|mango|durazno|miel|coco|frambuesa|arandano|limon|maracuy|chocolate|cereal|frutos|pina|manjar|batido|bebible|papaya|kiwi|guinda"],
                   uni=["lacteos-huevos-y-refrigerados/yoghurt"]),
    "pechuga": dict(q="pechuga de pollo deshuesada", kind="g", pkg=1000, inc=[r"pechuga"],
                    exc=[r"pavo|apanad|nugget|empan|cocid|ahumad|jamon|hamburg|marinad|rellen|cordon|tender|crispy|asad|desmech"],
                    uni=["carnes/pollo/pechugas-y-filetitos"]),
    "trutro": dict(q="trutro entero de pollo", kind="g", pkg=1000, inc=[r"trutro"], exc=[r"pavo|apanad|cocid|asad|ahumad|marinad|alita"],
                   uni=["carnes/pollo/trutro"]),
    "molida": dict(q="carne molida vacuno", kind="g", pkg=500, inc=[r"molida"], exc=[r"pavo|pollo|cerdo|hamburg|soya|vegetal|congel"],
                   uni=["carnes/vacuno/molida-bistec-y-otros"]),
    "atun": dict(q="atun lomitos en agua", kind="lata", pkg=1, inc=[r"atun", r"agua"], brand="van camp",
                 exc=[r"aceite|salsa|ensalada|pate|tomate|limon|pouch|rallado"],
                 uni=["despensa/conservas/pescados-y-mariscos-en-conserva"]),
    "salmon": dict(q="salmon filete", kind="g", pkg=500, inc=[r"salmon"], exc=[r"ahumad|lata|conserva|hamburg|apanad|sushi|pate|jurel|merluza|nugget"],
                   uni=["congelados/pescados-y-mariscos/pescados"]),
    "lentejas": dict(q="lentejas 1 kg", kind="g", pkg=1000, inc=[r"lenteja"], exc=[r"lata|cocid|sopa|crema|snack|pasta|tarro|listas?|preparad|harina"],
                     uni=["despensa/arroz-y-legumbres/legumbres"]),
    "porotos": dict(q="porotos 1 kg", kind="g", pkg=1000, inc=[r"poroto"], exc=[r"lata|cocid|verde|granado|tarro|listos?|preparad|negro.*lata|harina"],
                    uni=["despensa/arroz-y-legumbres/legumbres"]),
    "garbanzos": dict(q="garbanzos 1 kg", kind="g", pkg=1000, inc=[r"garbanzo"], exc=[r"lata|cocid|hummus|snack|tarro|harina|listos?|preparad"],
                      uni=["despensa/arroz-y-legumbres/legumbres"]),
    "avena": dict(q="avena tradicional", kind="g", pkg=1000, inc=[r"avena"], lo=0.4,
                  exc=[r"bebida|leche|barra|galleta|cereal|salvado|harina|granola|vainilla|chocolate|manzana|canela|frutilla|proteica|sachet|crocante|bocado"],
                  uni=["desayuno-y-dulces/cereales/fibra-avena-y-granola"]),
    "arroz": dict(q="arroz grado 2 1 kg", kind="g", pkg=1000, inc=[r"arroz"], brand="tucapel",
                  exc=[r"integral|basmati|jazmin|sushi|arborio|lista|cocid|precocid|bolsit|vaporiz|leche|galleta|harina|salvaje|thai|chaufan|curry|preparad|graneado|primavera|mexican|risotto|sachet|minuto"],
                  uni=["despensa/arroz-y-legumbres/arroz"]),
    "fideos": dict(q="spaghetti 400 g", kind="g", pkg=400, inc=[r"spaghetti|espagueti|tallarin"],
                   exc=[r"integral|sin gluten|arroz|huevo|instant|ramen|salsa|lenteja|garbanzo|quinoa|verdura|espinaca"],
                   uni=["despensa/fideos-pastas-y-salsas/largos"]),
    "quinoa": dict(q="quinoa", kind="g", pkg=500, inc=[r"quinoa|quinua"], lo=0.3,
                   exc=[r"barra|snack|galleta|pop|inflad|harina|hamburg|ensalada|fideo|spaghetti|cereal|chips|bebida|mix|lenteja|mediterran|tricolor|sabor|lista|graneada"],
                   uni=["despensa/arroz-y-legumbres"]),
    "pan": dict(q="pan de molde integral", kind="g", pkg=600, inc=[r"pan", r"integral"], lo=0.6,
                exc=[r"pita|hamburg|hot ?dog|tostad|rallado|sin gluten|galleta|pascua|marraqueta|hallulla|tortilla|wrap"],
                uni=["panaderia-y-pasteleria/pan-envasado/pan-molde-y-pita"]),
    "aceite": dict(q="aceite vegetal 1 litro", kind="ml", pkg=900, inc=[r"aceite"], brand="belmont", lo=0.8, hi=1.3,
                   exc=[r"oliva|coco|sesamo|spray|palta|aerosol|motor|bebe|corporal|masaje|almendra|linaza|pepita|ajo|trufa"],
                   uni=["despensa/aceite-y-alinos/aceite-vegetal", "despensa/aceite-y-alinos/aceite-maravilla"]),
    "oliva": dict(q="aceite de oliva extra virgen 500 ml", kind="ml", pkg=460, inc=[r"oliva"], lo=0.8, hi=1.3,
                  exc=[r"spray|aerosol|aceituna|orujo|ajo|albahaca|trufa|limon|merken|romero"],
                  uni=["despensa/aceite-y-alinos/aceite-oliva"]),
    "mani": dict(q="mantequilla de mani", kind="g", pkg=340, inc=[r"mani", r"mantequilla|crema|pasta|untable"], lo=0.4,
                 exc=[r"chocolate|galleta|barra|snack|salado|confitado|japones|cacao|bombon|helado|alfajor"],
                 uni=["desayuno-y-dulces/mermelada-y-manjar", "despensa/coctel-y-snacks/frutos-secos"]),
    "nueces": dict(start=True, q="nueces mariposa", kind="g", pkg=250, inc=[r"nuez|nueces"], lo=0.4,
                   exc=[r"mix|chocolate|confitad|macadamia|pecan|brasil|cascara|moscada|coco|helado|galleta|caramel|miel|harina|aceite|leche|bebida"],
                   uni=["despensa/coctel-y-snacks/frutos-secos"]),
    "papas": dict(start=True, q="papa malla", kind="kg", pkg=2000, inc=[r"\bpapas?\b"],
                  exc=[r"frita|chips|congelad|pre ?frit|duquesa|pure|camote|lays|corte|hash|nativa|cocktail|baston|rustica|carozzi|sopa"],
                  uni=["frutas-y-verduras/verduras/verduras"]),
    "platano": dict(start=True, q="platano", kind="kg", pkg=1000, inc=[r"platano"],
                    exc=[r"deshidrat|chips|snack|yogurt|bebida|jugo|helado|nectar|frutos|pure|colado|papilla|harina|barra|galleta|compota|frito|chip|congel|macho|verde"],
                    uni=["frutas-y-verduras/frutas/fruta"]),
    "manzana": dict(start=True, q="manzana", kind="kg", pkg=1000, inc=[r"manzana"],
                    exc=[r"jugo|nectar|compota|deshidrat|chips|snack|vinagre|yogurt|bebida|tarta|pie|sidra|kuchen|papilla|colado|pure|galleta|barra|te |infusion|caramel"],
                    uni=["frutas-y-verduras/frutas/fruta"]),
    "tomate": dict(start=True, q="tomate", kind="kg", pkg=1000, inc=[r"tomate"],
                   exc=[r"salsa|pasta|pure|triturad|cherry|deshidrat|ketchup|conserva|seco|lata|jugo|pelado|cubos|sopa|caja|picad|corte|congel|coctel|cocktail|cherry|uva"],
                   uni=["frutas-y-verduras/verduras/verduras"]),
    "lechuga": dict(start=True, q="lechuga", kind="un", pkg=1, inc=[r"lechuga"], exc=[r"mix|ensalada|bolsa|hidropon.*pack"],
                    uni=["frutas-y-verduras/verduras/verduras"]),
    "zanahoria": dict(start=True, q="zanahoria", kind="kg", pkg=1000, inc=[r"zanahoria"],
                      exc=[r"jugo|baby|rallad|congel|conserva|torta|baston|papilla|colado|pure|crema|corte|juliana|cubos|picad|lista|dole"],
                      uni=["frutas-y-verduras/verduras/verduras"]),
    "brocoli": dict(start=True, q="brocoli", q2="brócoli unidad", kind="un", pkg=1, inc=[r"brocoli"], exc=[r"congel|pizza|crema|sopa|mix|florete|bolsa|pote|brote"],
                    uni=["frutas-y-verduras/verduras/verduras"]),
    "cebolla": dict(start=True, q="cebolla", kind="kg", pkg=1000, inc=[r"cebolla"],
                    exc=[r"morada|perla|frita|deshidrat|polvo|caramel|crema|sopa|cebollin|aros|escabeche|en vinagre|verde|cubos|picad|corte|pluma|lista|congel|anillo|tempura|apanad|crut|crouton|sopa|chips|snack"],
                    uni=["frutas-y-verduras/verduras/verduras"]),
    "palta": dict(start=True, q="palta hass", kind="kg", pkg=1000, inc=[r"palta"], exc=[r"aceite|guacamole|congel|pulpa|crema"],
                  uni=["frutas-y-verduras/frutas/fruta", "frutas-y-verduras/verduras/verduras"]),
}

for _k, _v in CAT.items():
    _v["_pid"] = _k  # para saber qué producto se está eligiendo (opción premium)

MARCA_PROPIA = re.compile(r"\b(cuisine ?& ?co|cuisine and co|jumbo|santa isabel|tottus|precio uno|merkat|unimarc|nuestra cocina|alvi|lider|great value|acuenta|mi tienda|seleccion unimarc|smu)\b")

# ---------------------------------------------------------------- tamaño
UNID = {"kg": ("g", 1000), "kilo": ("g", 1000), "kilos": ("g", 1000), "kgs": ("g", 1000), "g": ("g", 1), "gr": ("g", 1),
        "grs": ("g", 1), "gramos": ("g", 1), "l": ("ml", 1000), "lt": ("ml", 1000), "lts": ("ml", 1000), "litro": ("ml", 1000),
        "litros": ("ml", 1000), "ml": ("ml", 1), "cc": ("ml", 1), "cm3": ("ml", 1), "un": ("un", 1), "u": ("un", 1),
        "unid": ("un", 1), "unidades": ("un", 1), "unidad": ("un", 1), "huevos": ("un", 1)}
RX_PACK = re.compile(r"(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(kg|kilos?|kgs|g|gr|grs|gramos|l|lt|lts|litros?|ml|cc)\b")
RX_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|kilos?|kgs|g|gr|grs|gramos|l|lt|lts|litros?|ml|cc|cm3|un|u|unid|unidades|unidad|huevos)\b")
RX_XN = re.compile(r"\bx\s*(\d+)\s*(?:un|u|unid|unidades)?\b")


def size_of(text):
    """(cantidad, base) desde un texto como 'Leche 1 L', 'Pack 3 x 160 g', 'Huevos 30 un'. None si no hay."""
    t = norm(text).replace(" ", " ")
    m = RX_PACK.search(t)
    if m:
        base, mult = UNID[m.group(3)]
        return int(m.group(1)) * float(m.group(2).replace(",", ".")) * mult, base, int(m.group(1))
    m = RX_SIZE.search(t)
    if m:
        base, mult = UNID[m.group(2)]
        return float(m.group(1).replace(",", ".")) * mult, base, 1
    m = RX_XN.search(t)
    if m:
        return float(m.group(1)), "un", 1
    return None



# Rutas de categorías públicas verificadas en el sitio oficial. No son endpoints privados.
LIDER_CATEGORIAS = {
    "huevo": "huevos",
    "leche": "leches-descremadas-1-l",
    "yogurt": "yogurt-griego-natural",
    "pechuga": "pechuga-de-pollo",
    "trutro": "trutro-de-pollo",
    "molida": "carne-molida-vacuno",
    "atun": "atun",
    "salmon": "salmon",
    "lentejas": "lentejas-1-kg-sin-sello",
    "porotos": "porotos-1-kg",
    "garbanzos": "bolsas-de-garbanzos",
    "avena": "avena-tradicional",
    "arroz": "arroz",
    "fideos": "spaghetti",
    "quinoa": "quinoa",
    "pan": "pan-integral",
    "aceite": "aceite-vegetal",
    "oliva": "aceite-de-oliva",
    "mani": "mantequilla-de-mani",
    "nueces": "nueces-mariposa",
    "papas": "papas",
    "platano": "platano",
    "zanahoria": "zanahoria-bolsa-del-valle",
    "brocoli": "brocoli-unidad",
    "manzana": "manzana",
    "tomate": "tomate",
    "lechuga": "lechuga",
    "cebolla": "cebollas-a-granel",
    "palta": "palta-hass",
}

# ---------------------------------------------------------------- lectores por cadena
# Cada uno devuelve una lista de productos: dict(n=nombre, p=precio, img, u=url, size=texto de tamaño,
# ppu=(precio, unidad) por kg/L si la cadena lo informa, stock=bool, steps=[[desde, precio_unitario], ...])

def ld_lists(t):
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            j = json.loads(html.unescape(m.group(1)))
        except Exception:
            continue
        for x in (j if isinstance(j, list) else [j]):
            if isinstance(x, dict) and x.get("@type") == "ItemList":
                out.append(x)
    return out


def jumbo_like(base, q, page=1):
    st, t = get(f"{base}/busqueda?ft={quote(q)}" + (f"&page={page}" if page > 1 else ""))
    if st != 200:
        return None, f"http {st}"
    if BLOQUEO.search(t[:20000]) and "ItemList" not in t:
        return None, "bloqueado"
    # Datos extra (precio por kg/L y stock) en el contenido de la página.
    raw = t.replace('\\"', '"')
    extra = {}
    for m in re.finditer(r'"price":(\d+),"listPrice":(\d+),"ppumPrice":(\d+(?:\.\d+)?),"ppumListPrice":[\d.]+,"ppumConversion":[\d.]+,'
                         r'"ppumMeasurementUnit":"(\w*)","images":\["([^"]+)"[^\]]*\],"name":"([^"]+)","stock":(true|false)', raw):
        extra[m.group(6)] = dict(ppu=(float(m.group(3)), norm(m.group(4))), stock=m.group(7) == "true")
    items = []
    for L in ld_lists(t):
        for el in L.get("itemListElement", []):
            it = el.get("item") or {}
            off = it.get("offers") or {}
            off = off[0] if isinstance(off, list) and off else off
            name = it.get("name") or el.get("name") or ""
            x = extra.get(name, {})
            items.append(dict(n=name, p=num(off.get("price")), img=it.get("image"), u=it.get("url"), size=name,
                              ppu=x.get("ppu"), stock=x.get("stock", "InStock" in str(off.get("availability", "InStock")))))
    return items, "ok" if items else "sin resultados"


def lider_nombre_valido(pid, nombre):
    """Exige el producto correcto, no solo una palabra en un producto relacionado."""
    t = norm(nombre)
    required = {
        "salmon": [r"\bsalmon\b", r"\bfilete\b"],
        "quinoa": [r"^\s*quinoa\b"],
        "oliva": [r"\baceite\s+(?:de\s+)?oliva\b", r"\bextra\s+virgen\b"],
        "arroz": [r"\bgrado\s*2\b"],
        "avena": [r"\btradicional\b"],
        "molida": [r"\b10\s*%\s*grasa\b"],
        "pechuga": [r"\bdeshuesad"],
        "trutro": [r"\bentero\b"],
        "lechuga": [r"\blechuga\b", r"\b1\s*un\b"],
        "papas": [r"\bpapas?\s+malla\b", r"\b2\s*kg\b"],
        "nueces": [r"\bmariposas?\b"],
    }
    if pid == "fideos" and re.search(r"\bmix\b|\btricolor\b", t):
        return False
    return all(re.search(r, t) for r in required.get(pid, []))


def lider_categoria(pid):
    """Lee productos del ItemList público de una categoría de Líder.

    Se limita a las rutas conocidas; si una página rechaza acceso no hace reintentos.
    """
    slug = LIDER_CATEGORIAS.get(pid)
    if not slug:
        return [], "sin fuente"
    base = "https://super.lider.cl"
    st, contenido = get(f"{base}/v/{slug}")
    if st != 200:
        return None, f"http {st}"
    listas = ld_lists(contenido)
    if not listas:
        return None, "bloqueado" if BLOQUEO.search(contenido[:20000]) else "sin datos"
    items = []
    for lista in listas:
        for elemento in lista.get("itemListElement", []):
            if not isinstance(elemento, dict):
                continue
            producto = elemento.get("item") or {}
            if not isinstance(producto, dict):
                continue
            ofertas = producto.get("offers") or {}
            if isinstance(ofertas, list):
                ofertas = ofertas[0] if ofertas else {}
            if not isinstance(ofertas, dict):
                continue
            p = num(ofertas.get("price"))
            if not p or p <= 0 or p > 1000000:
                continue
            nombre = producto.get("name") or elemento.get("name") or ""
            if not isinstance(nombre, str) or not nombre:
                continue
            # El catálogo excluye alimentos que no empiezan por su tipo:
            # quitar solo los prefijos conocidos de supermercados, no palabras arbitrarias.
            if CAT[pid].get("start"):
                nombre = re.sub(r"^(?:multi ?marca|lider)\s+", "", nombre, flags=re.I)
            if not lider_nombre_valido(pid, nombre):
                continue
            if pid == "lechuga":
                # Una lechuga entera en bolsa no es lo mismo que hojas/ensalada envasadas.
                nombre = re.sub(r"\bBolsa\s+(?=1\s*Un\b)", "", nombre, flags=re.I)
            # Evitar comparar el precio unitario de un envase muy distinto al
            # que la app considera una unidad de compra.
            if pid in ("salmon", "fideos", "yogurt"):
                tam = size_of(nombre)
                rangos = {"salmon": (400, 600), "fideos": (350, 550), "yogurt": (750, 1200)}
                lo, hi = rangos[pid]
                if not tam or tam[1] != "g" or not (lo <= tam[0] <= hi):
                    continue
            foto = producto.get("image")
            if isinstance(foto, list):
                foto = foto[0] if foto else None
            if isinstance(foto, dict):
                foto = foto.get("url")
            url = producto.get("url")
            if isinstance(url, str) and url.startswith("/"):
                url = base + url
            # En Lider lo que se vende a granel muestra el precio por kilo aunque el nombre diga "500 g".
            granel = bool(re.search(r"\bgranel\b", norm(nombre)))
            items.append(dict(n=nombre, p=p, img=foto, u=url or f"{base}/v/{slug}",
                              size="granel" if granel else nombre, ppu=(p, "kg") if granel else None,
                              stock="OutOfStock" not in str(ofertas.get("availability", ""))))
    return items, "ok" if items else "sin resultados"


def next_data(t):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def walk(o, pred, out):
    if isinstance(o, dict):
        if pred(o):
            out.append(o)
            return
        for v in o.values():
            walk(v, pred, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, pred, out)


def smu_item(d, base):
    sel = (d.get("sellers") or [{}])[0] or {}
    p = num(sel.get("price"))
    steps = []
    for s in d.get("priceSteps") or []:
        if num(s.get("promotionalPrice")) and s.get("minQuantity"):
            steps.append([int(s["minQuantity"]), num(s["promotionalPrice"])])
    name = d.get("nameComplete") or d.get("name") or ""
    size = " ".join(str(x) for x in [name, d.get("netContent") or "", d.get("format") or ""])
    img = (d.get("images") or [None])[0]
    return dict(n=name, p=p, img=img, u=base + (d.get("detailUrl") or ""), size=size, steps=steps,
                stock=(sel.get("availableQuantity", 1) or 0) > 0)


def alvi(q):
    st, t = get(f"https://www.alvi.cl/search?q={quote(q)}")
    if st != 200:
        return None, f"http {st}"
    d = next_data(t)
    if not d:
        return None, "bloqueado" if BLOQUEO.search(t[:20000]) else "sin datos"
    found = []
    walk(d, lambda o: "sellers" in o and ("nameComplete" in o or "name" in o) and "detailUrl" in o, found)
    items = [smu_item(x, "https://www.alvi.cl") for x in found]
    items = [x for x in items if x["p"]]
    return items, "ok" if items else "sin resultados"


UNI_CACHE = {}


def unimarc_cat(cat):
    if cat in UNI_CACHE:
        return UNI_CACHE[cat]
    items, estado = [], "ok"
    for page in (1, 2, 3):
        st, t = get(f"https://www.unimarc.cl/category/{cat}" + (f"?page={page}" if page > 1 else ""))
        if st != 200:
            estado = f"http {st}"
            break
        d = next_data(t)
        if not d:
            estado = "bloqueado" if BLOQUEO.search(t[:20000]) else "sin datos"
            break
        found = []
        walk(d, lambda o: "sellers" in o and "nameComplete" in o and "detailUrl" in o, found)
        new = [smu_item(x, "https://www.unimarc.cl") for x in found]
        new = [x for x in new if x["p"]]
        items += new
        if len(new) < 40:
            break
    UNI_CACHE[cat] = (items, estado)
    return items, estado


def unimarc(spec):
    items, estado = [], "sin datos"
    for c in spec.get("uni", []):
        it, e = unimarc_cat(c)
        items += it
        estado = e if not items else "ok"
    return items, estado


def lider(q):
    st, t = get(f"https://super.lider.cl/search?q={quote(q)}")
    if st != 200:
        return None, f"http {st}"
    d = next_data(t)
    if not d:
        return None, "bloqueado" if BLOQUEO.search(t[:30000]) else "sin datos"
    found = []
    walk(d, lambda o: "usItemId" in o and "priceInfo" in o and "name" in o, found)
    items = []
    for x in found:
        pi = x.get("priceInfo") or {}
        p = num(pi.get("linePrice") or pi.get("itemPrice"))
        if not p:
            continue
        ppu = None
        m = re.match(r"\$?([\d.]+)\s*x\s*(\w+)", str(pi.get("unitPrice") or ""))
        if m:
            ppu = (num(m.group(1)), norm(m.group(2)))
        img = (x.get("imageInfo") or {}).get("thumbnailUrl")
        url = x.get("canonicalUrl") or ""
        av = str((x.get("availabilityStatusV2") or {}).get("value") or x.get("availabilityStatus") or "IN_STOCK")
        items.append(dict(n=x.get("name") or "", p=p, img=img, u=("https://super.lider.cl" + url) if url.startswith("/") else url,
                          size=x.get("name") or "", ppu=ppu, stock="OUT" not in av.upper()))
    return items, "ok" if items else "sin resultados"


# ---------------------------------------------------------------- elegir el producto
def precio_norm(it, spec):
    """Precio llevado al tamaño de referencia del catálogo (pkg)."""
    kind, pkg = spec["kind"], spec["pkg"]
    sz = size_of(it["size"])
    ppu = it.get("ppu")
    if kind in ("g", "ml"):
        if not sz or sz[1] != kind:
            return None, None
        q = sz[0]
        lo, hi = spec.get("lo", 0.5), spec.get("hi", 2.6)
        if not (pkg * lo <= q <= pkg * hi):
            return None, None
        return it["p"] / q * pkg, q
    if kind == "kg":
        if sz and sz[1] == "g" and sz[0] < 200:
            return None, None
        if sz and sz[1] == "g":
            return it["p"] / sz[0] * pkg, sz[0]
        if ppu and ppu[1] in ("kg", "kilo", "kgs"):
            return ppu[0] * pkg / 1000, None
        if re.search(r"granel|por kg|x kg|kilo", norm(it["n"])):
            return it["p"] * pkg / 1000, None
        return None, None
    if kind == "un":
        if spec["pkg"] == 1:  # lechuga, brócoli: por unidad
            if sz and sz[1] == "un" and sz[0] > 1:
                return it["p"] / sz[0], 1
            if sz and sz[1] == "g" and sz[0] >= 1000:
                return None, None
            return it["p"], 1
        if sz and sz[1] == "un" and 6 <= sz[0] <= 60:
            return it["p"] / sz[0] * pkg, sz[0]
        return None, None
    if kind == "lata":
        if sz and sz[1] == "g" and 100 <= sz[0] / max(1, sz[2]) <= 200:
            return it["p"] / max(1, sz[2]), sz[0]
        return None, None
    return None, None


# Opción premium para el plan Holgada: lo que la app muestra como "marca premium". Si hay productos que calzan
# con la descripción, se toma el más barato de ellos; si no, uno de marca en el cuarto más caro de los encontrados.
PREMIUM = {
    "huevo": r"libre|campo|pastoreo|organic|omega|free",
    "leche": r"sin lactosa|protein|proteina",
    "yogurt": r"protein|proteina|0 ?%|oikos|skyr",
    "pechuga": r"filetito|filete|file",
    "molida": r"\b[3-7] ?%",
    "atun": r"premium|aceite de oliva|ventresca|seleccion|gourmet",
    "avena": r"integral|organica|premium|instantanea|quaker",
    "arroz": r"grado ?1|premium|basmati|jazmin|pregraneado",
    "fideos": r"barilla|de cecco|italian|bronce|semola|garofalo",
    "quinoa": r"organic|tricolor|real",
    "pan": r"semilla|multigrano|masa madre|chia|linaza|centeno",
    "oliva": r"premium|reserva|gourmet|primera|seleccion|organic",
    "mani": r"100 ?%|natural|sin azucar|crunchy",
}


def elegir(items, spec):
    cands = []
    for it in items or []:
        if not it.get("p") or not it.get("stock", True):
            continue
        n = norm(it["n"])
        if not all(re.search(r, n) for r in spec["inc"]):
            continue
        if any(re.search(r, n) for r in spec.get("exc", [])):
            continue
        if spec.get("start") and not re.match(r"\s*(?:" + spec["inc"][0] + ")", n):
            continue  # frutas, verduras y nueces: el nombre tiene que partir con el producto ("Papa malla", no "Sufles de papa")
        pn, q = precio_norm(it, spec)
        if not pn or pn <= 0:
            continue
        cands.append(dict(it, pn=pn))
    if not cands:
        return None
    med = median(c["pn"] for c in cands)
    cands = [c for c in cands if med / 3 <= c["pn"] <= med * 3] or cands
    cands.sort(key=lambda c: c["pn"])
    eco = cands[0]
    if spec.get("brand"):
        br = [c for c in cands if spec["brand"] in norm(c["n"])]
    else:
        br = [c for c in cands if not MARCA_PROPIA.search(norm(c["n"]))]
    eq = br[0] if br else eco
    pre = None
    pid = spec.get("_pid")
    if pid in PREMIUM:
        hits = [c for c in cands if re.search(PREMIUM[pid], norm(c["n"])) and not MARCA_PROPIA.search(norm(c["n"]))]
        if hits:
            pre = hits[0]
        elif br:
            pre = br[min(len(br) - 1, (len(br) * 3) // 4)]

    def out(c):
        o = dict(p=round(c["pn"]), n=c["n"][:90], img=c.get("img"), u=c.get("u"), pv=round(c["p"]))
        if c.get("steps"):
            o["t"] = [[s[0], round(s[1] * c["pn"] / c["p"])] for s in c["steps"]]
        return o
    r = dict(eq=out(eq), eco=out(eco), n=len(cands))
    if pre is not None:
        r["pre"] = out(pre)
    return r


# ---------------------------------------------------------------- principal
def cache_vigente(fecha, ahora):
    """No reutilizar precios que lleven más de siete días sin verificarse."""
    try:
        anterior = datetime.fromisoformat(fecha).replace(tzinfo=ahora.tzinfo)
        edad = ahora - anterior
        return timedelta(0) <= edad <= timedelta(days=7)
    except (ValueError, TypeError):
        return False


def main():
    from zoneinfo import ZoneInfo
    ahora = datetime.now(ZoneInfo("America/Santiago"))
    capturado_hoy = ahora.strftime("%Y-%m-%d %H:%M")
    try:
        with open("precios.json", encoding="utf-8") as f:
            anterior = json.load(f)
    except (OSError, ValueError):
        anterior = {}
    cadenas = CADENAS_ACTIVAS
    estado = {k: {} for k in cadenas}
    res = {pid: {} for pid in CAT}
    # Conservar el último dato verificado durante 7 días, sin llamarlo precio de hoy.
    for pid, por_cadena in anterior.get("p", {}).items():
        if pid not in res or not isinstance(por_cadena, dict):
            continue
        for ci, precio in por_cadena.items():
            if ci not in {str(k) for k in cadenas} or not isinstance(precio, dict):
                continue
            fecha_origen = precio.get("capturado") or anterior.get("fecha")
            if (cache_vigente(fecha_origen, ahora)
                    and (precio.get("eq") or {}).get("p", 0) > 0):
                res[pid][ci] = {**precio, "capturado": fecha_origen}
    from contextlib import ExitStack
    navegadores = ExitStack()
    uni_navegador = None
    solo = sys.argv[1:]  # opcional: limitar a algunos productos para probar
    for pid, spec in CAT.items():
        if solo and pid not in solo:
            continue
        for ci in cadenas:
            if ci in cadenas_bloq:
                continue
            if ci == 0:
                items, e = lider_categoria(pid)
            elif ci == 1:
                try:
                    if uni_navegador is None:
                        from unimarc_browser import UnimarcBrowser, UNIMARC_BUSQUEDAS, filtrar_unimarc
                        uni_navegador = navegadores.enter_context(UnimarcBrowser())
                    items, e = uni_navegador.consultar(UNIMARC_BUSQUEDAS.get(pid, spec["q"]))
                    items = filtrar_unimarc(pid, items)
                except Exception as err:
                    items, e = None, "error navegador"
                    log("   Unimarc: fallo al iniciar Chromium:", type(err).__name__)
            elif ci in (2, 3):
                base = "https://www.jumbo.cl" if ci == 2 else "https://www.santaisabel.cl"
                items, e = jumbo_like(base, spec["q"])
                # La primera página a veces trae solo envases chicos (huevos de 6 o 12, carne de 250 g), que salen
                # más caros por kilo; en la segunda suelen aparecer los envases grandes. Se suman sin repetir.
                if e == "ok":
                    it2, e2 = jumbo_like(base, spec["q"], page=2)
                    if it2:
                        vistos = {i["n"] for i in items}
                        nuevos = [i for i in it2 if i["n"] not in vistos]
                        items = items + nuevos
                        if nuevos:
                            log(f"   {cadenas[ci]} {pid}: +{len(nuevos)} de la página 2")
                # Si la búsqueda trae pocos resultados (Santa Isabel a veces trae 3 a 7), se prueba una búsqueda más amplia:
                # "huevos 30 unidades" pasa a "huevos"; "pechuga de pollo deshuesada" a "pechuga de pollo".
                corta = " ".join([w for w in spec["q"].split() if not re.search(r"\d", w) and w not in ("unidades", "un")][:3])
                if e == "ok" and len(items) < 10 and corta and corta != spec["q"]:
                    it3, e3 = jumbo_like(base, corta)
                    if it3:
                        vistos = {i["n"] for i in items}
                        nuevos = [i for i in it3 if i["n"] not in vistos]
                        items = items + nuevos
                        if nuevos:
                            log(f"   {cadenas[ci]} {pid}: +{len(nuevos)} buscando '{corta}'")
            else:
                items, e = alvi(spec["q"])
            estado[ci][e] = estado[ci].get(e, 0) + 1
            pick = elegir(items, spec) if items else None
            if not pick and spec.get("q2") and ci not in (0, 1) and not es_bloqueo(e):
                s2 = dict(spec, q=spec["q2"])
                it2, e2 = (lider(s2["q"]) if ci == 0 else jumbo_like("https://www.jumbo.cl", s2["q"]) if ci == 2 else
                           jumbo_like("https://www.santaisabel.cl", s2["q"]) if ci == 3 else alvi(s2["q"]))
                pick = elegir(it2, spec) if it2 else None
                if pick:
                    items = it2
            if items and not pick:
                log(f"   sin calce en {cadenas[ci]} para {pid}; leídos: " + " · ".join(f"{i['n'][:40]} ${int(i['p'] or 0):,}{'' if i.get('stock', True) else ' (sin stock)'}" for i in items[:8]))
            if pick:
                res[pid][str(ci)] = {**pick, "capturado": capturado_hoy, **({"fuente": "categoria_publica"} if ci == 0 else {"fuente": "pagina_publica_chromium"} if ci == 1 else {})}
            if pick and spec["kind"] == "kg":
                hit = next((i for i in items if i["n"] == pick["eq"]["n"][:90] or i["n"].startswith(pick["eq"]["n"][:60])), {})
                log(f"   (granel: precio de lista ${pick['eq']['pv']:,}, precio por kg informado: {hit.get('ppu')})")
            log(f"{pid:10s} {cadenas[ci]:8s} {e:14s} {len(items or []):3d} leídos  ",
                (f"eq ${pick['eq']['p']:,} {pick['eq']['n'][:45]} | eco ${pick['eco']['p']:,} {pick['eco']['n'][:35]}" if pick else "—"))
            if es_bloqueo(e) or (ci == 1 and e in ("timeout", "error lectura", "error navegador")):
                # No repetir en el mismo día una cadena que falló o denegó acceso.
                cadenas_bloq.add(ci)
                log(f"   {cadenas[ci]}: lectura no disponible; no se harán más consultas hoy")
    navegadores.close()
    data = dict(fecha=capturado_hoy,
                estado={cadenas[k]: v for k, v in estado.items()},
                p={k: v for k, v in res.items() if v})
    with open("precios.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open("registro.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(LOG) + "\n")
    tot = sum(len(v) for v in res.values())
    log(f"\nListo: {tot} precios de {len([v for v in res.values() if v])} productos.")


cadenas_bloq = set()

if __name__ == "__main__":
    main()
