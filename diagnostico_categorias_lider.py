"""Comprueba una vez cada URL pública de Líder antes de activar producción."""
import json
import actualizar as a

def main():
    summary={}
    for pid in a.LIDER_CATEGORIAS:
        items,status=a.lider_categoria(pid)
        pick=a.elegir(items,a.CAT[pid]) if items else None
        summary[pid]={"estado":status,"items":len(items or []),"valido":bool(pick),
            "precio":(pick or {}).get("eq",{}).get("p")}
        print(json.dumps({"producto":pid,**summary[pid]},ensure_ascii=False),flush=True)
        if a.es_bloqueo(status):
            print("Se detiene la prueba ante denegación de acceso.",flush=True)
            break
    ok=[pid for pid,s in summary.items() if s["valido"]]
    print(json.dumps({"revisados":len(summary),"validos":len(ok),"productos":ok},ensure_ascii=False),flush=True)
    if len(ok)<7:
        raise SystemExit("Cobertura insuficiente para activar esta versión")

if __name__=="__main__":
    main()
