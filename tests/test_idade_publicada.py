import pandas as pd
import pytest

from alertaencosta import idade_publicada
from alertaencosta.fonte_chuva import ErroColeta

AGORA = pd.Timestamp("2026-11-15T12:00:00Z")


@pytest.mark.parametrize("gerado_em,codigo", [("2026-11-14T13:00:00Z", 0), ("2026-11-14T11:00:00Z", 1)])
def test_pagina_publicada_velha_demais_falha(gerado_em, codigo, capsys):
    resultado = idade_publicada.conferir("https://x/estimativas.json", 24, AGORA,
                                         buscar=lambda url: {"gerado_em": gerado_em})
    assert resultado == codigo
    assert "horas" in capsys.readouterr().out


def test_pagina_inacessivel_falha():
    def falha(url):
        raise ErroColeta("HTTP 404 em x")
    assert idade_publicada.conferir("https://x/estimativas.json", 24, AGORA, buscar=falha) == 1
