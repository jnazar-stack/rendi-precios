"""Prueba del catálogo completo de Unimarc sin modificar los datos publicados."""
import json
from actualizar import CAT, elegir, es_bloqueo
from unimarc_browser import UnimarcBrowser, UNIMARC_BUSQUEDAS

def main():
    encontrados = 0
    intentados = 0
    with UnimarcBrowser() as navegador:
        for pid, spec in CAT.items():
            query = UNIMARC_BUSQUEDAS.get(pid, spec["q"])
            productos, estado = navegador.consultar(query)
            pick = elegir(productos, spec) if productos else None
            if pick:
                encontrados += 1
            intentados += 1
            print(json.dumps({
                "producto": pid, "consulta": query, "estado": estado,
                "leidos":len(productos or []), "validos":(pick or {}).get("n",0),
                "nombre": (pick or {}).get("eq",{}).get("n"),
                "precio_normalizado":(pick or {}).get("eq",{}).get("p")
            },ensure_ascii=False),flush=True)
            if es_bloqueo(estado):
                print("Prueba detenida por restricción de acceso.",flush=True)
                break
    print(json.dumps({"revisados":intentados,"validos":encontrados,"total_catalogo":len(CAT)}),flush=True)
    if encontrados < 17:
        raise SystemExit("Cobertura insuficiente: no publicar todavía el lector")

if __name__ == "__main__":
    main()
