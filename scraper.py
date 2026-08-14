#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper.py — Monitor de leilões (veículos, imóveis e bens diversos)

Versão adaptada pra rodar sozinha no GitHub Actions e publicar o resultado
como um site estático (GitHub Pages), em vez de rodar manualmente no seu PC.
Verifica vários leiloeiros brasileiros e marca quais lotes são NOVOS desde a
última execução (o estado fica salvo em docs/dados_vistos.json e é
commitado de volta no repositório a cada rodada pelo workflow do Actions).

SITES COBERTOS (agosto/2026):
  - Sodré Santoro          -> veículos (busca por modelo)
  - VIP Leilões            -> veículos (busca por modelo)
  - Mega Leilões           -> veículos (busca por modelo) + imóveis (listagem completa)
  - Portal Zuk / Zukerman  -> veículos (filtrado por modelo) + imóveis + bens diversos (tudo)
  - Leilo.com.br           -> carros (filtrado por modelo) + imóveis + equipamentos (tudo)
  - Freitas Leiloeiro      -> veículos (filtrado por modelo) + imóveis + materiais (tudo)
  - Superbid Exchange      -> veículos (busca por modelo) + imóveis + diversos (tudo)

Categorias de VEÍCULOS são filtradas pelos modelos configurados em MODELOS
abaixo (é o que você pediu originalmente: BMW 320i, Civic, Jetta, Golf,
Vectra, Lancer). Categorias de IMÓVEIS e BENS DIVERSOS/EQUIPAMENTOS/MATERIAIS
NÃO têm filtro de preço/local — mostram tudo que os sites têm listado, como
você pediu. Isso pode gerar bastante volume (centenas de itens); o relatório
HTML tem filtros por site/categoria pra facilitar a navegação.

USO LOCAL (opcional, pra testar antes de publicar):
    pip install -r requirements.txt
    playwright install chromium
    python scraper.py                 -> roda e gera docs/index.html
    python scraper.py --so-veiculos   -> roda só as categorias de veículos (mais rápido)

USO NO GITHUB ACTIONS (é assim que roda de verdade, sozinho, toda semana):
    Veja .github/workflows/checar-leiloes.yml — ele instala tudo, roda este
    script e publica docs/index.html no GitHub Pages automaticamente. Você
    não precisa rodar nada manualmente depois de configurado; dá pra também
    disparar manualmente pela aba "Actions" do repositório no GitHub
    quando quiser uma checagem na hora.

AVISOS IMPORTANTES:
  1) Vários desses sites (Leilo.com.br, Portal Zuk, Superbid, Freitas
     Leiloeiro, Mega Leilões, Sodré Santoro) mostraram, durante os testes,
     redirecionamentos automáticos de aba pra outros sites de leilão sem
     nenhum clique — pode ser publicidade agressiva de terceiros, ou pode
     ter sido interferência de eu ter testado vários sites ao mesmo tempo em
     abas compartilhadas. De qualquer forma, o script se protege disso:
     fecha automaticamente qualquer aba/popup extra que se abrir sozinha, e
     confere se a página não "fugiu" do domínio esperado antes de tentar ler
     os dados (se fugiu, ele pula esse site/categoria naquela rodada e segue
     pros outros, sem travar).
  2) O layout de cada site pode mudar a qualquer momento. Quando isso
     acontece, o site específico para de retornar resultados, mas o script
     não trava por causa disso — ele avisa no log ("erro em..." ou "pulando")
     e continua os outros. Se perceber que algum site parou de trazer coisa
     por muito tempo, me chama que eu ajusto o seletor.
  3) Domínios que pareciam "mortos"/redirecionando permanentemente para
     outro site (ex: sodresantoro.com.br/imoveis redireciona pra
     leilo.com.br) foram tratados apontando pro destino certo quando fazia
     sentido.
  4) Alguns sites (Leilo.com.br, Freitas Leiloeiro, Portal Zuk) não têm
     busca por palavra-chave funcional pra veículos — nesses casos o script
     baixa a listagem geral de veículos abertos e filtra pelos modelos
     configurados dentro do próprio Python (não é uma limitação sua, é do
     site).
  5) Mega Leilões não expõe link direto por lote nas telas de busca — o
     script mostra o código do lote (ex: ML06407/J13840 ou J126850) pra você
     localizar manualmente no site.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright não está instalado. Rode:\n  pip install -r requirements.txt\n  playwright install chromium")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
