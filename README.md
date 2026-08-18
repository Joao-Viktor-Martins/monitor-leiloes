# 🔨 Monitor de Leilões

Robô que verifica automaticamente lotes em 11 leiloeiros brasileiros (veículos, imóveis e bens diversos), identifica oportunidades reais com base em regras de desconto e preço, e publica os resultados em uma página web pública — sem custo de servidor e sem intervenção manual.

## O que o projeto faz

- Executa uma varredura semanal automatizada (agendada via GitHub Actions, sem depender de um computador ligado).
- Faz web scraping de 11 sites de leilão diferentes, cada um com estrutura própria de HTML.
- Aplica uma heurística de "oportunidade" (desconto entre 1a e 2a praça, ou preço abaixo de um limite por categoria) para filtrar ruído.
- Publica o resultado automaticamente como um site estático (GitHub Pages), atualizado a cada execução.
- Envia notificações push gratuitas (via ntfy) quando encontra um lote que bate com os critérios configurados.
- Permite adicionar novos sites de leilão sem escrever código, apenas configurando nome e URL.

## Stack técnica

- Python (scraping, regras de negócio, geração de HTML)
- GitHub Actions (agendamento e execução automática, sem servidor próprio)
- GitHub Pages (publicação do resultado como site estático)
- Playwright (para sites que exigem renderização de JavaScript)
- ntfy (notificações push sem necessidade de conta)

## Por que fiz esse projeto

Queria acompanhar oportunidades reais em leilões (veículos e imóveis) sem precisar checar manualmente dezenas de sites toda semana. O projeto resolve isso de ponta a ponta: coleta, filtra, publica e avisa, tudo rodando sozinho na nuvem, de graça.

---

## Como publicar sua própria versão

1. Crie um repositório público no GitHub e suba os arquivos deste projeto (scraper.py, requirements.txt, docs/, .github/workflows/).
2. Em Settings > Pages, configure o deploy a partir da branch main, pasta /docs.
3. Rode manualmente pela aba Actions > Checar leiloes > Run workflow para gerar o primeiro resultado.
4. (Opcional) Instale o app ntfy e inscreva-se no tópico configurado em NTFY_TOPIC no scraper.py para receber notificações.

A partir daí, o robô roda sozinho toda segunda-feira.

### Critério de oportunidade

- Desconto de 40% a 85% entre 1a e 2a praça (acima disso costuma ser erro de extração, não oportunidade real).
- Ou preço abaixo do limite configurado por categoria.
- Em Veículos, só conta se o título bater com um dos modelos monitorados.
- Em categorias sem filtro de conteúdo (Diversos, Bens Diversos), preço baixo sozinho não conta, só desconto de praça real.

### Personalização

- Editar modelos de veículo monitorados: lista MODELOS no topo de scraper.py.
- Adicionar um novo leiloeiro sem código: lista SITES_PERSONALIZADOS no topo de scraper.py (nome, URL e categoria opcional).
- Ajustar limites de desconto/preço: constantes DESCONTO_MINIMO_OPORTUNIDADE, DESCONTO_MAXIMO_CONFIAVEL e LIMITES_OPORTUNIDADE_POR_CATEGORIA.

### Rodando localmente (opcional)

```bash
pip install -r requirements.txt
playwright install chromium
python scraper.py
```

Isso gera docs/index.html, abra o arquivo no navegador para conferir antes de publicar.

### Limitações conhecidas

- Layouts de sites de terceiros podem mudar a qualquer momento; o robô ignora falhas pontuais e segue com os demais sites.
- Alguns sites de leilão têm proteção anti-bot que pode bloquear tráfego de datacenter (ex: GitHub Actions) sem bloquear navegação normal.
- A "oportunidade" é uma heurística, não uma avaliação de negócio, sempre confira edital, comissão do leiloeiro e condição do bem antes de decidir.

