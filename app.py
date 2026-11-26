"""
🎄 Calendario de Adviento personalizado (Streamlit)
===================================================
- La lógica vive aquí; el CONTENIDO se edita solo en `adviento.json`.
- Bloqueo por fecha real en zona horaria Europe/Madrid.
- Puertas desordenadas y de distintos tamaños, como un calendario de cartón.
- Modo prueba oculto en la barra lateral, protegido con contraseña.

Ejecutar en local:  streamlit run app.py
"""
import base64
import io
import json
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

import estado  # guarda qué días se han abierto (estado.py)

# ----------------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------------
BASE = Path(__file__).parent
ARCHIVO_CONTENIDO = BASE / "adviento.json"
ZONA = ZoneInfo("Europe/Madrid")

# Contraseña del modo prueba. Mejor definirla en los "Secrets" de Streamlit
# Cloud (clave TEST_PASSWORD); si no existe, se usa esta de reserva.
PASSWORD_RESERVA = "cambiame"

# Disposición FIJA y desordenada: cada fila es una lista de
# (día, anchura relativa, altura en px). Cambia números/tamaños a tu gusto,
# pero deben aparecer los 24 días una sola vez.
DISPOSICION = [
    [(7, 2, 110), (19, 1, 130), (3, 2, 100)],
    [(12, 1, 120), (21, 2, 140), (1, 1, 100), (15, 1, 130)],
    [(9, 2, 100), (4, 1, 140), (22, 2, 110)],
    [(17, 1, 130), (10, 2, 110), (6, 1, 100), (13, 2, 130)],
    [(2, 2, 140), (18, 1, 110), (11, 2, 100)],
    [(20, 1, 110), (8, 2, 130), (14, 1, 100), (23, 2, 120)],
    [(5, 1, 190), (24, 3, 190), (16, 1, 190)],  # ¡el 24, grande y central!
]

# Tamaño máximo (px) de las imágenes dentro de la ventana de cada día
IMG_MAX_ANCHO, IMG_MAX_ALTO = 620, 520

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

st.set_page_config(page_title="Calendario de Adviento", page_icon="🎄",
                   layout="centered", initial_sidebar_state="collapsed")


# ----------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------
def cargar_contenido() -> dict:
    """Lee adviento.json (sin caché, así los cambios se ven al recargar)."""
    try:
        return json.loads(ARCHIVO_CONTENIDO.read_text(encoding="utf-8"))
    except Exception as e:  # JSON mal escrito, archivo ausente...
        st.error(f"No pude leer adviento.json: {e}")
        return {"config": {}, "dias": {}}


def hoy_madrid():
    return datetime.now(ZONA).date()


def anio_calendario(hoy) -> int:
    """En enero el calendario sigue abierto (usa el diciembre anterior)."""
    return hoy.year - 1 if hoy.month == 1 else hoy.year


def esta_disponible(dia: int, hoy, anio: int, forzar: bool) -> bool:
    if forzar:
        return True
    return hoy >= hoy.replace(year=anio, month=12, day=dia)


def password_correcta(introducida: str) -> bool:
    try:
        real = st.secrets.get("TEST_PASSWORD", PASSWORD_RESERVA)
    except Exception:  # no hay secrets.toml en local
        real = PASSWORD_RESERVA
    return introducida == real


def ruta_media(valor: str) -> str:
    """URL tal cual; si es una ruta local, la resuelve respecto a la app."""
    return valor if valor.startswith("http") else str(BASE / valor)


def mostrar_enlace(item):
    """Acepta una URL o {"texto": "...", "url": "..."}. Si está vacío, se ignora."""
    if isinstance(item, dict):
        url, texto = item.get("url", ""), item.get("texto", "Abrir enlace")
    else:
        url, texto = item, "Abrir enlace"
    if not url.startswith("http"):
        return
    if isinstance(item, dict):  # con "texto" -> siempre un botón que abre el enlace
        st.link_button(texto, url, use_container_width=True)
    elif "spotify.com" in url and "/embed" not in url:
        embed = url.split("?")[0].replace("open.spotify.com/", "open.spotify.com/embed/")
        components.iframe(embed, height=152)
    elif any(x in url for x in ("youtu", "vimeo", ".mp4")):
        st.video(url)
    else:
        st.link_button(texto, url, use_container_width=True)


