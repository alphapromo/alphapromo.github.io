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

from . import affiliate, caption, carrossel, carta, reel, render, site, state
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
        reel.montar(d, n, fotos, ROOT / rel, dia=hoje)
    except Exception as e:  # noqa: BLE001
        log.error("Reel da oferta #%s falhou (vai como foto): %s", n, e)
        return False
    d.extras["reel"] = rel
    return True


def _aviso(msg: str) -> None:
    """Log + anotação no GitHub Actions (aparece no resumo da execução, sem abrir o log)."""
    log.info(msg)
    if env("GITHUB_ACTIONS"):
        print(f"::notice::{msg}", flush=True)


def _numeros_colecao(hoje: date, quantos: int) -> list[int]:
    """Próximos números da coleção do mês (001/155, 002/155…)."""
    arq = state.STATE / "colecao.json"
    dados = json.loads(arq.read_text()) if arq.exists() else {}
    chave = hoje.strftime("%Y-%m")
    ult = int(dados.get(chave, 0))
    dados[chave] = ult + quantos
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados, indent=2))
    return list(range(ult + 1, ult + 1 + quantos))


def gerar_artes(itens: list[tuple[Deal, int, object]], hoje: date, total_dia: int) -> None:
    """Desenha a Alpha Card (feed 4:5 e vertical 9:16) de cada (oferta, número, foto)."""
    pasta = f"{POSTS_DIR}/{hoje.isoformat()}"
    with carta.Fotografo() as f:
        for d, n, img in itens:
            feed, vert = f"{pasta}/{n}-feed.jpg", f"{pasta}/{n}-tiktok.jpg"
            num = d.extras.get("num_colecao") or 1
            render.salvar_jpeg(carta.render(d, n, total_dia, "feed", num, hoje, img, f), ROOT / feed)
            render.salvar_jpeg(carta.render(d, n, total_dia, "tiktok", num, hoje, img, f), ROOT / vert)
            d.extras.update({"arte_feed": feed, "arte_tiktok": vert})


def _publicado(plano: dict, n: int) -> bool:
    return any(str(v).startswith("ok:") for v in plano.get("posts", {}).get(str(n), {}).values())


def curate(cfg: Settings, hoje: date, mock: bool = False, force: bool = False, manter: bool = False) -> dict:
    """Escolhe as ofertas do dia. manter=True: refaz só as que ainda não foram publicadas."""
    existente = state.load_plan(hoje)
    if existente and existente.get("deals") and not force:
        log.info("Plano de %s já existe.", hoje)
        return existente
    c = cfg["curadoria"]
    if mock:
        deals = _mock_deals()
    else:
        deals = amazon.fetch(c["buscas_amazon"], c["desconto_minimo"]) + mercadolivre.fetch(
            c["categorias_ml"], c.get("explorar_subcategorias"))
    log.info("Candidatas: %s", len(deals))
    historico = state.load_history()
    fixas: dict[int, dict] = {}
    if existente and manter and existente.get("deals"):
        fixas = {n: raw for n, raw in enumerate(existente["deals"], start=1) if _publicado(existente, n)}
    excluir = {Deal.from_dict(r).chave for r in fixas.values()}
    escolhidas = selecionar_com_imagem(deals, c, historico, hoje, excluir,
                                       [Deal.from_dict(r) for r in fixas.values()])
    if not any(img is not None for _, img in escolhidas) and not fixas:
        raise SystemExit("Nenhuma oferta passou nos filtros hoje — verifique as fontes (veja o log acima).")

    plano = {"data": hoje.isoformat(), "gerado_em": now_brt().isoformat(timespec="minutes"), "deals": [],
             "posts": {str(n): existente["posts"][str(n)] for n in fixas} if fixas else {},
             "avulsos": (existente or {}).get("avulsos", []), "posts_avulsos": (existente or {}).get("posts_avulsos", {})}
    # ordem final: as já publicadas ficam no lugar; as novas preenchem os demais horários
    ordem: list[tuple[int, object, object]] = []  # (n, Deal|raw fixo, foto)
    for i, (d, img) in enumerate(escolhidas, start=1):
        if i in fixas:
            ordem.append((i, fixas[i], None))
        elif d is not None and img is not None:
            ordem.append((i, d, img))
    for i in sorted(fixas):  # extras já publicadas (#6, #7…) continuam no plano
        if i > len(escolhidas):
            ordem.append((i, fixas[i], None))
    ordem = [(k, x, img) for k, (_, x, img) in enumerate(ordem, start=1)]
    novas = [(n, d, img) for n, d, img in ordem if isinstance(d, Deal)]
    antigos = {n: Deal.from_dict(existente["deals"][n - 1]).extras.get("num_colecao")
               for n in range(1, len(existente["deals"]) + 1)} if (existente and manter and existente.get("deals")) else {}
    faltam = [n for n, _, _ in novas if not antigos.get(n)]
    numeros = dict(zip(faltam, _numeros_colecao(hoje, len(faltam))))
    for n, d, _ in novas:
        d.extras["num_colecao"] = antigos.get(n) or numeros[n]
        if not d.link_afiliado:
            d.link_afiliado = affiliate.afiliar(d.loja, d.url)
    gerar_artes([(d, n, img) for n, d, img in novas], hoje, len(ordem))
    for n, d, _ in ordem:
        if not isinstance(d, Deal):
            plano["deals"].append(d)
            continue
        if n in cfg["publicar"].get("reels_ofertas", []):
            gerar_reel(d, n, hoje)
        plano["deals"].append(d.to_dict())
        historico[d.chave] = hoje.isoformat()
        _aviso(f"#{n} {d.extras.get('tema', 'melhor do dia')} | top {d.extras.get('posicao')} em {d.categoria} | "
               f"{d.desconto}% OFF R$ {d.preco:.2f} | {d.extras.get('marca') or '-'} | {d.titulo[:60]}")

    state.save_plan(hoje, plano)
    state.save_history(historico, hoje)
    _limpar(hoje, cfg["site"]["manter_dias"])
    site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
    return plano


