from datetime import date

import numpy as np
import pandas as pd
import pytest

from alertaencosta import config
from alertaencosta.atributos import (COLUNAS_MODELO, SerieHoraria, atributos_chuva, faixa_72h,
                                     fim_da_janela_vistoria, tabela_atual, tabela_vistorias)
from tests.conftest import serie

INICIO = pd.Timestamp("2026-09-01T00:00Z")
FIM = pd.Timestamp("2026-10-31T23:00Z")


def _serie(valor=0.0, ausentes=None):
    horas = int((FIM - INICIO) / pd.Timedelta(hours=1)) + 1
    return SerieHoraria.de_tabela(serie("A521", "2026-09-01", horas, valor, ausentes), INICIO, FIM)


def _indice(instante):
    return int((instante - INICIO) / pd.Timedelta(hours=1))


def test_janelas_somam_so_horas_lidas():
    s = _serie(valor=1.0)
    linha = atributos_chuva(s, FIM)
    assert linha["chuva_24h"] == 24 and linha["chuva_72h"] == 72 and linha["chuva_30d"] == 720
    assert linha["dias_chuva"] == 30 and linha["chuva_valida"]


def test_ti05_semana_seca_e_valida():
    linha = atributos_chuva(_serie(valor=0.0), FIM)
    assert linha["chuva_72h"] == 0 and linha["dias_chuva"] == 0 and linha["chuva_valida"]


@pytest.mark.parametrize("ausentes,valido", [(7, True), (8, False)])
def test_ti09_d07_limite_de_horas_ausentes(ausentes, valido):
    fim_i = _indice(FIM)
    s = _serie(valor=1.0, ausentes={fim_i - k for k in range(ausentes)})
    linha = atributos_chuva(s, FIM)
    assert linha["ausentes_chuva_72h"] == ausentes
    assert linha["chuva_72h"] == 72 - ausentes
    assert linha["chuva_valida"] is valido


@pytest.mark.parametrize("posicoes", [
    range(0, 8), range(32, 40), range(64, 72), range(10, 40), range(0, 72, 9),
])
def test_ti10_lacunas_em_posicoes_diferentes(posicoes):
    fim_i = _indice(FIM)
    ausentes = {fim_i - p for p in posicoes}
    linha = atributos_chuva(_serie(valor=2.0, ausentes=ausentes), FIM)
    assert linha["chuva_72h"] == 2.0 * (72 - len(ausentes))
    assert linha["chuva_valida"] is (len(ausentes) <= 7)


def test_vazamento_janela_termina_na_vespera():
    fim = fim_da_janela_vistoria(date(2024, 3, 10))
    assert fim == pd.Timestamp("2024-03-10T03:00Z")
    tempos = pd.date_range("2024-03-01", "2024-03-12", freq="h", tz="UTC")
    chuva = pd.DataFrame({"estacao": "A521", "data_hora_utc": tempos,
                          "precipitacao_mm": (tempos > fim).astype(float) * 50})
    s = SerieHoraria.de_tabela(chuva, tempos[0], tempos[-1])
    assert atributos_chuva(s, fim)["chuva_24h"] == 0


def test_ti06_treino_e_producao_geram_os_mesmos_atributos():
    gerador = np.random.default_rng(1)
    horas = int((FIM - INICIO) / pd.Timedelta(hours=1)) + 1
    tabela = serie("A521", "2026-09-01", horas)
    tabela = tabela.assign(precipitacao_mm=gerador.gamma(0.3, 2.0, len(tabela)).round(1))
    series = {p: SerieHoraria.de_tabela(tabela.assign(estacao=p), INICIO, FIM) for p in config.PONTOS}
    dia = date(2026, 10, 20)
    fim = fim_da_janela_vistoria(dia)
    vistorias = pd.DataFrame({"id_vistoria": ["1|LESTE|2026-10-20"], "cod_vistoria": ["1"], "regional": ["LESTE"],
                              "data": [pd.Timestamp(dia)], "rotulo": [1]})
    treino = tabela_vistorias(vistorias, series).iloc[0]
    producao = tabela_atual(series, {p: fim for p in config.PONTOS}, fim).set_index("regional").loc["LESTE"]
    for coluna in COLUNAS_MODELO:
        assert abs(float(treino[coluna]) - float(producao[coluna])) < 1e-9, coluna


def test_d08_sem_recorte_menor_que_regional():
    proibidas = ("vila", "endereco", "logradouro", "latitude", "longitude", "coordenada")
    assert not [c for c in COLUNAS_MODELO if any(p in c for p in proibidas)]


def test_faixas_72h():
    assert [faixa_72h(x) for x in (0, 9.9, 10, 59, 60, 250)] == [0, 0, 1, 2, 3, 4]