def resolver_imagen(v: str):
    """Devuelve la ruta/URL de la imagen; si falta, prueba otras extensiones."""
    if v.startswith("http"):
        return v
    ruta = Path(ruta_media(v))
    for cand in [ruta] + [ruta.with_suffix(e) for e in (".png", ".jpg", ".jpeg", ".webp")]:
        if cand.exists():
            return str(cand)
    return None


@st.cache_data(show_spinner=False)
def imagen_html(ruta: str, mtime: float, max_w: int, max_h: int) -> str:
    """Imagen local -> HTML centrado, con rotación corregida y peso reducido."""
    img = ImageOps.exif_transpose(Image.open(ruta))
    if img.mode in ("RGBA", "LA", "P"):  # fondo blanco si hay transparencias
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        img = fondo
    img = img.convert("RGB")
    w, h = img.size
    ancho = int(min(w, max_w, max_h * w / h))
    img.thumbnail((ancho * 2, 4000))  # el doble de resolución para pantallas nítidas
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return caja_imagen(f"data:image/jpeg;base64,{b64}", ancho)


def caja_imagen(src: str, ancho: int) -> str:
    """HTML que centra la imagen y limita su tamaño."""
    return (f'<div style="text-align:center;margin:.6rem 0">'
            f'<img src="{src}" style="width:{ancho}px;max-width:100%;height:auto;'
            f'border-radius:12px"></div>')


def mostrar_imagenes(valor):
    """Una imagen (str) o varias (lista, en 2 columnas), centradas y con tamaño
    controlado. Las imágenes que aún no existan se omiten."""
    lista = [v for v in ([valor] if isinstance(valor, str) else list(valor or [])) if v]
    multi = len(lista) > 1
    max_w, max_h = (300, 300) if multi else (IMG_MAX_ANCHO, IMG_MAX_ALTO)
    cols = st.columns(2) if multi else [st.container()]
    for i, v in enumerate(lista):
        with cols[i % len(cols)]:
            ruta = resolver_imagen(v)
            if not ruta:
                if st.session_state.get("auth"):  # solo lo ves tú, con sesión privada
                    st.caption(f"Falta la imagen: {v}")
            elif ruta.startswith("http"):
                st.markdown(caja_imagen(ruta, max_w), unsafe_allow_html=True)
            else:
                st.markdown(imagen_html(ruta, Path(ruta).stat().st_mtime, max_w, max_h),
                            unsafe_allow_html=True)


def norm(s: str) -> str:
    """Minúsculas y sin tildes, para comparar respuestas."""
    s = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ----------------------------------------------------------------------------
# ESTILOS
# ----------------------------------------------------------------------------
CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Great+Vibes&family=Playfair+Display:ital,wght@0,500;1,400&display=swap');