DOCS_DIR.mkdir(exist_ok=True)
STATE_FILE = DOCS_DIR / "dados_vistos.json"
REPORT_FILE = DOCS_DIR / "index.html"

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO — edite a lista abaixo com os modelos de veículo que você
# quer acompanhar. Isso só afeta as categorias de VEÍCULOS; imóveis e bens
# diversos aparecem todos, sem filtro.
# ---------------------------------------------------------------------------
MODELOS = [
    "BMW 320i",
    "Civic",
    "Jetta",
    "Golf",
    "Vectra",
    "Lancer",
]

# Palavras-chave usadas para reconhecer os modelos acima dentro do título de
# um lote, nos sites onde não dá pra buscar por termo (só listar tudo e
# filtrar aqui no Python).
TERMOS_CHAVE_MODELOS = ["320I", "CIVIC", "JETTA", "GOLF", "VECTRA", "LANCER", "BMW"]

TIMEOUT = 30000  # ms


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def bate_modelo(titulo):
    if not titulo:
        return False
    t = titulo.upper()
    return any(k in t for k in TERMOS_CHAVE_MODELOS)


def extrair_campos_de_texto(texto):
    """Parser genérico: dado o texto de um card de lote, tenta achar preço,
    título, local e uma 'condição/status' a partir de heurísticas de texto.
    Não é perfeito (cada site formata diferente), mas cobre a maioria dos
    casos sem precisar de um parser dedicado por site."""
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]

    preco = None
    m = re.search(r"R\$\s*[\d\.]+,\d{2}", texto)
    if m:
        preco = m.group(0)

    ignorar = re.compile(
        r"^(Lote\b|R\$|location_on|schedule|photo|favorite|calendar_today|chevron|"
        r"\d+\s*Fotos?$|\d+\s*/\s*\d+$|AO VIVO|ABERTO|VENDIDO|Judicial|Extrajudicial|"
        r"Lance|Maior lance|\d+%$|\d+x no cart)",
        re.I,
    )
    titulo = None
    for l in linhas:
        if len(l) >= 8 and not ignorar.match(l) and not re.match(r"^\d+$", l):
            titulo = l
            break
    if not titulo and linhas:
        titulo = linhas[0]

    local = None
    m2 = re.search(r"([A-ZÀ-Ú][a-zà-ú\.\s]{2,30})\s*[/\-]\s*([A-Z]{2})\b", texto)
    if m2:
        local = f"{m2.group(1).strip()}/{m2.group(2)}"

    condicao_kw = [
        "SEM SINISTRO", "MÉDIA MONTA", "PEQUENA MONTA", "GRANDE MONTA",
        "RECUPERADO DE FINANCIAMENTO", "FINANCEIRA", "SEGURADORA",
        "JUDICIAL", "EXTRAJUDICIAL", "VENDIDO NO ESTADO",
    ]
    condicao = next((l for l in linhas if l.upper() in condicao_kw), "")

    return titulo, preco, local, condicao


def dominio_ok(page, esperado):
    if not esperado:
        return True
    try:
        return esperado in (page.url or "")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# SODRÉ SANTORO — veículos (SPA/Nuxt, texto renderizado de cada link "/lote/")
