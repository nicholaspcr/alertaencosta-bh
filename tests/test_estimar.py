import json
from dataclasses import replace

import pandas as pd
import pytest

from alertaencosta import config, estimar, modelos
from alertaencosta.atributos import SerieHoraria, tabela_atual
from alertaencosta.fonte_chuva import ErroColeta, Leituras
from tests.conftest import serie

AGORA = pd.Timestamp("2026-11-07T21:10:00Z")


def _coleta(horas_atraso: int = 1, valor: float = 0.2, ausentes=None) -> estimar.Coleta:
    fim = AGORA.floor("h") - pd.Timedelta(hours=horas_atraso - 1)
    inicio = fim - pd.Timedelta(days=31)
    horas = int((fim - inicio) / pd.Timedelta(hours=1)) + 1
    partes = [serie(p, str(inicio), horas, valor, ausentes) for p in config.PONTOS]
    return estimar.Coleta(pd.concat(partes, ignore_index=True), "Open-Meteo (gravado)", 2)


def _por_regional(estimativas):
    return {r["regional"]: r for r in estimativas["regionais"]}


def _com_contagens(versao, n):
    info = {**versao.info, "contagens_faixa_72h": {r: [n] * 5 for r in config.REGIONAIS}}
    return replace(versao, info=info)


@pytest.mark.parametrize("atraso,calculado", [(47, True), (49, False)])
def test_ti07_idade_do_dado(versao_treinada, atraso, calculado):
    versao, _ = versao_treinada
    e = estimar.estimar(_com_contagens(versao, 100), _coleta(horas_atraso=atraso), AGORA)
    estados = {r["estado"] for r in e["regionais"]}
    assert estados == ({"calculado"} if calculado else {"dados_insuficientes"})
    if not calculado:
        assert all(r["nivel"] is None and r["probabilidade"] is None for r in e["regionais"])


def test_ti05_chuva_zero_e_leitura_valida(versao_treinada):
    versao, _ = versao_treinada
    e = estimar.estimar(_com_contagens(versao, 100), _coleta(valor=0.0), AGORA)
    assert all(r["estado"] == "calculado" and r["chuva_72h_mm"] == 0 for r in e["regionais"])


@pytest.mark.parametrize("n,calculado", [(29, False), (30, True)])
def test_ti08_volume_de_vistorias(versao_treinada, n, calculado):
    versao, _ = versao_treinada
    e = estimar.estimar(_com_contagens(versao, n), _coleta(), AGORA)
    assert all((r["estado"] == "calculado") is calculado for r in e["regionais"])


def test_ti09_horas_ausentes_demais_na_producao(versao_treinada):
    versao, _ = versao_treinada
    horas = 31 * 24 + 1
    ausentes = {horas - 1 - k for k in range(1, 9)}
    e = estimar.estimar(_com_contagens(versao, 100), _coleta(ausentes=ausentes), AGORA)
    assert {r["estado"] for r in e["regionais"]} == {"dados_insuficientes"}
    assert all(r["chuva_72h_mm"] is None for r in e["regionais"])


def test_leitura_acima_do_maximo_nao_baixa_o_nivel(versao_treinada):
    versao, _ = versao_treinada
    coleta = _coleta()
    tabela = coleta.tabela.copy()
    tabela.loc[tabela.index[-3], "precipitacao_mm"] = 500.0
    e = estimar.estimar(_com_contagens(versao, 100), replace(coleta, tabela=tabela), AGORA)
    afetado = tabela.loc[tabela.index[-3], "estacao"]
    for r in e["regionais"]:
        no_ponto = config.REGIONAL_PONTO[r["regional"]] == afetado
        assert r["estado"] == ("dados_insuficientes" if no_ponto else "calculado")
        assert (r["chuva_24h_mm"] is None) is no_ponto and (r["chuva_72h_mm"] is None) is no_ponto