.stApp {
  background: radial-gradient(ellipse at top, #5c1a2b 0%, #2b0a14 70%) fixed;
}
.block-container { max-width: 900px; padding-top: 2rem; }
h1.titulo {
  font-family: 'Great Vibes', cursive; font-size: 3.6rem; text-align: center;
  color: #f4d58d; margin: 0; text-shadow: 0 0 18px rgba(244,213,141,.45);
}
p.subtitulo {
  font-family: 'Playfair Display', serif; font-style: italic; text-align: center;
  color: #f1d9d9; font-size: 1.15rem; margin: .2rem 0 1.4rem;
}
p.aviso { text-align:center; color:#e8c7a0; font-family:'Playfair Display',serif; }

/* Mantener las columnas en horizontal también en móvil */
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .5rem !important; }
div[data-testid="stColumn"], div[data-testid="column"] { min-width: 0 !important; }

/* Imágenes centradas y con esquinas suaves */
div[data-testid="stImage"] { display: flex; justify-content: center; }
div[data-testid="stImage"] img { max-width: 100%; height: auto; border-radius: 12px; }

/* Puertas (base común) */
div[class*="st-key-puerta_"] button {
  width: 100%; border-radius: 14px; border: 2px solid #f4d58d;
  transition: transform .15s, box-shadow .15s;
}
div[class*="st-key-puerta_"] button p {
  font-family: 'Great Vibes', cursive; font-size: 2.4rem; line-height: 1;
}
div[class*="st-key-puerta_"] button:hover { transform: scale(1.04) rotate(-1deg); }
</style>
"""

# Plantilla por puerta: __D__ = día, __H__ = altura, __ESTADO__ = reglas de color
PLANTILLAS = {
    "bloqueada": """background: linear-gradient(145deg,#3a1220,#240a14);
        color: #b79a6b; border-color: #6b4a3a; opacity: .85;""",
    "disponible": """background: linear-gradient(145deg,#f4d58d,#d9a441);
        color: #5c1a2b; box-shadow: 0 0 18px rgba(244,213,141,.6);""",
    "abierta": """background: linear-gradient(145deg,#2f6b4f,#184032);
        color: #f4d58d; border-color: #9ccfae;""",
}


def css_puertas(estados: dict, alturas: dict) -> str:
    reglas = ""
    for d, estado in estados.items():
        extra = "font-size: 3.4rem;" if d == 24 else ""
        reglas += (f'.st-key-puerta_{d} button {{ height: {alturas[d]}px; '
                   f'{PLANTILLAS[estado]} }}\n'
                   f'.st-key-puerta_{d} button p {{ {extra} }}\n')
    return f"<style>{reglas}</style>"


# ----------------------------------------------------------------------------
# VISTA DE UN DÍA ABIERTO (ventana emergente)
# ----------------------------------------------------------------------------
def render_quiz(d: int, quiz: list, premio: dict):
    """Test de preguntas: si acierta todas, se enseña el premio."""
    resp = [st.radio(q["pregunta"], q["opciones"], index=None, key=f"quiz_{d}_{i}")
            for i, q in enumerate(quiz)]
    if st.button("Comprobar", key=f"quiz_ok_{d}"):
        if None in resp:
            st.warning("Contesta a todas, que no vale dejar ninguna")
        else:
            aciertos = sum(r == q["opciones"][q["correcta"]] for r, q in zip(resp, quiz))
            st.session_state[f"ganado_{d}"] = aciertos == len(quiz)
            if aciertos != len(quiz):
                st.error(f"{aciertos} de {len(quiz)}. ¡Casi! Prueba otra vez")
    if st.session_state.get(f"ganado_{d}"):
        st.success(premio.get("texto", "¡Premio!"))
        mostrar_imagenes(premio.get("imagen"))


def render_adivina(d: int, a: dict):
    """Adivinanza con emojis: acepta varias respuestas válidas."""
    if a.get("emojis"):
        st.markdown(f"<p style='font-size:3rem;text-align:center'>{a['emojis']}</p>",
                    unsafe_allow_html=True)
    r = st.text_input(a.get("pregunta", "¿Qué es?"), key=f"adv_{d}")
    if r:
        if any(norm(x) in norm(r) for x in a["respuestas"]):
            st.success(a["acierto"])
        else:
            st.error("Mmm… no es esa. ¡Sigue intentándolo!")


def render_revelar(d: int, r: dict):
    """Botón que, al pulsarlo, descubre una imagen."""
    if st.button(r.get("boton", "Pulsa aquí para saber más"), key=f"rev_{d}",
                 use_container_width=True):
        st.session_state[f"rev_ok_{d}"] = True
    if st.session_state.get(f"rev_ok_{d}"):
        mostrar_imagenes(r.get("imagen"))


def render_dia(d: int, c: dict):
    """Pinta el contenido definido en adviento.json para ese día."""
    if not c:
        st.info("Este día aún no tiene contenido… ¡se está preparando algo!")
        return
    if c.get("titulo"):
        st.markdown(f"<h2 style='font-family:Great Vibes,cursive;font-size:2.6rem;"
                    f"text-align:center;color:#d9a441;margin:0'>{c['titulo']}</h2>",
                    unsafe_allow_html=True)
    intro = c.get("intro")
    if intro and not st.session_state.get(f"intro_ok_{d}"):
        with st.container(border=True):
            st.markdown(intro["texto"])
        if st.button(intro.get("boton", "Empezar"), key=f"intro_{d}", use_container_width=True):
            st.session_state[f"intro_ok_{d}"] = True
            st.rerun(scope="fragment")
        return
    mostrar_imagenes(c.get("imagen"))
    if c.get("texto"):
        with st.container(border=True):
            st.markdown(c["texto"])
    if c.get("quiz"):
        render_quiz(d, c["quiz"], c.get("premio", {}))
    if c.get("adivina"):
        render_adivina(d, c["adivina"])
    for item in c.get("enlaces", []):
        mostrar_enlace(item)
    if c.get("reto"):
        st.info(f"**Reto del día:** {c['reto']}")
    if c.get("vale"):
        st.success(f"**Vale:** {c['vale']}")
    if c.get("revelar"):
        render_revelar(d, c["revelar"])
    if c.get("firma"):
        st.markdown(f"<p style='text-align:right;font-style:italic'>{c['firma']}</p>",
                    unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# APP
# ----------------------------------------------------------------------------
datos = cargar_contenido()
cfg, dias = datos.get("config", {}), datos.get("dias", {})
# Días abiertos de verdad (se cargan del JSON/GitHub y sobreviven a recargas y reinicios)
if "abiertas" not in st.session_state:
    st.session_state["abiertas"] = estado.cargar()
# Días abiertos solo durante el modo prueba (no se guardan)
st.session_state.setdefault("abiertas_prueba", set())

# --- Barra lateral: modo prueba (oculta y con contraseña) -------------------
forzar = False
with st.sidebar.expander("Zona privada"):
    if not st.session_state.get("auth"):
        pw = st.text_input("Contraseña", type="password")
        if pw:
            if password_correcta(pw):
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
    else:
        forzar = st.toggle("Modo prueba: abrir todos los días", value=False)
        st.caption(f"Días abiertos guardados: {sorted(st.session_state['abiertas']) or 'ninguno'}")
        if st.session_state.get("aviso_estado"):
            st.warning("No pude guardar en GitHub (revisa los Secrets). Se guardó solo en local.")
        if st.checkbox("Quiero reiniciar los días abiertos") and st.button("Reiniciar ahora"):
            estado.guardar(set(), reemplazar=True)
            st.session_state["abiertas"] = set()
            st.session_state["abiertas_prueba"] = set()
            st.rerun()
        if st.button("Cerrar sesión"):
            st.session_state["auth"] = False
            st.rerun()

# --- Cabecera ----------------------------------------------------------------
hoy = hoy_madrid()
anio = anio_calendario(hoy)
st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(f"<h1 class='titulo'>{cfg.get('titulo', 'Calendario de Adviento')}</h1>",
            unsafe_allow_html=True)
st.markdown(f"<p class='subtitulo'>{cfg.get('subtitulo', '')}</p>", unsafe_allow_html=True)

inicio = hoy.replace(year=anio, month=12, day=1)
if hoy < inicio:
    st.markdown(f"<p class='aviso'>Faltan {(inicio - hoy).days} días para la primera "
                f"puerta ✨</p>", unsafe_allow_html=True)
else:
    st.markdown(f"<p class='aviso'>Hoy es {hoy.day} de {MESES[hoy.month]} · "
                f"busca la puerta que toca.</p>", unsafe_allow_html=True)
if forzar:
    st.warning("Modo prueba activo: todas las puertas están abiertas.")

# --- Estados y estilos de cada puerta ---------------------------------------
alturas = {d: h for fila in DISPOSICION for d, _, h in fila}
estados = {}
for d in alturas:
    if not esta_disponible(d, hoy, anio, forzar):
        estados[d] = "bloqueada"
    elif d in st.session_state["abiertas"] or (forzar and d in st.session_state["abiertas_prueba"]):
        estados[d] = "abierta"
    else:
        estados[d] = "disponible"
st.markdown(css_puertas(estados, alturas), unsafe_allow_html=True)

# --- Tablero -------------------------------------------------------------------
for fila in DISPOSICION:
    columnas = st.columns([peso for _, peso, _ in fila])
    for col, (d, _, _) in zip(columnas, fila):
        with col:
            etiqueta = f"🔒 {d}" if estados[d] == "bloqueada" else str(d)
            if st.button(etiqueta, key=f"puerta_{d}", use_container_width=True):
                if estados[d] == "bloqueada":
                    st.toast(f"🔒 Esta puerta se abre el {d} de diciembre", icon="🎄")
                else:
                    if forzar:  # en modo prueba NO se guarda nada de verdad
                        st.session_state["abiertas_prueba"].add(d)
                    elif d not in st.session_state["abiertas"]:
                        st.session_state["abiertas"].add(d)
                        st.session_state["aviso_estado"] = not estado.guardar(
                            st.session_state["abiertas"])
                    # Pinta la puerta en verde ya, sin esperar a otra recarga
                    st.markdown(css_puertas({d: "abierta"}, alturas), unsafe_allow_html=True)
                    contenido = dias.get(str(d), {})
                    st.dialog(f"✨ {d} de diciembre ✨", width="large")(
                        lambda d=d, c=contenido: render_dia(d, c))()
                    if d == 24:
                        st.snow()