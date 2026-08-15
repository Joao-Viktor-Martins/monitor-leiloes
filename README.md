# Monitor de Leilões — versão site (grátis, atualiza sozinho)

Este projeto roda uma checagem semanal automática em 11 leiloeiros
brasileiros (veículos pelos modelos configurados + imóveis e bens diversos
sem filtro, com foco extra em São Paulo capital e interior) e publica o
resultado como uma página web grátis, sem precisar de Python instalado no
seu computador nem de você clicar em nada depois de configurado. Lotes que
batem com os critérios de "boa oportunidade" (desconto grande na 2ª praça
ou preço bem abaixo do normal) ficam marcados com 🔥 e disparam uma
notificação push grátis no seu celular.

Como funciona: o GitHub roda o `scraper.py` sozinho, no horário agendado
(toda segunda), usando os servidores dele (não o seu PC). O resultado vira
a página `docs/index.html`, publicada automaticamente em um link tipo:

```
https://SEU-USUARIO.github.io/monitor-leiloes/
```

Não é um domínio .com personalizado (isso custaria dinheiro), mas é um link
real, sempre no ar, que funciona no celular e em qualquer navegador.


## Passo a passo pra publicar (uns 10 minutos, só na primeira vez)

### 1. Criar uma conta no GitHub (se ainda não tiver)
Vá em **github.com** → "Sign up" → siga o cadastro (é grátis, só precisa de
um e-mail). Esse passo é seu — eu não posso criar contas por você.

### 2. Criar um repositório novo
- Clique no `+` no canto superior direito → **"New repository"**.
- Nome: `monitor-leiloes` (pode ser outro nome, só lembre que o link do site
  vai usar esse nome).
- Deixe como **Public** (repositório privado não consegue publicar no
  GitHub Pages gratuito).
- Não marque nenhuma opção de "adicionar README" — vamos subir os arquivos
  já prontos.
- Clique em **"Create repository"**.

### 3. Subir os arquivos deste pacote
Na página do repositório recém-criado, clique no link **"uploading an
existing file"** (ou "adicionar arquivo" → "fazer upload de arquivos").
Arraste TODOS os arquivos e pastas deste pacote pra lá, mantendo a
estrutura de pastas:

```
scraper.py
requirements.txt
README.md
docs/index.html
docs/dados_vistos.json
.github/workflows/checar-leiloes.yml
```

Atenção: o GitHub às vezes esconde a pasta `.github` no arrastar-e-soltar
do navegador. Se isso acontecer, use o modo "upload files" e arraste a
pasta `.github` separadamente, ou (mais confiável) instale o **GitHub
Desktop** (app gratuito) e publique a pasta inteira por ele — é só abrir o
GitHub Desktop, "Add Local Repository", escolher esta pasta, e "Publish
repository".

Depois de subir tudo, clique em **"Commit changes"**.

### 4. Ativar o GitHub Pages
- No repositório, vá em **Settings** (aba no topo) → **Pages** (menu da
  esquerda).
- Em "Build and deployment" → "Source", escolha **"Deploy from a branch"**.
- Em "Branch", escolha **main** e a pasta **/docs**, depois **Save**.
- Espere 1-2 minutos. O GitHub vai te mostrar o link do site (algo como
  `https://seu-usuario.github.io/monitor-leiloes/`).

### 5. Rodar a primeira checagem
Por padrão, o robô só roda automaticamente toda segunda-feira. Pra ver o
resultado de verdade agora, dispare manualmente:
- Vá na aba **Actions** do repositório.
- Clique em **"Checar leilões"** na lista da esquerda.
- Clique no botão **"Run workflow"** → **"Run workflow"** de novo pra
  confirmar.
- Espere uns 3-8 minutos (ele está checando 7 sites de verdade). Quando o
  círculo ficar verde ✅, atualize a página do seu site — os resultados vão
  estar lá.

Pronto — a partir daqui ele roda sozinho toda segunda, sem você precisar
fazer nada.


## Ativar a notificação push de "oportunidade" (grátis, sem conta)

1. Instale o app **ntfy** no celular ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iPhone](https://apps.apple.com/app/ntfy/id1625396347)), ou simplesmente acesse pelo navegador do celular.
2. Dentro do app, toque em **"+"** / "Subscribe to topic" e digite exatamente:
   ```
   leiloes-joao-c1c1d7f4
   ```
   (esse "tópico" já está configurado no `scraper.py`, na constante `NTFY_TOPIC` — não precisa mexer em nada).
3. Pronto. Toda vez que o robô achar um lote novo que bate com os critérios de oportunidade (desconto de 40%+ na 2ª praça, ou preço abaixo do limite da categoria), você recebe uma notificação na hora, com os destaques.

Não precisa criar conta em lugar nenhum — o ntfy funciona só com esse "código de canal". Só um detalhe: como não tem login, qualquer pessoa que souber esse código exato também consegue se inscrever nele — não é um problema de segurança sério pra esse uso (são só resultados de leilão público), mas se quiser mais privacidade dá pra trocar `NTFY_TOPIC` no `scraper.py` por outro código mais aleatório antes de subir pro GitHub.

Pra ajustar quando conta como "oportunidade", edite no `scraper.py`:
- `DESCONTO_MINIMO_OPORTUNIDADE` (padrão: 40%)
- `LIMITES_OPORTUNIDADE_POR_CATEGORIA` (preço máximo por categoria pra contar como "barato")


## Editar os modelos de veículo procurados
Abra `scraper.py`, procure a lista `MODELOS` perto do topo do arquivo, edite
os nomes, suba o arquivo atualizado pro GitHub (Commit changes) — a próxima
rodada já usa a lista nova.


## Limitações (as mesmas da versão local)
- O layout de cada site pode mudar a qualquer momento — se algum site parar
  de trazer resultado, o robô não trava, só pula ele e segue os outros.
- Alguns sites não têm busca por palavra-chave funcional pra veículos; o
  script baixa a listagem geral e filtra pelos modelos configurados.
- Mega Leilões não expõe link direto por lote — mostra o código do lote pra
  você buscar manualmente no site.
- Categorias de imóveis/bens diversos não têm filtro de preço/local — o
  volume pode ser grande; use os filtros da própria página (site/categoria/
  só novidades/só oportunidades) pra navegar.
- Alguns sites de leilão têm proteção anti-bot que pode redirecionar
  tráfego de datacenter (como o do GitHub Actions) pra outro site — se um
  site específico zerar direto sempre que roda no GitHub mas funcionar
  normal no seu navegador, é provavelmente isso, não um bug do script.
- Rico Leilões, Alfa Leilões e Savoy Leilões (fortes no interior de SP)
  foram identificados mas não entraram no robô automático — exigem
  navegação manual. Vale checar de vez em quando à mão.
- A "oportunidade" é uma heurística (regra fixa), não uma avaliação real do
  negócio — sempre confira o edital, comissão do leiloeiro e condição do
  bem antes de decidir qualquer coisa.


## Rodando localmente (opcional, só pra testar antes de publicar)
```
pip install -r requirements.txt
playwright install chromium
python scraper.py
```
Isso gera `docs/index.html` — abra esse arquivo no navegador pra conferir
antes de subir pro GitHub.
