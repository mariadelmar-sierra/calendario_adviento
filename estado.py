"""
Persistencia de los días abiertos del calendario.

Se guarda en `estado_adviento.json` con este formato: {"abiertas": [1, 2, 5]}

⚠️ En Streamlit Community Cloud el disco es temporal: se borra cada vez que la app
se duerme o se reinicia. Por eso, si en los Secrets hay GITHUB_TOKEN y GITHUB_REPO,
el mismo JSON se guarda además en una rama aparte del repositorio ("estado"), que
NO provoca redespliegues y no se pierde nunca. Sin secrets (en local) se usa solo
el archivo del disco.
"""
import base64
import json
from pathlib import Path

import requests
import streamlit as st

ARCHIVO = Path(__file__).parent / "estado_adviento.json"
NOMBRE = "estado_adviento.json"


def _config():
    """(token, 'usuario/repo', rama) si hay secrets de GitHub; si no, None."""
    try:
        s = st.secrets
        if "GITHUB_TOKEN" in s and "GITHUB_REPO" in s:
            return s["GITHUB_TOKEN"], s["GITHUB_REPO"], s.get("GITHUB_BRANCH", "estado")
    except Exception:  # no hay secrets.toml (ejecución local)
        pass
    return None


def _api(metodo, ruta, token, **kw):
    return requests.request(
        metodo, f"https://api.github.com/repos/{ruta}", timeout=10,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"}, **kw)


def _leer_remoto(token, repo, rama):
    """Devuelve (set de días, sha del archivo) o (None, None) si no existe."""
    r = _api("GET", f"{repo}/contents/{NOMBRE}?ref={rama}", token)
    if r.status_code == 200:
        datos = json.loads(base64.b64decode(r.json()["content"]))
        return set(datos["abiertas"]), r.json()["sha"]
    return None, None


def _asegurar_rama(token, repo, rama):
    """Crea la rama de estado (copia de la principal) si todavía no existe."""
    if _api("GET", f"{repo}/git/ref/heads/{rama}", token).status_code == 200:
        return
    base = _api("GET", repo, token).json()["default_branch"]
    sha = _api("GET", f"{repo}/git/ref/heads/{base}", token).json()["object"]["sha"]
    _api("POST", f"{repo}/git/refs", token,
         json={"ref": f"refs/heads/{rama}", "sha": sha})


def cargar() -> set:
    """Días abiertos guardados (GitHub si está configurado; si no, el disco)."""
    cfg = _config()
    if cfg:
        try:
            dias, _ = _leer_remoto(*cfg)
            if dias is not None:
                return dias
        except Exception:
            pass
    try:
        return set(json.loads(ARCHIVO.read_text(encoding="utf-8"))["abiertas"])
    except Exception:
        return set()


def guardar(abiertas: set, reemplazar: bool = False) -> bool:
    """Guarda los días abiertos. Por defecto SOLO AÑADE (une con lo ya guardado),
    para no perder días si una lectura falló. `reemplazar=True` sirve para reiniciar.
    Devuelve False si no pudo guardar en GitHub (el disco local sí se guarda)."""
    abiertas = set(abiertas)
    cfg = _config()
    ok = True
    if cfg:
        token, repo, rama = cfg
        try:
            _asegurar_rama(token, repo, rama)
            remotos, sha = _leer_remoto(token, repo, rama)
            if remotos and not reemplazar:
                abiertas |= remotos
            cuerpo = {"message": "Estado del calendario", "branch": rama,
                      "content": base64.b64encode(json.dumps(
                          {"abiertas": sorted(abiertas)}, indent=2).encode()).decode()}
            if sha:
                cuerpo["sha"] = sha
            r = _api("PUT", f"{repo}/contents/{NOMBRE}", token, json=cuerpo)
            ok = r.status_code in (200, 201)
        except Exception:
            ok = False
    try:  # copia local (útil en tu ordenador)
        ARCHIVO.write_text(json.dumps({"abiertas": sorted(abiertas)}, indent=2),
                           encoding="utf-8")
    except Exception:
        ok = ok and cfg is not None
    return ok