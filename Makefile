PY ?= .venv/bin/python

.PHONY: instalar testes ingestao treino publicar estimar site lote

instalar:
	python3.13 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt

testes:
	$(PY) -m pytest -q --cov=alertaencosta --cov-report=term-missing

ingestao:
	$(PY) -m alertaencosta.ingestao_chuva

treino:
	$(PY) -m alertaencosta.treino

publicar:
	$(PY) -m alertaencosta.publicar $(VERSAO)

estimar:
	$(PY) -m alertaencosta.estimar --saida site/estimativas.json

lote:
	$(PY) -m alertaencosta.carga_lote $(ARQUIVO)

site:
	$(PY) -m http.server 8000 --directory site