# ---------------------------------------------------------------------------
def scrape_sodre(page, termo):
    url = f"https://www.sodresantoro.com.br/veiculos/lotes?term={quote(termo)}&sort=auction_date_init_asc"
    itens = []
    try:
        page.goto(url, timeout=TIMEOUT)
        page.wait_for_selector('a[href*="/lote/"]', timeout=10000)
        page.wait_for_timeout(800)
        if not dominio_ok(page, "sodresantoro.com.br"):
            log("   [Sodré Santoro] saiu do domínio esperado — pulando")
            return itens
    except Exception:
        return itens  # sem resultados pra esse termo agora, ou site lento/fora do ar — segue a vida

    links = page.query_selector_all('a[href*="/lote/"]')
    seen_hrefs = set()
    for link in links:
        href = link.get_attribute("href")
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        texto = link.inner_text()
        linhas = [l.strip() for l in texto.split("\n") if l.strip()]
        if len(linhas) < 3:
            continue
        lote_id = linhas[0]
        titulo = linhas[2] if len(linhas) > 2 else linhas[0]
        preco = None
        for i, l in enumerate(linhas):
            if "Lance atual" in l or "Lance inicial" in l:
                if i + 1 < len(linhas):
                    preco = linhas[i + 1]
                break
        condicao = next(
            (l for l in linhas if l.upper() in ("SEM SINISTRO", "MÉDIA MONTA", "PEQUENA MONTA", "GRANDE MONTA")),
            "",
        )
        local = next((l for l in linhas if "/" in l and l.upper() == l and len(l) < 30), "")
        itens.append(
            {
                "site": "Sodré Santoro",
                "categoria": "Veículos",
                "termo": termo,
                "id": lote_id,
                "titulo": titulo,
                "preco": preco,
                "condicao": condicao,
                "local": local,
                "url": href,
            }
        )
    return itens


# ---------------------------------------------------------------------------
# VIP LEILÕES — veículos (SSR, busca via querystring ?Filtro.Texto=...)
# ---------------------------------------------------------------------------
def scrape_vip(page, termo):
    url = f"https://www.vipleiloes.com.br/pesquisa?Filtro.Texto={quote(termo)}"
    itens = []
    try:
        page.goto(url, timeout=TIMEOUT)
        page.wait_for_timeout(2000)
        if not dominio_ok(page, "vipleiloes.com.br"):
            log("   [VIP Leilões] saiu do domínio esperado — pulando")
            return itens
    except Exception:
        return itens

    if page.locator("text=Nenhum lote encontrado").count() > 0:
        return itens

    links = page.query_selector_all('a[href*="/evento/anuncio/"]')
    seen = {}
    for link in links:
        href = link.get_attribute("href")
        if not href:
            continue
        full = href if href.startswith("http") else f"https://www.vipleiloes.com.br{href}"
        seen.setdefault(full, link)

    for full, link in seen.items():
        try:
            card_text = link.evaluate(
                "el => { let n = el; for (let i=0;i<6 && n.parentElement;i++){ "
                "n = n.parentElement; if (n.innerText && n.innerText.includes('Valor Atual')) return n.innerText; } "
                "return el.innerText; }"
            )
        except Exception:
            card_text = link.inner_text()
        linhas = [l.strip() for l in card_text.split("\n") if l.strip()]
        titulo = linhas[1] if len(linhas) > 1 else (linhas[0] if linhas else termo)
        preco = None
        for i, l in enumerate(linhas):
            if l == "Valor Atual" and i + 1 < len(linhas):
                preco = linhas[i + 1]
                break
        lote_m = re.search(r"Lote:\s*(\d+)\s*Local:\s*(\w+)", card_text)
        lote_id = lote_m.group(0) if lote_m else full
        itens.append(
            {
                "site": "VIP Leilões",
                "categoria": "Veículos",
                "termo": termo,
                "id": lote_id,
                "titulo": titulo,
                "preco": preco,
                "condicao": "",
                "local": lote_m.group(2) if lote_m else "",
                "url": full,
            }
        )
    return itens


