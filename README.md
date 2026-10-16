# Alpha Promo

Robô que todo dia escolhe as 5 ofertas mais quentes do Mercado Livre e da Amazon, gera as artes na identidade Alpha Promo e publica no Instagram (feed + stories) e no TikTok nos horários de pico. Os links de afiliado ficam numa página "link na bio" que se atualiza sozinha.

Roda de graça no GitHub Actions. Depois de configurado, não precisa de nenhuma ação manual.

## Como funciona

| Horário (Brasília) | O que acontece |
|---|---|
| 06:40 | Busca ofertas, ranqueia, escolhe 5, gera as artes e atualiza a página da bio |
| 07:50 · 11:50 · 17:50 · 19:50 · 21:20 | Publica a oferta #1 … #5 (a melhor do dia sai às 19:50) |

- **Ranking**: % de desconto, popularidade, frete grátis e economia em reais. Descarta descontos suspeitos (>85%), acessórios baratos, produtos repetidos nos últimos 14 dias e mais de 2 da mesma categoria.
- **Link na bio**: legenda no Instagram/TikTok não tem link clicável, então cada post diz "oferta #3 no link da bio" e a página (`docs/`, publicada pelo GitHub Pages) lista as ofertas numeradas com o seu link de afiliado.
- **Tokens que expiram** (Instagram a cada 60 dias, Mercado Livre e TikTok giram) são renovados e salvos sozinhos.
- **Se algo falhar**, o GitHub manda e-mail e a próxima execução tenta de novo o que ficou pendente.

## Configuração (uma vez só)

Todos os valores abaixo vão em **Settings › Secrets and variables › Actions › New repository secret**. Ninguém consegue ler um Secret depois de salvo.

### 1. GitHub
- **Settings › Pages**: *Deploy from a branch* → `main` / `/docs`. A página fica em `https://alphapromo.github.io`. Coloque esse endereço na bio do Instagram e do TikTok.
- **`GH_PAT`**: github.com/settings/personal-access-tokens › *Fine-grained* › só o repositório `alpha-promo` › permissão **Secrets: Read and write**. Serve para o robô renovar os próprios tokens.

### 2. Mercado Livre (obrigatório)
- **`ML_MATT_WORD`** e **`ML_MATT_TOOL`**: no portal afiliados.mercadolivre.com.br › Ferramentas › Gerador de link, gere o link de qualquer produto e abra-o no navegador. O endereço final contém `matt_word=...&matt_tool=...`: copie os dois valores. (Se o seu link tiver só `tag=...`, use o Secret **`ML_TAG`**.)
- Opcional, deixa a coleta mais estável: crie um app em developers.mercadolivre.com.br e salve **`ML_CLIENT_ID`**, **`ML_CLIENT_SECRET`** e **`ML_REFRESH_TOKEN`**.

### 3. Amazon
- **`AMAZON_TAG`**: seu ID de rastreamento do Associados (ex.: `alphapromo-20`). Já vale para o botão "Ofertas do dia na Amazon" da página.
- Depois de 10 vendas em 30 dias, a Amazon libera a **Creators API**. Aí salve **`AMAZON_CLIENT_ID`** e **`AMAZON_CLIENT_SECRET`** e o robô passa a escolher 2 produtos da Amazon por dia sozinho.

### 4. Instagram (conta profissional)
1. developers.facebook.com › Criar app › tipo **Empresa** › adicione o produto **Instagram** › *API com login do Instagram*.
2. Em *Gerar tokens de acesso*, adicione a conta @alphapromo e gere o token.
3. Salve **`IG_ACCESS_TOKEN`** (o token) e **`IG_USER_ID`** (o ID mostrado ao lado da conta).

O app pode ficar em modo de desenvolvimento: ele só publica na sua própria conta, não precisa de revisão da Meta.

### 5. TikTok
Padrão: **Upload-Post** (upload-post.com), um serviço já aprovado pelo TikTok. Com app próprio não auditado, o TikTok deixa os posts privados.
1. Crie a conta, conecte o TikTok da Alpha Promo e dê um nome ao perfil. Confira o plano: 5 posts por dia dão ~150 por mês.
2. Salve **`UPLOADPOST_API_KEY`** e **`UPLOADPOST_USER`** (o nome do perfil).

Para usar um app próprio no futuro: `config.yaml` › `tiktok_backend: "oficial"` e os Secrets `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` e `TIKTOK_REFRESH_TOKEN`.

### 6. Testar
Aba **Actions › Alpha Promo › Run workflow**:
- `curate` + *Modo teste* → gera as ofertas e as artes sem publicar (as artes aparecem em `docs/posts/`).
- `post`, oferta `1` → publica a oferta #1 agora.

## Ajustes
Tudo em `config.yaml`: horários, desconto mínimo, faixa de preço, categorias, buscas da Amazon e o que publicar. Se mudar horários, ajuste também os `cron` em `.github/workflows/alpha-promo.yml` (em UTC = Brasília + 3h).

## Rodar no computador
```bash
pip install -r requirements.txt
python -m promobot curate --mock      # ofertas de exemplo, sem internet
python -m promobot run --dry-run      # o que faria agora, sem publicar
```

## Regras que o robô já respeita
- Toda legenda e a página informam que há link de afiliado (`#publi`) — exigência do CONAR, do Mercado Livre e da Amazon.
- A página traz o aviso "Como Associado da Amazon, recebo por compras qualificadas".
- Preços da Amazon só entram via API oficial (a Amazon proíbe copiar preço do site).
- No máximo 5 posts por dia: bem abaixo dos limites de API do Instagram e do TikTok.