def produto(cfg: Settings, hoje: date, busca: str, exigir: list[str], rotulo: str, lancamento: str = "") -> int:
    """Lançamento/pré-venda escolhido a dedo: busca no catálogo do Mercado Livre e desenha a carta.

    Fica em plano["avulsos"] (não ocupa os horários do dia). Publicar depois com `post --avulso --slot N`.
    """
    d = mercadolivre.buscar_produto(busca, exigir)
    if d is None:
        raise SystemExit(f"Não achei '{busca}' com preço no Mercado Livre.")
    img = render.baixar_imagem(d.imagem)
    if img is None:
        raise SystemExit("Produto sem foto disponível.")
    plano = state.load_plan(hoje) or {"data": hoje.isoformat(), "deals": [], "posts": {}}
    avulsos = plano.setdefault("avulsos", [])
    n = len(avulsos) + 1
    d.link_afiliado = affiliate.afiliar(d.loja, d.url)
    d.extras.update({"tema": rotulo, "avulso": True, "lancamento": lancamento,
                     "num_colecao": _numeros_colecao(hoje, 1)[0]})
    pasta = f"{POSTS_DIR}/{hoje.isoformat()}"
    with carta.Fotografo() as f:
        feed, vert = f"{pasta}/L{n}-feed.jpg", f"{pasta}/L{n}-tiktok.jpg"
        render.salvar_jpeg(carta.render(d, n, 0, "feed", d.extras["num_colecao"], hoje, img, f), ROOT / feed)
        render.salvar_jpeg(carta.render(d, n, 0, "tiktok", d.extras["num_colecao"], hoje, img, f), ROOT / vert)
    d.extras.update({"arte_feed": feed, "arte_tiktok": vert})
    avulsos.append(d.to_dict())
    state.save_plan(hoje, plano)
    site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
    _aviso(f"Lançamento L{n} | {d.titulo[:70]} | R$ {d.preco:.2f} | de R$ {d.preco_original:.2f} | {d.extras.get('marca') or '-'} | {d.url}")
    return n