# ---------------------------------------------------------------------------
# MEGA LEILÕES — veículos via busca (regex no texto da página) + imóveis via
# listagem completa (sem termo). Não expõe link direto por lote; mostramos o
# código do lote (ex: ML06407/J13840) pra localizar manualmente no site.
# ---------------------------------------------------------------------------
def scrape_mega(page, termo):
    url = f"https://www.megaleiloes.com.br/pesquisar?q={quote(termo)}"
    itens = []
    try:
        page.goto(url, timeout=TIMEOUT)
        page.wait_for_timeout(3000)
        if not dominio_ok(page, "megaleiloes.com.br"):
            log("   [Mega Leilões] saiu do domínio esperado — pulando")
            return itens
        body_text = page.inner_text("body")
    except Exception:
        return itens

    blocos = re.split(r"(?=R\$\s*[\d.]+,\d{2}\s*\n[^\n]+\nML\d+)", body_text)
    for bloco in blocos:
        m = re.match(
            r"R\$\s*([\d.]+,\d{2})\s*\n(.+?)\s*\n(ML\d+\s*/\s*J\d+)\s*\n([^\n]+)\n",
            bloco.strip(),
        )
        if not m:
            continue
        preco, titulo, codigo, local = m.group(1), m.group(2), m.group(3), m.group(4)
        if "FINALIZADO" in bloco:
            continue  # não interessa o que já encerrou
        status = "EM BREVE" if "EM BREVE" in bloco else "ATIVO"
        itens.append(
            {
                "site": "Mega Leilões",
                "categoria": "Veículos",
                "termo": termo,
                "id": codigo.replace(" ", ""),
                "titulo": titulo,
                "preco": preco,
                "condicao": status,
                "local": local,
                "url": None,  # busque pelo código (ex: ML06407/J13840) em megaleiloes.com.br
            }
        )
    return itens


def scrape_mega_categoria(page, url, categoria):
    """Listagem completa (sem termo de busca) pra categorias como imóveis.
    Estrutura de texto é diferente da tela de busca, então usamos outro
    parser: procuramos códigos de referência (ex: J126850) como marcador de
    cada bloco e olhamos as linhas ao redor. É best-effort — pode perder
    campos em alguns lotes com formatação fora do padrão."""
    itens = []
    try:
        page.goto(url, timeout=TIMEOUT)
        page.wait_for_timeout(2500)
        if not dominio_ok(page, "megaleiloes.com.br"):
            log(f"   [Mega Leilões/{categoria}] saiu do domínio esperado — pulando")
            return itens
        body_text = page.inner_text("body")
    except Exception as e:
        log(f"   erro em scrape_mega_categoria({categoria}): {e}")
        return itens

    linhas = [l.strip() for l in body_text.split("\n") if l.strip()]
    codigo_re = re.compile(r"^[A-Z]{1,3}\d{5,7}$")
    vistos_codigo = set()
    for i, l in enumerate(linhas):
        if not codigo_re.match(l) or l in vistos_codigo:
            continue
        vistos_codigo.add(l)
        titulo = linhas[i - 1] if i >= 1 else ""
        local = linhas[i + 1] if i + 1 < len(linhas) else ""
        preco = None
        for j in range(max(0, i - 6), i):
            m = re.search(r"R\$\s*[\d.]+,\d{2}", linhas[j])
            if m:
                preco = m.group(0)
        if not titulo or len(titulo) < 5:
            continue
        itens.append(
            {
                "site": "Mega Leilões",
                "categoria": categoria,
                "termo": "",
                "id": l,
                "titulo": titulo,
                "preco": preco,
                "condicao": "",
                "local": local,
                "url": None,
            }
        )
    return itens


