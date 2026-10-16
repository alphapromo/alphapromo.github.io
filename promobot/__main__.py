"""Alpha Promo — ponto de entrada.

    python -m promobot run              # o que o GitHub Actions chama: decide sozinho o que fazer agora
    python -m promobot curate [--force] # escolhe as 5 ofertas do dia e gera as artes
    python -m promobot post --slot 3    # publica a oferta #3 agora
    python -m promobot brand            # regera logo/avatar em assets/brand
    --dry-run  não publica nada    --mock  usa ofertas de exemplo (teste sem internet)
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import date, datetime, timedelta

import time

import requests

from . import affiliate, caption, reel, render, site, state
from .config import BRT, ROOT, Settings, env, now_brt
from .models import Deal
from .publish import instagram, tiktok
from .sources import amazon, mercadolivre

log = logging.getLogger("promobot")
POSTS_DIR = "docs/posts"


# ------------------------------------------------------------------ curadoria
def _mock_deals() -> list[Deal]:
    data = json.loads((ROOT / "tests" / "fixtures" / "deals_mock.json").read_text(encoding="utf-8"))
    return [Deal.from_dict(d) for d in data]


def gerar_reel(d: Deal, n: int, hoje: date) -> bool:
    """Monta o Reel da oferta n com as fotos do produto. Devolve True se deu certo."""
    urls = d.extras.get("fotos") or []
    if not urls and d.loja == "Mercado Livre":
        urls = mercadolivre.fotos_produto(d.id)
    if not urls:
        urls = [d.imagem]
    fotos = [render.baixar_imagem(u) for u in urls]
    rel = f"{POSTS_DIR}/{hoje.isoformat()}/{n}-reel.mp4"
    try:
        reel.montar(d, n, fotos, ROOT / rel)
    except Exception as e:  # noqa: BLE001
        log.error("Reel da oferta #%s falhou (vai como foto): %s", n, e)
        return False
    d.extras["reel"] = rel
    return True


def curate(cfg: Settings, hoje: date, mock: bool = False, force: bool = False) -> dict:
    existente = state.load_plan(hoje)
    if existente and not force:
        log.info("Plano de %s já existe.", hoje)
        return existente
    c = cfg["curadoria"]
    if mock:
        deals = _mock_deals()
    else:
        deals = amazon.fetch(c["buscas_amazon"], c["desconto_minimo"]) + mercadolivre.fetch(c["categorias_ml"])
    log.info("Candidatas: %s", len(deals))
    historico = state.load_history()
    escolhidas = selecionar_com_imagem(deals, c, historico, hoje)
    if not escolhidas:
        raise SystemExit("Nenhuma oferta passou nos filtros hoje — verifique as fontes (veja o log acima).")

    pasta = f"{POSTS_DIR}/{hoje.isoformat()}"
    plano = {"data": hoje.isoformat(), "gerado_em": now_brt().isoformat(timespec="minutes"), "deals": [], "posts": {}}
    for n, (d, produto) in enumerate(escolhidas, start=1):
        if not d.link_afiliado:
            d.link_afiliado = affiliate.afiliar(d.loja, d.url)
        feed, vert = f"{pasta}/{n}-feed.jpg", f"{pasta}/{n}-tiktok.jpg"
        render.salvar_jpeg(render.render_post(d, n, "feed", produto), ROOT / feed)
        render.salvar_jpeg(render.render_post(d, n, "tiktok", produto), ROOT / vert)
        d.extras.update({"arte_feed": feed, "arte_tiktok": vert})
        if n in cfg["publicar"].get("reels_ofertas", []):
            gerar_reel(d, n, hoje)
        plano["deals"].append(d.to_dict())
        historico[d.chave] = hoje.isoformat()
        log.info("#%s  %s%% OFF  %s  [%s] score=%s", n, d.desconto, d.titulo[:60], d.loja, d.score)

    state.save_plan(hoje, plano)
    state.save_history(historico, hoje)
    _limpar(hoje, cfg["site"]["manter_dias"])
    site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
    return plano


def selecionar_com_imagem(deals, c, historico, hoje):
    """Seleciona e garante que a foto do produto baixa; se não baixar, pega a próxima."""
    pool = list(deals)
    final = []
    while pool and len(final) < c["ofertas_por_dia"]:
        faltam = c["ofertas_por_dia"] - len(final)
        ja = {d.chave: hoje.isoformat() for d, _ in final}
        lote = [d for d in ranking_selecionar(pool, {**c, "ofertas_por_dia": faltam}, {**historico, **ja}, hoje) if d]
        if not lote:
            break
        for d in lote:
            pool.remove(d)
            img = render.baixar_imagem(d.imagem)
            if img is not None:
                final.append((d, img))
            else:
                log.warning("Pulando %s: imagem indisponível", d.titulo[:50])
    # reaplica a ordem de horários (melhor oferta no horário nobre)
    ordem = ranking_selecionar([d for d, _ in final], {**c, "repetir_produto_apos_dias": 0, "desconto_minimo": 0,
                                                       "preco_minimo": 0, "preco_maximo": 10**9, "maximo_por_categoria": 99},
                               {}, hoje)
    por_chave = {d.chave: (d, img) for d, img in final}
    return [por_chave[d.chave] for d in ordem if d and d.chave in por_chave]


def ranking_selecionar(*a, **k):
    from .ranking import selecionar

    return selecionar(*a, **k)


def _limpar(hoje: date, dias: int) -> None:
    corte = hoje - timedelta(days=dias)
    base = ROOT / POSTS_DIR
    if base.exists():
        for p in base.iterdir():
            try:
                if date.fromisoformat(p.name) < corte:
                    shutil.rmtree(p)
            except ValueError:
                pass
    state.prune_plans(hoje, max(dias, 3))


# ------------------------------------------------------------------ publicação
def post_slot(cfg: Settings, hoje: date, slot: int, dry_run: bool = False) -> bool:
    plano = state.load_plan(hoje)
    if not plano or slot > len(plano["deals"]):
        log.error("Sem oferta #%s no plano de %s", slot, hoje)
        return False
    d = Deal.from_dict(plano["deals"][slot - 1])
    pub = cfg["publicar"]
    marca = cfg["marca"]
    feito = plano["posts"].setdefault(str(slot), {})
    ok = True

    feed_raw = cfg.raw_url(d.extras["arte_feed"])
    vert_raw = cfg.raw_url(d.extras["arte_tiktok"])
    vert_pages = f"{cfg.pages_url}/{d.extras['arte_tiktok'].removeprefix('docs/')}"

    ig_ok = bool(env("IG_ACCESS_TOKEN") and env("IG_USER_ID"))
    tt_ok = bool(env("UPLOADPOST_API_KEY") if pub["tiktok_backend"] != "oficial" else env("TIKTOK_REFRESH_TOKEN"))
    if not dry_run:
        if not ig_ok:
            log.warning("Instagram ainda não configurado — pulando.")
            pub = {**pub, "instagram_feed": False, "instagram_stories": False}
        if not tt_ok:
            log.warning("TikTok ainda não configurado — pulando.")
            pub = {**pub, "tiktok": False}

    reel_url = f"{cfg.pages_url}/{d.extras['reel'].removeprefix('docs/')}" if d.extras.get("reel") else ""
    if reel_url and not dry_run and not _no_ar(reel_url):
        log.warning("Reel ainda não está no ar (%s) — oferta #%s vai como foto.", reel_url, slot)
        reel_url = ""

    tarefas = []
    if pub.get("instagram_feed") and reel_url:
        tarefas.append(("instagram_feed", lambda: instagram.post_reel(reel_url, caption.legenda(d, slot, marca, "instagram"), pub["instagram_api_versao"])))
    elif pub.get("instagram_feed"):
        tarefas.append(("instagram_feed", lambda: instagram.post_feed(feed_raw, caption.legenda(d, slot, marca, "instagram"), pub["instagram_api_versao"])))
    if pub.get("instagram_stories"):
        tarefas.append(("instagram_story", lambda: instagram.post_story(vert_raw, pub["instagram_api_versao"])))
    if pub.get("tiktok"):
        url_tt = vert_pages if pub["tiktok_backend"] == "oficial" else vert_raw
        tarefas.append(("tiktok", lambda: tiktok.post(url_tt, caption.titulo_tiktok(d, slot), caption.legenda(d, slot, marca, "tiktok"),
                                                       pub["tiktok_backend"], pub.get("tiktok_musica_automatica", True))))

    for nome, fn in tarefas:
        if str(feito.get(nome, "")).startswith("ok:"):
            log.info("%s da oferta #%s já publicado — pulando.", nome, slot)
            continue
        if dry_run:
            log.info("[dry-run] publicaria %s da oferta #%s", nome, slot)
            continue
        try:
            rid = fn()
            feito[nome] = f"ok:{rid}"
            log.info("Publicado %s da oferta #%s → %s", nome, slot, rid)
        except Exception as e:  # noqa: BLE001
            ok = False
            feito[nome] = f"erro:{str(e)[:300]}"
            log.error("Falhou %s da oferta #%s: %s", nome, slot, e)
    if not dry_run:
        state.save_plan(hoje, plano)
    return ok


def _no_ar(url: str, espera_max: int = 360) -> bool:
    """Espera o arquivo aparecer no GitHub Pages (o deploy leva ~1 min após o commit)."""
    fim = time.time() + espera_max
    while time.time() < fim:
        try:
            r = requests.head(url, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(15)
    return False


def _hhmm(s: str, hoje: date) -> datetime:
    h, m = map(int, s.split(":"))
    return datetime(hoje.year, hoje.month, hoje.day, h, m, tzinfo=BRT)


def run(cfg: Settings, dry_run: bool, mock: bool) -> int:
    agora = now_brt()
    hoje = agora.date()
    ag = cfg["agenda"]
    if not mock and not (env("ML_MATT_WORD") or env("ML_TAG")):
        log.warning("Robô em espera: cadastre o Secret ML_MATT_WORD (ou ML_TAG) para começar. Nada foi feito.")
        return 0
    if not mock and not (env("ML_CLIENT_ID") and env("ML_CLIENT_SECRET")) and not env("AMAZON_CLIENT_ID"):
        log.warning("Robô em espera: cadastre ML_CLIENT_ID e ML_CLIENT_SECRET (app do Mercado Livre). Nada foi feito.")
        return 0
    tol = timedelta(minutes=ag["tolerancia_minutos"])
    if dry_run is False and not mock:
        instagram.refresh_token_if_due(hoje)

    plano = state.load_plan(hoje)
    if plano is None and agora >= _hhmm(ag["curadoria"], hoje) - timedelta(minutes=30):
        plano = curate(cfg, hoje, mock=mock)

    ok = True
    if plano:
        for i, horario in enumerate(ag["posts"], start=1):
            t = _hhmm(horario, hoje)
            feitos = plano["posts"].get(str(i), {})
            pendente = not feitos or any(not str(v).startswith("ok:") for v in feitos.values())
            if t <= agora <= t + tol and pendente:
                ok &= post_slot(cfg, hoje, i, dry_run=dry_run)
        site.build(hoje, agora.strftime("%d/%m às %Hh%M"))
    return 0 if ok else 1


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(prog="promobot")
    p.add_argument("cmd", choices=["run", "curate", "post", "brand", "site", "arte", "diag", "reel"], nargs="?", default="run")
    p.add_argument("--slot", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--mock", action="store_true")
    a = p.parse_args(argv)
    cfg = Settings.load()
    hoje = now_brt().date()
    dry = a.dry_run or env("DRY_RUN") == "1"

    if a.cmd == "brand":
        render.brand_assets(ROOT / "assets" / "brand")
        return 0
    if a.cmd == "site":
        site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
        return 0
    if a.cmd == "reel":  # monta o Reel de uma oferta do plano de hoje (publica no próximo 'post')
        plano = state.load_plan(hoje)
        if not plano or not a.slot:
            p.error("precisa de plano de hoje e --slot")
        d = Deal.from_dict(plano["deals"][a.slot - 1])
        if gerar_reel(d, a.slot, hoje):
            plano["deals"][a.slot - 1] = d.to_dict()
            state.save_plan(hoje, plano)
            return 0
        return 1
    if a.cmd == "diag":
        mercadolivre.diagnostico()
        return 0
    if a.cmd == "arte":  # refaz as artes do plano de hoje, sem trocar as ofertas
        plano = state.load_plan(hoje)
        if not plano:
            p.error("sem plano para hoje")
        for n, raw in enumerate(plano["deals"], start=1):
            d = Deal.from_dict(raw)
            img = render.baixar_imagem(d.imagem)
            render.salvar_jpeg(render.render_post(d, n, "feed", img), ROOT / d.extras["arte_feed"])
            render.salvar_jpeg(render.render_post(d, n, "tiktok", img), ROOT / d.extras["arte_tiktok"])
        log.info("Artes de %s refeitas.", hoje)
        return 0
    if a.cmd == "curate":
        curate(cfg, hoje, mock=a.mock, force=a.force)
        return 0
    if a.cmd == "post":
        if not a.slot:
            p.error("--slot é obrigatório")
        if a.force:
            plano = state.load_plan(hoje) or {}
            plano.get("posts", {}).pop(str(a.slot), None)
            if plano:
                state.save_plan(hoje, plano)
        ok = post_slot(cfg, hoje, a.slot, dry_run=dry)
        site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
        return 0 if ok else 1
    return run(cfg, dry_run=dry, mock=a.mock)


if __name__ == "__main__":
    sys.exit(main())
