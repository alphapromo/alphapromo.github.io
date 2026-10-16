"""Publicação no Instagram (API do Instagram com login do Instagram).

Secrets: IG_USER_ID, IG_ACCESS_TOKEN (token de longa duração, 60 dias).
O token é renovado sozinho a cada 7 dias e salvo de volta (precisa de GH_PAT).
"""
from __future__ import annotations

import logging
import time
from datetime import date

import requests

from ..config import env
from ..secrets_store import save_secret

log = logging.getLogger(__name__)
HOST = "https://graph.instagram.com"


class InstagramError(RuntimeError):
    pass


def _check(r: requests.Response) -> dict:
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        raise InstagramError(f"{r.status_code}: {data.get('error', data)}")
    return data


def refresh_token_if_due(hoje: date) -> None:
    token = env("IG_ACCESS_TOKEN")
    if not token or hoje.weekday() != 0:  # toda segunda-feira
        return
    r = requests.get(f"{HOST}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    try:
        novo = _check(r)["access_token"]
    except Exception as e:  # noqa: BLE001
        log.error("Instagram: não consegui renovar o token: %s", e)
        return
    if novo != token:
        save_secret("IG_ACCESS_TOKEN", novo)


def _publish(container_params: dict, versao: str) -> str:
    uid, token = env("IG_USER_ID"), env("IG_ACCESS_TOKEN")
    if not (uid and token):
        raise InstagramError("IG_USER_ID / IG_ACCESS_TOKEN não configurados")
    base = f"{HOST}/{versao}"
    cid = _check(requests.post(f"{base}/{uid}/media", data={**container_params, "access_token": token}, timeout=60))["id"]
    for _ in range(30):  # espera o Instagram processar a imagem
        st = _check(requests.get(f"{base}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise InstagramError(f"container {cid}: {st}")
        time.sleep(4)
    pub = _check(requests.post(f"{base}/{uid}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60))
    return pub["id"]


def post_feed(image_url: str, caption: str, versao: str) -> str:
    return _publish({"image_url": image_url, "caption": caption}, versao)


def post_story(image_url: str, versao: str) -> str:
    return _publish({"image_url": image_url, "media_type": "STORIES"}, versao)