def extra(cfg: Settings, hoje: date, tema_n: int, quantos: int, mock: bool = False) -> list[int]:
    """Acrescenta ao plano de hoje `quantos` ofertas extras do tema (ex.: 2 = Games).

    Só escolhe e desenha; a publicação é feita depois com `post --slot N`
    (as artes precisam estar no ar no GitHub antes de ir para o Instagram).
    """
    from .ranking import _bonus_palavras, _no_tema, _parecido, marca_ok, score

    plano = state.load_plan(hoje)
    if not plano:
        raise SystemExit("Ainda não há plano hoje — rode a curadoria antes.")
    c = cfg["curadoria"]
    tema = {int(k): v for k, v in c["temas"].items()}[tema_n]
    if mock:
        deals = _mock_deals()
    else:
        cats = {k: c["categorias_ml"].get(k, tema["nome"]) for k in tema.get("categorias", [])} or c["categorias_ml"]
        explorar = {k: v for k, v in (c.get("explorar_subcategorias") or {}).items() if k in cats}
        deals = mercadolivre.fetch(cats, explorar)
    historico = state.load_history()
    corte = (hoje - timedelta(days=c["repetir_produto_apos_dias"])).isoformat()
    ja = [Deal.from_dict(r) for r in plano["deals"]]
    cand = []
    for d in deals:
        if historico.get(d.chave, "") >= corte or not (c["desconto_minimo"] <= d.desconto <= c.get("desconto_maximo", 70)):
            continue
        if not marca_ok(d, c):
            continue
        if not d.imagem or not _no_tema(d, tema, relaxado=True):
            continue
        d.score = score(d) + _bonus_palavras(d, tema)
        cand.append(d)
    cand.sort(key=lambda d: d.score, reverse=True)
    escolhidas = []
    for d in cand:
        if len(escolhidas) >= quantos:
            break
        if any(_parecido(d.titulo, u.titulo) for u in ja + [e for e, _ in escolhidas]):
            continue
        img = render.baixar_imagem(d.imagem)
        if img is not None:
            escolhidas.append((d, img))
    if not escolhidas:
        raise SystemExit(f"Nenhuma oferta de {tema['nome']} disponível agora.")
    base = len(plano["deals"])
    numeros = _numeros_colecao(hoje, len(escolhidas))
    itens = []
    for k, (d, img) in enumerate(escolhidas):
        d.extras.update({"tema": tema["nome"], "num_colecao": numeros[k], "extra": True})
        if not d.link_afiliado:
            d.link_afiliado = affiliate.afiliar(d.loja, d.url)
        itens.append((d, base + k + 1, img))
    gerar_artes(itens, hoje, base + len(itens))
    for d, n, _ in itens:
        plano["deals"].append(d.to_dict())
        historico[d.chave] = hoje.isoformat()
        _aviso(f"Extra #{n} | top {d.extras.get('posicao')} | {d.desconto}% OFF R$ {d.preco:.2f} | {d.extras.get('marca') or '-'} | {d.titulo[:60]}")
    state.save_plan(hoje, plano)
    state.save_history(historico, hoje)
    site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
    return [n for _, n, _ in itens]