# ---------------------------------------------------------------------------
# MOTOR GENÉRICO — usado pelos sites novos (Portal Zuk, Leilo.com.br,
# Freitas Leiloeiro, Superbid Exchange). Extrai lotes a partir de um seletor
# de link + parser de texto genérico. Cobre menos detalhes por lote do que
# os scrapers dedicados acima, mas evita duplicar muito código pra 4 sites
# com estrutura parecida (lista de cards com link + texto).
# ---------------------------------------------------------------------------
def raspar_generico(page, cfg, termo=None):
    if termo is not None:
        url = cfg["url_tpl"].format(termo=quote(termo))
    else:
        url = cfg["url"]

    itens = []
    try:
        page.goto(url, timeout=TIMEOUT)
        page.wait_for_timeout(cfg.get("espera_ms", 1800))
        if cfg.get("espera_sel"):
            try:
                page.wait_for_selector(cfg["espera_sel"], timeout=6000)
            except Exception:
                pass
        if not dominio_ok(page, cfg.get("dominio_esperado")):
            log(f"   [{cfg['site']}/{cfg['categoria']}] saiu do domínio esperado (possível redirecionamento) — pulando")
            return itens
    except Exception as e:
        log(f"   [{cfg['site']}/{cfg['categoria']}] erro ao carregar: {e}")
        return itens

    try:
        links = page.query_selector_all(cfg["link_sel"])
    except Exception as e:
        log(f"   [{cfg['site']}/{cfg['categoria']}] erro no seletor: {e}")
        return itens

    dominio = cfg.get("dominio_esperado", "")
    seen = set()
    for link in links:
        try:
            href = link.get_attribute("href")
        except Exception:
            continue
        if not href or href in seen:
            continue
        seen.add(href)
        try:
            texto = link.inner_text()
        except Exception:
            continue
        if not texto or len(texto.strip()) < 8:
            continue

        if href.startswith("http"):
            full = href
        else:
            full = f"https://{dominio}" + (href if href.startswith("/") else f"/{href}")

        titulo, preco, local, condicao = extrair_campos_de_texto(texto)

        if cfg.get("tipo") == "listagem_filtrada" and not bate_modelo(titulo):
            continue

        itens.append(
            {
                "site": cfg["site"],
                "categoria": cfg["categoria"],
                "termo": termo or "",
                "id": full,
                "titulo": titulo or (termo or cfg["categoria"]),
                "preco": preco,
                "condicao": condicao,
                "local": local or "",
                "url": full,
            }
        )
        if len(itens) >= cfg.get("max_itens", 300):
            break
    return itens


