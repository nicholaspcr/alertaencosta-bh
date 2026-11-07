import pandas as pd
import pytest

from alertaencosta.fonte_chuva import (COLUNAS, ErroColeta, OpenMeteoHistorico, OpenMeteoRecente,
                                       resposta_para_tabela)
from alertaencosta.limpeza import limpar_chuva
from tests.conftest import resposta_gravada

AGORA = pd.Timestamp("2026-11-07T21:07:00Z")
INICIO = pd.Timestamp("2026-10-10T00:00:00Z")
FIM = pd.Timestamp("2026-10-20T23:00:00Z")


def _historico():
    return OpenMeteoHistorico(buscar_json=lambda url: resposta_gravada("historico_A521.json"))


def _recente(resposta=None, agora=AGORA):
    resposta = resposta or resposta_gravada("recente_A521.json")
    return OpenMeteoRecente(agora=agora, buscar_json=lambda url: resposta)


def test_ti01_contrato_igual_nos_dois_adaptadores():
    h = _historico().leituras("A521", INICIO, FIM)
    r = _recente().leituras("A521", INICIO, FIM)
    for leituras in (h, r):
        t = leituras.tabela
        assert list(t.columns) == COLUNAS
        assert str(t["data_hora_utc"].dt.tz) == "UTC"
        assert t["data_hora_utc"].is_monotonic_increasing
        assert not t["data_hora_utc"].duplicated().any()
        assert leituras.fonte
    comum = h.tabela.merge(r.tabela, on=["estacao", "data_hora_utc"])
    assert len(comum) > 200
    assert (comum["precipitacao_mm_x"] - comum["precipitacao_mm_y"]).abs().max() <= 0.1


def test_ti02_hora_sem_valor_fica_ausente_nunca_zero():
    resposta = resposta_gravada("recente_A521.json")
    valores = list(resposta["hourly"]["precipitation"])
    valores[10] = None
    tabela = resposta_para_tabela("A521", {**resposta, "hourly": {**resposta["hourly"], "precipitation": valores}})
    assert pd.isna(tabela.loc[10, "precipitacao_mm"])
    limpa = limpar_chuva(tabela, {"A521": 100.0}, AGORA)
    assert limpa.descartes["sem_valor"] == 1
    assert tabela.loc[10, "data_hora_utc"] not in set(limpa.tabela["data_hora_utc"])


@pytest.mark.parametrize("erro", ["HTTP 429 em api.open-meteo.com", "erro de rede: timed out"])
def test_ti02_erro_http_e_de_rede_viram_erro_coleta(erro):
    def falha(url):
        raise ErroColeta(erro)
    with pytest.raises(ErroColeta):
        OpenMeteoRecente(agora=AGORA, buscar_json=falha).leituras("A521", INICIO, AGORA)


def test_ti02_horario_invalido_vira_erro_coleta():
    resposta = resposta_gravada("recente_A521.json")
    tempos = ["lixo"] * len(resposta["hourly"]["time"])
    with pytest.raises(ErroColeta):
        resposta_para_tabela("A521", {**resposta, "hourly": {**resposta["hourly"], "time": tempos}})


def test_ti02_resposta_de_erro_da_api():
    with pytest.raises(ErroColeta, match="Latitude"):
        resposta_para_tabela("A521", resposta_gravada("erro_parametro.json"))


def test_ti03_horas_de_previsao_descartadas():
    bruta = resposta_para_tabela("A521", resposta_gravada("recente_A521.json"))
    assert bruta["data_hora_utc"].max() > AGORA
    tabela = _recente().leituras("A521", AGORA - pd.Timedelta(days=32), AGORA).tabela
    assert tabela["data_hora_utc"].max() <= AGORA


def test_ti04_d06_dado_invalido_descartado_e_contado():
    tempos = pd.date_range("2026-11-01", periods=5, freq="h", tz="UTC")
    tabela = pd.DataFrame({"estacao": "A521", "data_hora_utc": [*tempos[:4], AGORA + pd.Timedelta(hours=2)],
                           "precipitacao_mm": [1.0, -0.5, 99.0, 2.0, 1.0]})
    r = limpar_chuva(tabela, {"A521": 23.5}, AGORA)
    assert r.descartes == {"sem_valor": 0, "negativa": 1, "acima_maximo": 1, "data_futura": 1}
    assert list(r.tabela["precipitacao_mm"]) == [1.0, 2.0]
