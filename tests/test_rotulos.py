from datetime import date

import pytest

from alertaencosta.carga_lote import adicionar_lote
from alertaencosta.rotulos import EspecificacaoLote, ErroLote, carregar_lotes, ler_lote, sha256_arquivo
from tests.conftest import escrever_csv_vistorias

HOJE = date(2026, 11, 7)
BOAS = [
    ("1", "Barreiro", "10/01/2024", "Alto"),
    ("2", "VENDA NOVA", "11/01/2024 09:30", "muito alto"),
    ("3", "Centro-Sul", "12/01/2024", "Médio"),
]


def _ler(caminho, **kwargs):
    espec = EspecificacaoLote(arquivo=caminho.name, sha256="", **kwargs)
    return ler_lote(caminho, espec, HOJE)


def test_d01_lote_valido_e_rotulo(tmp_path):
    r = _ler(escrever_csv_vistorias(tmp_path / "a.csv", BOAS))
    assert list(r.tabela["rotulo"]) == [1, 1, 0]
    assert set(r.tabela["regional"]) == {"BARREIRO", "VENDA NOVA", "CENTRO-SUL"}


@pytest.mark.parametrize("cabecalho", [
    "COD_VISTORIA;REGIONAL;DATA_EXECUCAO_VISTORIA",
    "COD_VISTORIA;REGIONAL;DATA;NIVEL_RISCO",
])
def test_d01_ti15_esquema_invalido_rejeitado(tmp_path, cabecalho):
    caminho = escrever_csv_vistorias(tmp_path / "a.csv", BOAS, cabecalho)
    with pytest.raises(ErroLote):
        _ler(caminho)


def test_d01_cabecalho_trocado_detectado_pelo_conteudo(tmp_path):
    trocadas = [(c, d, r, n) for c, r, d, n in BOAS]
    caminho = escrever_csv_vistorias(tmp_path / "a.csv", trocadas)
    with pytest.raises(ErroLote, match="data"):
        _ler(caminho)
    corrigido = _ler(caminho, ordem_colunas=("cod_vistoria", "data", "regional", "nivel_risco"))
    assert len(corrigido.tabela) == 3


def test_d03_regional_fora_da_lista_rejeita(tmp_path):
    caminho = escrever_csv_vistorias(tmp_path / "a.csv", [*BOAS, ("9", "Contagem", "01/02/2024", "Alto")])
    with pytest.raises(ErroLote, match="regional"):
        _ler(caminho)


def test_d04_nivel_vazio_sai_e_desconhecido_rejeita(tmp_path):
    vazio = _ler(escrever_csv_vistorias(tmp_path / "a.csv", [*BOAS, ("4", "Leste", "01/02/2024", "")]))
    assert len(vazio.tabela) == 3
    assert list(vazio.descartados["motivo"]) == ["nivel_vazio"]
    with pytest.raises(ErroLote, match="nível"):
        _ler(escrever_csv_vistorias(tmp_path / "b.csv", [*BOAS, ("5", "Leste", "01/02/2024", "Crítico")]))


def test_d04_nivel_extra_registrado_no_manifesto(tmp_path):
    caminho = escrever_csv_vistorias(tmp_path / "a.csv", [("1", "Leste", "01/02/2024", "Muito baixo")])
    r = _ler(caminho, niveis_extras={"Muito baixo": "Baixo"})
    assert r.tabela.loc[0, "rotulo"] == 0


def test_d05_datas_invalidas_e_futuras_descartadas(tmp_path):
    linhas = [*BOAS, ("6", "Leste", "31/02/2024", "Alto"), ("7", "Leste", "01/01/2047", "Alto")]
    r = _ler(escrever_csv_vistorias(tmp_path / "a.csv", linhas))
    assert sorted(r.descartados["motivo"]) == ["data_futura", "data_invalida"]


