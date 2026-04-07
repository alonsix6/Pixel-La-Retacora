# Pixel La Retacora

Sistema de tracking pixel para artículos y páginas en Notion. Inserta un pixel invisible en tus artículos y obtén analytics detallados: visitas, países, dispositivos, navegadores, y más — todo separado por artículo.

## Cómo funciona

1. Despliega el backend en Railway
2. Copia la URL del pixel desde el dashboard
3. Inserta el pixel como imagen embebida en tu artículo de Notion
4. Cada vez que alguien abre el artículo, el pixel registra la visita
5. Visualiza todo en el dashboard en tiempo real

## Stack

- **Backend:** FastAPI + SQLite
- **Frontend:** Dashboard HTML/CSS/JS vanilla
- **Deploy:** Railway
- **Geolocalización:** ip-api.com (free tier)

## Deploy en Railway

1. Crea un proyecto en [Railway](https://railway.app)
2. Conecta este repositorio de GitHub
3. Railway detectará automáticamente el `Procfile` y `runtime.txt`
4. Agrega un volumen persistente montado en `/data` (para la base de datos)
5. Configura la variable de entorno `DASHBOARD_TOKEN` con un token secreto
6. Despliega y obtén tu URL pública (ej: `https://pixel-la-retacora.up.railway.app`)

## Insertar pixel en Notion

1. Ve al dashboard: `https://TU-URL/dashboard?token=TU_TOKEN`
2. Copia la URL del pixel de la sección inferior
3. Cambia `mi-articulo` por un nombre único para tu artículo:
   - `https://TU-URL/pixel?pagina=guia-seo`
   - `https://TU-URL/pixel?pagina=tutorial-python`
   - `https://TU-URL/pixel?pagina=landing-page`
4. En Notion, escribe `/image` → selecciona "Enlace" → pega la URL
5. Minimiza el bloque de imagen (es un 1x1 px transparente, casi invisible)

**Importante:** Usa un nombre diferente en `?pagina=` para cada artículo. Así el dashboard separa las visitas por artículo.

## API Endpoints

| Endpoint | Auth | Descripción |
|----------|------|-------------|
| `GET /pixel?pagina=nombre` | No | Registra visita y retorna pixel GIF 1x1 |
| `GET /stats?pagina=X&range=7d` | Sí | Métricas agregadas (JSON) |
| `GET /pages` | Sí | Lista de artículos con conteo de visitas |
| `GET /recent?pagina=X` | Sí | Últimas 20 visitas |
| `GET /dashboard` | Sí | Dashboard web |
| `GET /health` | No | Health check |

Los endpoints con auth requieren `?token=TU_TOKEN` (configurado via `DASHBOARD_TOKEN`).

El parámetro `range` acepta: `hoy`, `7d`, `30d`, `todo`.

## Desarrollo local

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Dashboard: http://localhost:8000/dashboard

## Limitaciones

- **Cache de Notion:** Notion puede cachear el pixel. Cada sesión nueva registra visita, pero visitas repetidas en la misma sesión podrían no registrarse.
- **IP proxy:** Cuando Notion pre-renderiza la página, la IP puede ser de servidores de Notion, no del visitante real.