# Config dos sites "novos", rodados pelo motor genérico acima.
SITES_GENERICO = [
    # --- Portal Zuk (Zukerman Leilões) ---
    {
        "site": "Portal Zuk", "categoria": "Veículos", "tipo": "listagem_filtrada",
        "url": "https://www.portalzuk.com.br/leilao-de-veiculos",
        "link_sel": '.card-property a[href*="/veiculo/"]',
        "dominio_esperado": "portalzuk.com.br", "espera_ms": 1500,
    },
    {
        "site": "Portal Zuk", "categoria": "Imóveis", "tipo": "listagem_completa",
        "url": "https://www.portalzuk.com.br/leilao-de-imoveis",
        "link_sel": '.card-property a[href*="/imovel/"]',
        "dominio_esperado": "portalzuk.com.br", "espera_ms": 1500,
    },
    {
        "site": "Portal Zuk", "categoria": "Bens Diversos", "tipo": "listagem_completa",
        "url": "https://www.portalzuk.com.br/leilao-de-bens-diversos",
        "link_sel": '.card-property a[href*="/materiais/"]',
        "dominio_esperado": "portalzuk.com.br", "espera_ms": 1500,
    },
    # --- Leilo.com.br (também cobre o que era Sodré Santoro/imóveis e Grandes Leilões, que hoje redirecionam pra cá) ---
    {
        "site": "Leilo.com.br", "categoria": "Carros", "tipo": "listagem_filtrada",
        "url": "https://leilo.com.br/leilao/carros",
        "link_sel": '.carousel-hover-card a[href^="/leilao/"]',
        "dominio_esperado": "leilo.com.br", "espera_ms": 3000,
        "espera_sel": ".carousel-hover-card a",
    },
    {
        "site": "Leilo.com.br", "categoria": "Imóveis", "tipo": "listagem_completa",
        "url": "https://leilo.com.br/leilao/imoveis",
        "link_sel": '.carousel-hover-card a[href^="/leilao/"]',
        "dominio_esperado": "leilo.com.br", "espera_ms": 3000,
        "espera_sel": ".carousel-hover-card a",
    },
    {
        "site": "Leilo.com.br", "categoria": "Equipamentos", "tipo": "listagem_completa",
        "url": "https://leilo.com.br/leilao/equipamentos",
        "link_sel": '.carousel-hover-card a[href^="/leilao/"]',
        "dominio_esperado": "leilo.com.br", "espera_ms": 3000,
        "espera_sel": ".carousel-hover-card a",
    },
    # --- Freitas Leiloeiro ---
    {
        "site": "Freitas Leiloeiro", "categoria": "Veículos", "tipo": "listagem_filtrada",
        "url": "https://www.freitasleiloeiro.com.br/Leiloes/Pesquisar?query=&categoria=1",
        "link_sel": 'a[href*="/Leiloes/LoteDetalhes"]',
        "dominio_esperado": "freitasleiloeiro.com.br", "espera_ms": 1500,
    },
    {
        "site": "Freitas Leiloeiro", "categoria": "Imóveis", "tipo": "listagem_completa",
        "url": "https://www.freitasleiloeiro.com.br/Leiloes/Pesquisar?query=&categoria=2",
        "link_sel": 'a[href*="/Leiloes/LoteDetalhes"]',
        "dominio_esperado": "freitasleiloeiro.com.br", "espera_ms": 1500,
    },
    {
        "site": "Freitas Leiloeiro", "categoria": "Materiais", "tipo": "listagem_completa",
        "url": "https://www.freitasleiloeiro.com.br/Leiloes/Pesquisar?query=&categoria=3",
        "link_sel": 'a[href*="/Leiloes/LoteDetalhes"]',
        "dominio_esperado": "freitasleiloeiro.com.br", "espera_ms": 1500,
    },
    # --- Superbid Exchange ---
    {
        "site": "Superbid Exchange", "categoria": "Imóveis", "tipo": "listagem_completa",
        "url": "https://www.superbid.net/categorias/imoveis",
        "link_sel": 'a[href*="/oferta/"]',
        "dominio_esperado": "superbid.net", "espera_ms": 1500,
    },
    {
        "site": "Superbid Exchange", "categoria": "Diversos", "tipo": "listagem_completa",
        "url": "https://www.superbid.net/categorias/oportunidades",
        "link_sel": 'a[href*="/oferta/"]',
        "dominio_esperado": "superbid.net", "espera_ms": 1500,
    },
]

# Site com busca por termo funcional (Superbid): roda uma vez por modelo.
SITE_SUPERBID_BUSCA = {
    "site": "Superbid Exchange", "categoria": "Veículos", "tipo": "busca_por_termo",
    "url_tpl": "https://www.superbid.net/busca/{termo}",
    "link_sel": 'a[href*="/oferta/"]',
    "dominio_esperado": "superbid.net", "espera_ms": 1500,
}


# ---------------------------------------------------------------------------
# ORQUESTRAÇÃO
# ---------------------------------------------------------------------------
def carregar_vistos():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def salvar_vistos(vistos):
    STATE_FILE.write_text(json.dumps(sorted(vistos), ensure_ascii=False, indent=2), encoding="utf-8")


