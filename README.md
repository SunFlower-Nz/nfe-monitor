# NFe Monitor

Sistema de monitoramento automático de Notas Fiscais Eletrônicas (NFe) para empresas brasileiras. Consulta os portais SEFAZ periodicamente, detecta novas NFe emitidas contra o CNPJ da empresa, envia alertas por e-mail e disponibiliza um dashboard para acompanhamento fiscal.

## Problema

Empresas brasileiras frequentemente desconhecem notas fiscais eletrônicas emitidas contra seus CNPJs até que seja tarde demais. Isso gera:
- Perda de prazos para aproveitamento de créditos fiscais
- Multas por descumprimento de obrigações acessórias
- Divergências de estoque
- Surpresas no fluxo de caixa

## Solução

O NFe Monitor automatiza todo o processo:
1. **Consulta** os portais SEFAZ em busca de novas NFe
2. **Notifica** por e-mail quando novas NFe são detectadas
3. **Dashboard** para visualização, filtragem e exportação de dados fiscais
4. **Relatórios** de gastos, fornecedores e créditos tributários

## Arquitetura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Celery     │────▶│   SEFAZ      │     │  Frontend   │
│   Workers    │     │   Portal     │     │  (Streamlit) │
│   (scraping) │◀────│   Scraper    │     │             │
└──────┬───────┘     └──────────────┘     └──────┬──────┘
       │                                         │
       ▼                                         ▼
┌──────────────┐                         ┌──────────────┐
│  PostgreSQL  │◀────────────────────────│   FastAPI    │
│  (dados)     │                         │   Backend    │
└──────────────┘                         └──────┬───────┘
                                                │
┌──────────────┐                         ┌──────▼───────┐
│    Redis     │◀────────────────────────│   Celery     │
│   (broker)   │                         │   Beat       │
└──────────────┘                         │ (agendador)  │
                                         └──────────────┘
```

## Stack Tecnológico

| Camada | Tecnologia |
|--------|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy, Alembic |
| **Fila de Tarefas** | Celery + Redis |
| **Banco de Dados** | PostgreSQL |
| **Scraping** | Playwright (headless browser) |
| **Frontend** | Streamlit |
| **Autenticação** | JWT + bcrypt |
| **Deploy** | Docker Compose |

## Como Executar

```bash
# Clonar o repositório
git clone https://github.com/SunFlower-Nz/nfe-monitor.git
cd nfe-monitor

# Copiar template de variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais

# Iniciar todos os serviços
docker compose up -d

# Executar migrações
docker compose exec api alembic upgrade head

# Acessar
# Documentação da API: http://localhost:8000/docs
# Dashboard: http://localhost:8501
```

## Estrutura do Projeto

```
nfe-monitor/
├── app/
│   ├── core/
│   │   ├── config.py            # Configurações (pydantic-settings)
│   │   ├── security.py          # JWT, hashing de senhas
│   │   └── database.py          # Engine/session SQLAlchemy
│   ├── models/
│   │   └── models.py            # Modelos do banco de dados
│   ├── scrapers/
│   │   ├── base.py              # Scraper abstrato
│   │   └── sefaz_nacional.py    # Portal Nacional NF-e
│   ├── tasks/
│   │   ├── celery_app.py        # Configuração do Celery
│   │   ├── scrape_tasks.py      # Tarefas de scraping
│   │   └── notification_tasks.py # Alertas por e-mail
│   └── main.py                  # Aplicação FastAPI
├── dashboard/
│   └── app.py                   # Dashboard Streamlit
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Licença

Todos os direitos reservados. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
