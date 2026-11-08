// "Eu quero" instantâneo: o Instagram avisa este Worker (Cloudflare) assim que
// alguém comenta, e ele manda o link da oferta no direct da pessoa em segundos.
//
// Segredos (definidos pelo GitHub Actions, nunca no código):
//   IG_ACCESS_TOKEN, IG_USER_ID, IG_APP_SECRET
// Variáveis (wrangler.toml): VERIFY_TOKEN, API_VERSION, SITE

const GATILHO = /\bquero\b/;

function normalizar(t) {
  return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function assinaturaOk(corpo, cabecalho, segredo) {
  if (!cabecalho || !segredo) return false;
  const chave = await crypto.subtle.importKey("raw", new TextEncoder().encode(segredo),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const esperado = "sha256=" + hex(await crypto.subtle.sign("HMAC", chave, new TextEncoder().encode(corpo)));
  if (esperado.length !== cabecalho.length) return false;
  let dif = 0;
  for (let i = 0; i < esperado.length; i++) dif |= esperado.charCodeAt(i) ^ cabecalho.charCodeAt(i);
  return dif === 0;
}

function brl(v) {
  return "R$ " + Number(v).toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function mensagem(oferta, usuario, site) {
  const oi = usuario ? `Oi, @${usuario}! 👋` : "Oi! 👋";
  if (!oferta) {
    return `${oi} Todas as ofertas, com link direto, estão aqui: ${site}\n\n` +
      "Segue a @alphapromo.ofertas pra receber as próximas ofertas antes de acabar 🧡";
  }
  const nome = oferta.titulo.length <= 70 ? oferta.titulo : oferta.titulo.slice(0, 69).replace(/\s+\S*$/, "") + "…";
  return `${oi} Aqui está o link da oferta que você pediu:\n\n` +
    `🛒 ${nome}\n💰 ${brl(oferta.preco)} no ${oferta.loja} (preço do dia do post, pode ter mudado)\n` +
    `👉 ${oferta.link}\n\n` +
    "Segue a @alphapromo.ofertas pra receber as próximas ofertas antes de acabar 🧡";
}

async function ofertas(env) {
  // lista publicada pelo robô no GitHub Pages: id do post -> oferta
  const r = await fetch(`${env.SITE}/ofertas-ig.json`, { cf: { cacheTtl: 60 } });
  return r.ok ? r.json() : {};
}

async function jaRespondido(cid) {
  const chave = new Request(`https://quero.local/${cid}`);
  if (await caches.default.match(chave)) return true;
  await caches.default.put(chave, new Response("1", { headers: { "Cache-Control": "max-age=604800" } }));
  return false;
}

async function responder(v, env) {
  const base = `https://graph.instagram.com/${env.API_VERSION}`;
  const usuario = v.from?.username || "";
  const mapa = await ofertas(env);
  const oferta = mapa[v.media?.id];
  const dm = await fetch(`${base}/${env.IG_USER_ID}/messages?access_token=${encodeURIComponent(env.IG_ACCESS_TOKEN)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient: { comment_id: v.id }, message: { text: mensagem(oferta, usuario, env.SITE) } }),
  });
  if (!dm.ok) {
    console.log("direct falhou", dm.status, await dm.text());
    return;
  }
  const texto = usuario ? `@${usuario} te mandei o link no direct! 📩` : "Te mandei o link no direct! 📩";
  const rp = await fetch(`${base}/${v.id}/replies`, {
    method: "POST",
    body: new URLSearchParams({ message: texto, access_token: env.IG_ACCESS_TOKEN }),
  });
  if (!rp.ok) console.log("resposta pública falhou", rp.status, await rp.text());
}

async function processar(dados, env) {
  for (const entrada of dados.entry || []) {
    for (const mudanca of entrada.changes || []) {
      if (mudanca.field !== "comments") continue;
      const v = mudanca.value || {};
      if (!v.id || v.from?.id === env.IG_USER_ID) continue; // comentário da própria Alpha Promo
      if (v.parent_id) continue; // resposta dentro de outro comentário
      if (!GATILHO.test(normalizar(v.text))) continue;
      if (await jaRespondido(v.id)) continue; // o Instagram às vezes reenvia o mesmo aviso
      await responder(v, env);
    }
  }
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "GET") {
      // verificação feita pela Meta ao cadastrar o webhook
      if (url.searchParams.get("hub.mode") === "subscribe" &&
          url.searchParams.get("hub.verify_token") === env.VERIFY_TOKEN) {
        return new Response(url.searchParams.get("hub.challenge") || "");
      }
      return new Response("Alpha Promo: eu quero ✓");
    }
    if (req.method !== "POST") return new Response("", { status: 405 });
    const corpo = await req.text();
    if (!(await assinaturaOk(corpo, req.headers.get("x-hub-signature-256"), env.IG_APP_SECRET))) {
      return new Response("assinatura inválida", { status: 401 });
    }
    ctx.waitUntil(processar(JSON.parse(corpo), env));
    return new Response("ok");
  },
};
