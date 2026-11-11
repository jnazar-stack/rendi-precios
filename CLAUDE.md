# rendi-precios

Lector diario de precios y catálogo de supermercados chilenos para la app Rendi. La guía completa del proyecto (cómo trabajar con Jorge, la app, Supabase, compilación) está en `CLAUDE.md` del repo `jnazar-stack/rendi-app`.

- `actualizar.py` → `precios.json` (workflow `diario.yml`): precio del día de cada alimento del plan en Jumbo, Santa Isabel, Lider, Unimarc y Alvi, con niveles económica/equilibrada/holgada.
- `catalogo.py` → `catalogo.json` (workflow `catalogo.yml`): ~11.000 productos de comida unidos por código de barras, con tabla nutricional por 100 g y porción (`nu`, `nu.sv`) leídas de páginas de Jumbo/Santa Isabel (`nutri_vtex.json`, `ean_vtex.json`). También busca los códigos que escanean los usuarios (tabla `codigos` en Supabase).
- `suplementos.py` → `suplementos.json` (workflow `suplementos.yml`): suplementos de Allnutrition, Supletech, Jumbo y Lider con costo por g de proteína y por dosis de creatina.
- Reglas: ritmo pausado, sin saltar protecciones anti-bot ni resolver CAPTCHAs; si una cadena niega el acceso, se sigue al día siguiente. Nada se consulta desde los teléfonos.
- Los registros de Actions no se pueden bajar desde la nube: para diagnosticar, escribir la salida a un archivo y subirlo.
- Los cron están en UTC y GitHub los atrasa varias horas.
