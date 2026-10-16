"""Publicação no TikTok (post de foto).

Dois caminhos (config.yaml > publicar.tiktok_backend):

- "uploadpost": usa o Upload-Post (upload-post.com), um app já auditado pelo TikTok,
  então os posts saem públicos desde o primeiro dia.
  Secrets: UPLOADPOST_API_KEY, UPLOADPOST_USER (nome do perfil criado no painel deles).
- "oficial": seu próprio app no TikTok for Developers. Enquanto o app não passar
  na auditoria do TikTok, os posts ficam PRIVADOS (só você vê).
  Secrets: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN.
  O domínio das imagens (seu GitHub Pages) precisa estar verificado no app.
"""
from __future__ import annotations

import logging
import time

import requests

from ..config import env
from ..secrets_store import save_secret

log = logging.getLogger(__name__)


class TikTokError(RuntimeError):
    pass


# ------------------------------------------------------------------ Upload-Post
def _uploadpost(image_url: str, titulo: str, descricao: str, musica: bool) -> str:
    key, user = env("UPLOADPOST_API_KEY"), env("UPLOADPOST_USER")
    if not (key and user):
        raise TikTokError("UPLOADPOST_API_KEY / UPLOADPOST_USER não configurados")
    data = [
        ("user", user),
        ("platform[]", "tiktok"),
        ("photos[]", image_url),
        ("tiktok_title", titulo),
        ("description", descricao),
        ("post_mode", "DIRECT_POST"),
        ("privacy_level", "PUBLIC_TO_EVERYONE"),
        ("auto_add_music", "true" if musica else "false"),
        ("brand_content_toggle", "true"),  # divulgação de marca de terceiros (afiliado)
    ]
    r = requests.post(
        "https://api.upload-post.com/api/upload_photos",
        headers={"Authorization": f"Apikey {key}"},
        data=data,
        timeout=180,
    )
    body = r.json() if r.content else {}
    if r.status_code >= 400 or not body.get("success", False):
        raise TikTokError(f"Upload-Post {r.status_code}: {body}")
    res = (body.get("results") or {}).get("tiktok") or {}
    return res.get("url") or body.get("request_id") or "ok"


# ------------------------------------------------------------------ API oficial
API = "https://open.tiktokapis.com/v2"


def _token() -> str:
    ck, cs, rt = env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET"), env("TIKTOK_REFRESH_TOKEN")
    if not (ck and cs and rt):
        raise TikTokError("TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_REFRESH_TOKEN não configurados")
    r = requests.post(
        f"{API}/oauth/token/",
        data={"client_key": ck, "client_secret": cs, "grant_type": "refresh_token", "refresh_token": rt},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise TikTokError(f"token: {data}")
    if data.get("refresh_token") and data["refresh_token"] != rt:
        save_secret("TIKTOK_REFRESH_TOKEN", data["refresh_token"])
    return data["access_token"]


def _oficial(image_url: str, titulo: str, descricao: str, musica: bool) -> str:
    token = _token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    info = requests.post(f"{API}/post/publish/creator_info/query/", headers=h, timeout=30).json()
    opcoes = (info.get("data") or {}).get("privacy_level_options") or ["SELF_ONLY"]
    privacidade = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opcoes else opcoes[0]
    body = {
        "post_info": {
            "title": titulo,
            "description": descricao[:4000],
            "privacy_level": privacidade,
            "disable_comment": False,
            "auto_add_music": musica,
            "brand_content_toggle": privacidade != "SELF_ONLY",  # conteúdo de marca não pode ser privado
            "brand_organic_toggle": False,
        },
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": [image_url]},
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    r = requests.post(f"{API}/post/publish/content/init/", headers=h, json=body, timeout=60).json()
    err = (r.get("error") or {}).get("code")
    if err and err != "ok":
        raise TikTokError(f"init: {r}")
    publish_id = r["data"]["publish_id"]
    for _ in range(20):
        st = requests.post(f"{API}/post/publish/status/fetch/", headers=h, json={"publish_id": publish_id}, timeout=30).json()
        status = (st.get("data") or {}).get("status")
        if status == "PUBLISH_COMPLETE":
            break
        if status == "FAILED":
            raise TikTokError(f"status: {st}")
        time.sleep(6)
    if privacidade == "SELF_ONLY":
        log.warning("TikTok: app ainda não auditado — post saiu como PRIVADO.")
    return publish_id


def post(image_url: str, titulo: str, descricao: str, backend: str, musica: bool = True) -> str:
    if backend == "oficial":
        return _oficial(image_url, titulo, descricao, musica)
    return _uploadpost(image_url, titulo, descricao, musica)