def gerar_relatorio_html(itens, novos_ids):
    sites = sorted({it["site"] for it in itens})
    categorias = sorted({it.get("categoria", "") for it in itens})
    novos_count = sum(1 for it in itens if f"{it['site']}|{it.get('categoria','')}|{it['id']}" in novos_ids)

    linhas = []
    for it in itens:
        chave = f"{it['site']}|{it.get('categoria','')}|{it['id']}"
        eh_novo = chave in novos_ids
        link = f'<a href="{it["url"]}" target="_blank">abrir</a>' if it.get("url") else f'(busque "{it["id"]}" no site)'
        badge = ' <span class="novo">NOVO</span>' if eh_novo else ""
        linhas.append(
            f'<tr data-site="{it["site"]}" data-categoria="{it.get("categoria","")}" data-novo="{"1" if eh_novo else "0"}">'
            f"<td>{it['site']}</td><td>{it.get('categoria','')}</td><td>{it['titulo']}{badge}</td>"
            f"<td>{it.get('preco') or '-'}</td><td>{it.get('condicao') or '-'}</td>"
            f"<td>{it.get('local') or '-'}</td><td>{link}</td>"
            "</tr>"
        )

    opcoes_site = "".join(f'<option value="{s}">{s}</option>' for s in sites)
    opcoes_cat = "".join(f'<option value="{c}">{c}</option>' for c in categorias if c)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de Leilões</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background:#f7f7f8; margin:0; padding:24px; color:#1a1a1a; }}
