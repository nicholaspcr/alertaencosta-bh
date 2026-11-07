import json
import shutil

import numpy as np
import pandas as pd
import pytest

from alertaencosta import avaliacao, modelos, publicar, treino, versoes


def test_ti16_um_comando_gera_versao_com_relatorio(versao_treinada, ambiente_sintetico):
    versao, _ = versao_treinada
    pasta = ambiente_sintetico["modelos"] / versao.id
    relatorio = (pasta / "relatorio.md").read_text(encoding="utf-8")
    assert "M-01" in relatorio and "M-02" in relatorio and "M-04" in relatorio
    assert "PENDENTE DE REVISÃO HUMANA" in relatorio
    assert set(versao.info["metricas_teste"]) == {"baseline", "logistica", "arvore"}


def test_m01_modelo_com_chuva_vence_baseline_quando_ha_sinal(versao_treinada):
    versao, _ = versao_treinada
    m = versao.info["metricas_teste"]
    assert versao.info["tipo"] in ("logistica", "arvore")
    assert avaliacao.supera_baseline(m[versao.info["tipo"]], m["baseline"])


def test_ti17_candidato_que_perde_publica_baseline():
    metricas = {"baseline": {"auc": 0.60, "brier": 0.18},
                "logistica": {"auc": 0.58, "brier": 0.17},
                "arvore": {"auc": 0.61, "brier": 0.19}}
    assert treino.escolher_modelo(metricas, {"logistica": [], "arvore": []}) == "baseline"


def test_m06_reprovado_na_monotonia_nao_e_escolhido():
    metricas = {"baseline": {"auc": 0.6, "brier": 0.18},
                "logistica": {"auc": 0.7, "brier": 0.16},
                "arvore": {"auc": 0.72, "brier": 0.15}}
    assert treino.escolher_modelo(metricas, {"logistica": [("LESTE", 1)], "arvore": []}) == "arvore"
    assert treino.escolher_modelo(metricas, {"logistica": [], "arvore": []}) == "arvore"
    sem_margem = {**metricas, "arvore": {"auc": 0.705, "brier": 0.155}}
    assert treino.escolher_modelo(sem_margem, {"logistica": [], "arvore": []}) == "logistica"


def test_m06_modelo_escolhido_monotono_na_chuva(versao_treinada):
    versao, _ = versao_treinada
    assert avaliacao.monotonia(versao.modelo) == []


def test_m08_reproducao_com_mesma_semente(versao_treinada, ambiente_sintetico, tmp_path):
    versao, entradas = versao_treinada
    _, info = treino.treinar(entradas, tmp_path, n_bootstrap=10)
    for tipo, m in versao.info["metricas_teste"].items():
        assert abs(info["metricas_teste"][tipo]["auc"] - m["auc"]) < 1e-6
        assert abs(info["metricas_teste"][tipo]["brier"] - m["brier"]) < 1e-6


def test_m10_limiares_gravados_e_reproduzidos(versao_treinada):
    versao, entradas = versao_treinada
    conjunto = treino.montar_conjunto(entradas)
    treino_df = avaliacao.dividir(conjunto.tabela).treino
    p = modelos.probabilidade(versao.modelo, treino_df)
    assert tuple(versao.info["limiares"]) == pytest.approx(modelos.limiares(p))


def test_m09_tempo_de_treino_registrado(versao_treinada):
    versao, _ = versao_treinada
    assert 0 < versao.info["tempo_treino_s"] < 30 * 60


def test_ti13_conversao_em_nivel_nos_limiares():
    limites = (0.30, 0.45)
    assert modelos.nivel(0.2999, limites) == "habitual"
    assert modelos.nivel(0.30, limites) == "elevado"
    assert modelos.nivel(0.4499, limites) == "elevado"
    assert modelos.nivel(0.45, limites) == "muito elevado"


def test_intervalo_contem_estimativa(versao_treinada):
    versao, entradas = versao_treinada
    amostra = treino.montar_conjunto(entradas).tabela.head(50)
    p = modelos.probabilidade(versao.modelo, amostra)
    baixo, alto = modelos.intervalo(versao.replicas, amostra)
    assert np.all((0 <= baixo) & (baixo <= alto) & (alto <= 1))
    assert np.mean((baixo <= p) & (p <= alto)) > 0.9


def test_vazamento_tres_testes(versao_treinada):
    _, entradas = versao_treinada
    divisao = avaliacao.dividir(treino.montar_conjunto(entradas).tabela)
    avaliacao.checar_vazamento(divisao)
    misturada = avaliacao.Divisao(pd.concat([divisao.treino, divisao.teste.head(1)]), divisao.teste)
    with pytest.raises(avaliacao.ErroVazamento):
        avaliacao.checar_vazamento(misturada)
    adiantada = divisao.treino.assign(fim_janela_utc=divisao.treino["fim_janela_utc"] + pd.Timedelta(hours=1))
    with pytest.raises(avaliacao.ErroVazamento):
        avaliacao.checar_vazamento(avaliacao.Divisao(adiantada, divisao.teste))


def test_baseline_suaviza_para_taxa_da_regional():
    X = pd.DataFrame({"regional": ["LESTE"] * 10 + ["OESTE"] * 10, "mes": [1] * 20})
    y = [1] * 10 + [0] * 10
    b = modelos.BaselineSazonal(forca_prior=10).fit(X, y)
    p = b.predict_proba(pd.DataFrame({"regional": ["LESTE", "OESTE", "NORTE"], "mes": [1, 1, 5]}))[:, 1]
    assert p[0] > p[1] and 0 < p[1] < 1 and p[2] == pytest.approx(0.5)


def test_ti18_publicar_e_reverter(versao_treinada, ambiente_sintetico, tmp_path):
    versao, entradas = versao_treinada
    pasta = tmp_path / "modelos"
    shutil.copytree(ambiente_sintetico["modelos"] / versao.id, pasta / versao.id)
    (tmp_path / "site").mkdir()
    publicar.publicar(versao.id, pasta, tmp_path / "site")
    id_novo, _ = treino.treinar(entradas, pasta, n_bootstrap=5)
    publicar.publicar(id_novo, pasta, tmp_path / "site")
    assert versoes.id_vigente(pasta / "VIGENTE") == id_novo
    publicar.publicar(versao.id, pasta, tmp_path / "site")
    assert versoes.id_vigente(pasta / "VIGENTE") == versao.id
    como = json.loads((tmp_path / "site" / "como-funciona.json").read_text(encoding="utf-8"))
    assert [h["versao"] for h in como["historico"]] == [versao.id, id_novo, versao.id]
    assert como["explicacao"]["valores"]


def test_publicar_versao_inexistente(tmp_path):
    with pytest.raises(versoes.ErroVersao):
        versoes.publicar("modelo-1900.01.01", tmp_path)
    assert not (tmp_path / "VIGENTE").exists()
    assert publicar.main([]) == 2