def test_d02_vistoria_repetida_removida_e_contada(tmp_path):
    a = escrever_csv_vistorias(tmp_path / "a.csv", BOAS)
    b = escrever_csv_vistorias(tmp_path / "b.csv", [("1", "Barreiro", "10/01/2024", "Baixo")])
    manifesto = tmp_path / "lotes.json"
    manifesto.write_text(
        '{"lotes": [{"arquivo": "a.csv", "sha256": "%s"}, {"arquivo": "b.csv", "sha256": "%s"}]}'
        % (sha256_arquivo(a), sha256_arquivo(b)), encoding="utf-8")
    r = carregar_lotes(manifesto, HOJE)
    assert len(r.tabela) == 3
    assert r.tabela.set_index("cod_vistoria").loc["1", "nivel_risco"] == "Baixo"
    assert (r.descartados["motivo"] == "vistoria_repetida").sum() == 1


def test_d02_codigo_reutilizado_em_outra_vistoria_e_mantido(tmp_path):
    linhas = [("1", "Barreiro", "10/01/2024", "Alto"), ("1", "Leste", "03/05/2024", "Baixo")]
    a = escrever_csv_vistorias(tmp_path / "a.csv", linhas)
    manifesto = tmp_path / "lotes.json"
    manifesto.write_text('{"lotes": [{"arquivo": "a.csv", "sha256": "%s"}]}' % sha256_arquivo(a),
                         encoding="utf-8")
    r = carregar_lotes(manifesto, HOJE)
    assert len(r.tabela) == 2 and r.tabela["id_vistoria"].is_unique


def test_hash_diferente_do_manifesto_rejeita(tmp_path):
    escrever_csv_vistorias(tmp_path / "a.csv", BOAS)
    manifesto = tmp_path / "lotes.json"
    manifesto.write_text('{"lotes": [{"arquivo": "a.csv", "sha256": "0"}]}', encoding="utf-8")
    with pytest.raises(ErroLote, match="hash"):
        carregar_lotes(manifesto, HOJE)


def test_ti15_lote_invalido_nao_altera_base_vigente(tmp_path):
    base = escrever_csv_vistorias(tmp_path / "base.csv", BOAS)
    manifesto = tmp_path / "lotes.json"
    manifesto.write_text('{"lotes": [{"arquivo": "base.csv", "sha256": "%s"}]}' % sha256_arquivo(base),
                         encoding="utf-8")
    antes = (sha256_arquivo(manifesto), sha256_arquivo(base))
    novos = tmp_path / "novo"
    novos.mkdir()
    ruins = [
        escrever_csv_vistorias(novos / "ausente.csv", BOAS, "COD_VISTORIA;REGIONAL;NIVEL_RISCO"),
        escrever_csv_vistorias(novos / "renomeada.csv", BOAS, "COD;REGIONAL;DATA_EXECUCAO_VISTORIA;NIVEL_RISCO"),
        escrever_csv_vistorias(novos / "nivel.csv", [("8", "Leste", "01/02/2024", "Gravíssimo")]),
    ]
    for ruim in ruins:
        with pytest.raises(ErroLote):
            adicionar_lote(ruim, arquivo_lotes=manifesto, hoje=HOJE)
    assert (sha256_arquivo(manifesto), sha256_arquivo(base)) == antes
    assert sorted(p.name for p in tmp_path.glob("*.csv")) == ["base.csv"]


def test_rf08_lote_valido_entra_no_manifesto(tmp_path):
    base = escrever_csv_vistorias(tmp_path / "base.csv", BOAS)
    manifesto = tmp_path / "lotes.json"
    manifesto.write_text('{"lotes": [{"arquivo": "base.csv", "sha256": "%s"}]}' % sha256_arquivo(base),
                         encoding="utf-8")
    novos = tmp_path / "novo"
    novos.mkdir()
    novo = escrever_csv_vistorias(novos / "lote2.csv", [("10", "Norte", "01/03/2026", "Alto")])
    adicionar_lote(novo, arquivo_lotes=manifesto, hoje=HOJE)
    assert len(carregar_lotes(manifesto, HOJE).tabela) == 4