def selecionar_com_imagem(deals, c, historico, hoje, excluir=None, ja_usados=None):
    """Escolhe uma oferta por horário (com tema) e garante que a foto baixa; se não, troca."""
    from .ranking import selecionar_por_tema

    ruins: set[str] = set(excluir or ())
    fotos: dict[str, object] = {}
    for _ in range(6):
        escolha = selecionar_por_tema(deals, c, historico, hoje, excluir=ruins, ja_usados=ja_usados)
        faltou = False
        for d in escolha:
            if d is None or d.chave in fotos:
                continue
            img = render.baixar_imagem(d.imagem)
            if img is None:
                log.warning("Pulando %s: imagem indisponível", d.titulo[:50])
                ruins.add(d.chave)
                faltou = True
            else:
                fotos[d.chave] = img
        if not faltou:
            break
    return [(d, fotos.get(d.chave) if d is not None else None) for d in escolha]


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
def post_slot(cfg: Settings, hoje: date, slot: int, dry_run: bool = False, avulso: bool = False) -> bool:
    """Publica a oferta #slot do plano (ou o lançamento/pré-venda nº slot, se avulso=True)."""
    lista, chave_posts = ("avulsos", "posts_avulsos") if avulso else ("deals", "posts")
    plano = state.load_plan(hoje)
    if not plano or slot > len(plano.get(lista, [])):
        log.error("Sem %s #%s no plano de %s", lista, slot, hoje)
        return False
    d = Deal.from_dict(plano[lista][slot - 1])
    pub = cfg["publicar"]
    marca = cfg["marca"]
    feito = plano.setdefault(chave_posts, {}).setdefault(str(slot), {})
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

    # trava contra duplicado: se o post do feed já está no Instagram, não publica de novo (nem o story)
    if not dry_run and ig_ok and pub.get("instagram_feed") and not str(feito.get("instagram_feed", "")).startswith("ok:"):
        primeira = caption.legenda(d, slot, marca, "instagram").split("\n", 1)[0]
        existente = instagram.ja_publicado(primeira, pub["instagram_api_versao"])
        if existente:
            log.warning("Oferta #%s já está no Instagram (%s) — não vou publicar de novo.", slot, existente)
            feito["instagram_feed"] = f"ok:{existente}"
            feito.setdefault("instagram_story", "ok:ja-publicado")

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
    """Chamado a cada 15 min pelo GitHub. Só faz algo quando há tarefa no horário."""
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
    if not dry_run and not mock:
        controle = state.STATE / "token-instagram-renovado.txt"
        ultimo = controle.read_text().strip() if controle.exists() else ""
        if hoje.weekday() == 0 and ultimo != hoje.isoformat():
            instagram.refresh_token_if_due(hoje)
            controle.write_text(hoje.isoformat())

    mudou = False
    plano = state.load_plan(hoje)
    if (plano is None or not plano.get("deals")) and agora >= _hhmm(ag["curadoria"], hoje) - timedelta(minutes=30):
        plano = curate(cfg, hoje, mock=mock)
        mudou = True

    ok = True
    if plano and plano.get("deals"):
        for i, horario in enumerate(ag["posts"], start=1):
            t = _hhmm(horario, hoje)
            feitos = plano["posts"].get(str(i), {})
            pendente = not feitos or any(not str(v).startswith("ok:") for v in feitos.values())
            if t <= agora <= t + tol and pendente:
                ok &= post_slot(cfg, hoje, i, dry_run=dry_run)
                mudou = True
                plano = state.load_plan(hoje)

    # carrossel "Top 5 da semana": prepara ~1h antes e publica no horário (as imagens precisam estar no ar)
    cs = ag.get("carrossel_semanal")
    if cs and agora.weekday() == int(cs["dia_semana"]) and hoje.isoformat() >= str(cs.get("inicio", "")):
        hora = _hhmm(cs["hora"], hoje)
        dados = carrossel.carregar(hoje)
        if dados is None and hora - timedelta(minutes=75) <= agora < hora + tol:
            carrossel.preparar(cfg, hoje)
            mudou = True
        elif dados and not str(dados.get("post", "")).startswith(("ok:", "pulado")) and hora <= agora <= hora + tol:
            ok &= carrossel.publicar(cfg, hoje, dry_run=dry_run)
            mudou = True
    if mudou:
        site.build(hoje, agora.strftime("%d/%m às %Hh%M"))
    if not mudou:
        log.info("Nada a fazer agora (%s).", agora.strftime("%H:%M"))
    return 0 if ok else 1


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(prog="promobot")
    p.add_argument("cmd", choices=["run", "curate", "post", "brand", "site", "arte", "diag", "reel", "extra", "carrossel", "produto"], nargs="?", default="run")
    p.add_argument("--slot", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--manter", action="store_true", help="curate: mantém as ofertas já publicadas hoje")
    p.add_argument("--tema", type=int, default=2, help="extra: número do tema (2 = Games)")
    p.add_argument("--quantos", type=int, default=2)
    p.add_argument("--busca", default="", help="produto: o que procurar no catálogo")
    p.add_argument("--exigir", default="", help="produto: palavras obrigatórias no nome, separadas por vírgula")
    p.add_argument("--rotulo", default="Pré-venda")
    p.add_argument("--lancamento", default="", help="produto: data de lançamento (ex.: 19/11)")
    p.add_argument("--avulso", action="store_true", help="post: publica um lançamento (L1, L2…)")
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
        itens = [(Deal.from_dict(raw), n, None) for n, raw in enumerate(plano["deals"], start=1)
                 if not _publicado(plano, n)]
        itens = [(d, n, render.baixar_imagem(d.imagem)) for d, n, _ in itens]
        gerar_artes(itens, hoje, len(plano["deals"]))
        for d, n, _ in itens:
            plano["deals"][n - 1] = d.to_dict()
        state.save_plan(hoje, plano)
        log.info("Artes de %s refeitas.", hoje)
        return 0
    if a.cmd == "curate":
        curate(cfg, hoje, mock=a.mock, force=a.force or a.manter, manter=a.manter)
        return 0
    if a.cmd == "carrossel":  # prepara (1ª vez) ou publica (2ª vez) o Top 5 da semana de hoje
        if carrossel.carregar(hoje) is None or a.force:
            carrossel.preparar(cfg, hoje)
        else:
            carrossel.publicar(cfg, hoje, dry_run=dry)
        site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
        return 0
    if a.cmd == "produto":
        produto(cfg, hoje, a.busca, [x.strip() for x in a.exigir.split(",") if x.strip()], a.rotulo, a.lancamento)
        return 0
    if a.cmd == "extra":
        extra(cfg, hoje, a.tema, a.quantos, mock=a.mock)
        return 0
    if a.cmd == "post":
        if not a.slot:
            p.error("--slot é obrigatório")
        if a.force:
            plano = state.load_plan(hoje) or {}
            plano.get("posts", {}).pop(str(a.slot), None)
            if plano:
                state.save_plan(hoje, plano)
        ok = post_slot(cfg, hoje, a.slot, dry_run=dry, avulso=a.avulso)
        site.build(hoje, now_brt().strftime("%d/%m às %Hh%M"))
        return 0 if ok else 1
    return run(cfg, dry_run=dry, mock=a.mock)


if __name__ == "__main__":
    sys.exit(main())
