# OpenSCAP Dashboard

Dashboard local para visualizar resultados de scans OpenSCAP (xccdf-results.xml).

## Requisitos

- Python 3.6+ (sem dependências externas — usa só stdlib)

## Como usar

### 1. Rode o scan no servidor (como root)

```bash
sudo oscap xccdf eval \
  --profile xccdf_org.ssgproject.content_profile_cis_server_l2 \
  --results xccdf-results.xml \
  --report xccdf-report.html \
  /usr/share/xml/scap/ssg/content/ssg-ol9-ds.xml
```

### 2. Copie o XML para sua máquina local

```bash
scp usuario@servidor:/caminho/xccdf-results.xml .
```

### 3. Inicie o dashboard

```bash
# Passando o XML direto na inicialização:
python3 server.py xccdf-results.xml

# Ou sem argumento e faça upload pela interface:
python3 server.py
```

O browser abre automaticamente em http://localhost:8765

## O que o dashboard mostra

- Score de conformidade (%)
- Totais: pass / fail / not checked / not applicable
- Gráfico de distribuição (donut)
- Falhas por categoria (barras horizontais)
- Tabela de regras que falharam, filtráveis por severidade (alta / média / baixa)

## Segurança

O arquivo XML é processado inteiramente local — nenhum dado é enviado para a internet.
O servidor escuta apenas em localhost (127.0.0.1).