def test_ti11_ti12_estimativa_igual_ao_modelo_e_evidencias(versao_treinada):
    versao, _ = versao_treinada
    v = _com_contagens(versao, 100)
    coleta = _coleta(valor=0.5)
    e = _por_regional(estimar.estimar(v, coleta, AGORA))
    fim = AGORA.floor("h")
    inicio = (AGORA - pd.Timedelta(days=estimar.DIAS_JANELA_COLETA)).floor("h")
    series = {p: SerieHoraria.de_tabela(coleta.tabela[coleta.tabela.estacao == p], inicio, fim)
              for p in config.PONTOS}
    atual = tabela_atual(series, {p: fim for p in config.PONTOS}, AGORA)
    p = modelos.probabilidade(versao.modelo, atual)
    for i, linha in atual.iterrows():
        r = e[linha["regional"]]
        assert r["probabilidade"] == pytest.approx(p[i], abs=1e-4)
        baixo, alto = r["intervalo_95"]
        assert 0 <= baixo <= alto <= 1
        assert r["chuva_24h_mm"] == pytest.approx(12.0) and r["chuva_72h_mm"] == pytest.approx(36.0)
        assert r["vistorias_na_faixa"] == 100


def test_ti14_procedencia(versao_treinada):
    versao, _ = versao_treinada
    e = estimar.estimar(versao, _coleta(), AGORA)
    assert e["versao_modelo"] == versao.id
    assert e["versao_dados"] == versao.info["versao_dados"]
    assert "Open-Meteo" in e["atribuicao"] and e["fonte_chuva"]
    assert set(e["ultima_leitura"]) == set(config.PONTOS)


def test_ti17_marcacao_de_baseline(versao_treinada):
    versao, _ = versao_treinada
    base = replace(versao, info={**versao.info, "baseline_em_uso": True})
    assert estimar.estimar(base, _coleta(), AGORA)["baseline_em_uso"] is True


def test_ti19_ti20_campos_granularidade_e_tamanho(versao_treinada, tmp_path):
    versao, _ = versao_treinada
    saida = tmp_path / "estimativas.json"
    estimar.gravar(estimar.estimar(versao, _coleta(), AGORA), saida)
    texto = saida.read_text(encoding="utf-8")
    dados = json.loads(texto)
    assert len(texto.encode()) < 20_000
    assert "_registro" not in dados
    assert [r["regional"] for r in dados["regionais"]] == list(config.REGIONAIS)
    campos = {"regional", "estado", "motivos", "nivel", "probabilidade", "intervalo_95", "chuva_24h_mm",
              "chuva_72h_mm", "faixa_72h", "vistorias_na_faixa", "ponto_chuva", "ultima_leitura"}
    assert all(set(r) == campos for r in dados["regionais"])
    for proibido in ("cod_vistoria", "vila", "logradouro", "latitude", "longitude", "coordenada"):
        assert proibido not in texto.lower()


def test_ti02_falha_na_coleta_nao_sobrescreve(versao_treinada, tmp_path, capsys):
    versao, _ = versao_treinada
    saida = tmp_path / "estimativas.json"
    saida.write_text('{"anterior": true}', encoding="utf-8")

    class FonteQueFalha:
        nome = "falha"

        def leituras(self, estacao, inicio, fim) -> Leituras:
            raise ErroColeta("HTTP 429 em api.open-meteo.com")

    codigo = estimar.executar(saida, AGORA, FonteQueFalha(), carregar=lambda: versao)
    assert codigo == 1
    assert json.loads(saida.read_text(encoding="utf-8")) == {"anterior": True}
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert registro["sucesso"] is False and "429" in registro["erro"]


def test_rf07_execucao_registra_chamadas(versao_treinada, tmp_path, capsys):
    versao, _ = versao_treinada

    class FonteGravada:
        nome = "gravada"
        chamadas = 0

        def leituras(self, estacao, inicio, fim) -> Leituras:
            self.chamadas += 1
            tabela = _coleta().tabela
            return Leituras(tabela[tabela.estacao == estacao].reset_index(drop=True), self.nome)

    assert estimar.executar(tmp_path / "e.json", AGORA, FonteGravada(), carregar=lambda: versao) == 0
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert registro["sucesso"] is True and registro["chamadas_open_meteo"] == 2