h1 {{ font-size: 20px; }}
table {{ width:100%; border-collapse: collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.1); }}
th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid #eee; font-size:14px; }}
th {{ background:#111; color:#fff; }}
tr:hover {{ background:#fafafa; }}
.meta {{ color:#666; font-size:13px; margin-bottom:16px; }}
.filtros {{ margin-bottom:16px; display:flex; gap:12px; flex-wrap:wrap; }}
.filtros select, .filtros label {{ padding:6px 10px; border-radius:6px; border:1px solid #ccc; font-size:14px; background:#fff; }}
.novo {{ background:#e6f4ea; color:#1a7f37; font-size:11px; font-weight:600; padding:2px 6px; border-radius:4px; }}
@media (max-width: 700px) {{
  table, thead, tbody, th, td, tr {{ display:block; }}
  th {{ display:none; }}
  tr {{ background:#fff; border-radius:8px; margin-bottom:10px; padding:8px 12px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  td {{ border:none; padding:4px 0; }}
  td:before {{ content: attr(data-label); font-weight:600; display:block; font-size:11px; color:#888; }}
}}
</style></head>
<body>
<h1>Monitor de Leilões</h1>
<div class="meta">Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC · {len(itens)} lote(s) no total · {novos_count} novo(s) desde a última checagem · atualiza automaticamente toda semana</div>
<div class="filtros">
  <select id="filtroSite"><option value="">Todos os sites</option>{opcoes_site}</select>
  <select id="filtroCategoria"><option value="">Todas as categorias</option>{opcoes_cat}</select>
  <label><input type="checkbox" id="filtroNovos"> só novidades</label>
</div>
<table id="tabela">
<tr><th>Site</th><th>Categoria</th><th>Título</th><th>Preço</th><th>Condição</th><th>Local</th><th>Link</th></tr>
{''.join(linhas) if linhas else '<tr><td colspan="7">Nenhum lote encontrado nessa checagem.</td></tr>'}
</table>
<script>
function filtrar() {{
  var site = document.getElementById('filtroSite').value;
  var cat = document.getElementById('filtroCategoria').value;
  var soNovos = document.getElementById('filtroNovos').checked;
  var linhas = document.querySelectorAll('#tabela tr[data-site]');
  linhas.forEach(function(tr) {{
    var mostraSite = !site || tr.getAttribute('data-site') === site;
    var mostraCat = !cat || tr.getAttribute('data-categoria') === cat;
    var mostraNovo = !soNovos || tr.getAttribute('data-novo') === '1';
    tr.style.display = (mostraSite && mostraCat && mostraNovo) ? '' : 'none';
  }});
}}
document.getElementById('filtroSite').addEventListener('change', filtrar);
document.getElementById('filtroCategoria').addEventListener('change', filtrar);
document.getElementById('filtroNovos').addEventListener('change', filtrar);
</script>
</body></html>"""
    REPORT_FILE.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Monitor de leilões (veículos, imóveis e bens diversos)")
    parser.add_argument("--so-veiculos", action="store_true", help="roda só as categorias de veículos (mais rápido)")
    args = parser.parse_args()

    vistos = carregar_vistos()
    todos = []

    log(f"Checando {len(MODELOS)} modelos de veículo + (se --so-veiculos não for usado) imóveis/diversos em 7 leiloeiros...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        # fecha automaticamente qualquer popup/aba nova que abrir sozinha
        # (proteção contra os redirecionamentos automáticos observados em
        # alguns desses sites)
        page = context.new_page()

        def fechar_popup_extra(pagina_nova):
            if pagina_nova != page:
                try:
                    pagina_nova.close()
                except Exception:
                    pass

        context.on("page", fechar_popup_extra)
        page.set_extra_http_headers({"Accept-Language": "pt-BR,pt;q=0.9"})

        # --- Veículos: sites com busca por termo (roda uma vez por modelo) ---
        for termo in MODELOS:
            log(f"-> veículos: {termo}")
            for scraper in (scrape_sodre, scrape_vip, scrape_mega):
                try:
                    itens = scraper(page, termo)
                except Exception as e:
                    log(f"   erro em {scraper.__name__} para '{termo}': {e}")
                    itens = []
                todos.extend(itens)
            try:
                itens = raspar_generico(page, SITE_SUPERBID_BUSCA, termo=termo)
            except Exception as e:
                log(f"   erro em Superbid Exchange para '{termo}': {e}")
                itens = []
            todos.extend(itens)

        # --- Veículos: sites sem busca funcional (baixa tudo, filtra aqui) ---
        for cfg in SITES_GENERICO:
            if cfg["categoria"] not in ("Carros", "Veículos"):
                continue
            log(f"-> {cfg['site']} / {cfg['categoria']} (filtrando pelos modelos configurados)")
            try:
                itens = raspar_generico(page, cfg)
            except Exception as e:
                log(f"   erro em {cfg['site']}/{cfg['categoria']}: {e}")
                itens = []
            todos.extend(itens)

        if not args.so_veiculos:
            # --- Imóveis e bens diversos: mostra tudo, sem filtro ---
            log("-> Mega Leilões / Imóveis (listagem completa)")
            try:
                todos.extend(scrape_mega_categoria(page, "https://www.megaleiloes.com.br/imoveis", "Imóveis"))
            except Exception as e:
                log(f"   erro em Mega Leilões/Imóveis: {e}")

            for cfg in SITES_GENERICO:
                if cfg["categoria"] in ("Carros", "Veículos"):
                    continue
                log(f"-> {cfg['site']} / {cfg['categoria']} (tudo, sem filtro)")
                try:
                    itens = raspar_generico(page, cfg)
                except Exception as e:
                    log(f"   erro em {cfg['site']}/{cfg['categoria']}: {e}")
                    itens = []
                todos.extend(itens)

        browser.close()

    novos = []
    for it in todos:
        chave = f"{it['site']}|{it.get('categoria','')}|{it['id']}"
        if chave not in vistos:
            novos.append(it)
        vistos.add(chave)

    novos_ids = {f"{it['site']}|{it.get('categoria','')}|{it['id']}" for it in novos}
    gerar_relatorio_html(todos, novos_ids)
    salvar_vistos(vistos)

    log(f"Total encontrado: {len(todos)} | Novos desde a última vez: {len(novos)}")
    log(f"Relatório salvo em: {REPORT_FILE}")


if __name__ == "__main__":
    main()
