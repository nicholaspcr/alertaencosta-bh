from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from alertaencosta import config
from alertaencosta.atributos import COLUNAS_MODELO

TIPOS = ("baseline", "logistica", "arvore")


class BaselineSazonal(ClassifierMixin, BaseEstimator):
    def __init__(self, forca_prior: float = config.FORCA_PRIOR_BASELINE):
        self.forca_prior = forca_prior

    def fit(self, X: pd.DataFrame, y) -> BaselineSazonal:
        y = np.asarray(y)
        dados = pd.DataFrame({"regional": X["regional"].to_numpy(),
                              "mes": X["mes"].to_numpy(), "y": y})
        m = self.forca_prior
        self.taxa_global_ = float(y.mean())
        por_regional = dados.groupby("regional")["y"].agg(["sum", "count"])
        self.taxa_regional_ = ((por_regional["sum"] + m * self.taxa_global_)
                               / (por_regional["count"] + m)).to_dict()
        por_mes = dados.groupby(["regional", "mes"])["y"].agg(["sum", "count"])
        prior = np.array([self.taxa_regional_[r] for r, _ in por_mes.index])
        self.taxa_regional_mes_ = dict(zip(
            por_mes.index, (por_mes["sum"].to_numpy() + m * prior) / (por_mes["count"].to_numpy() + m)
        ))
        self.classes_ = np.array([0, 1])
        return self

    def _taxa(self, regional: str, mes: int) -> float:
        if (regional, mes) in self.taxa_regional_mes_:
            return float(self.taxa_regional_mes_[(regional, mes)])
        return float(self.taxa_regional_.get(regional, self.taxa_global_))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        p = np.array([self._taxa(r, m) for r, m in zip(X["regional"], X["mes"])])
        return np.column_stack([1 - p, p])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def _seletor(escalar: bool) -> ColumnTransformer:
    transformador = StandardScaler() if escalar else "passthrough"
    return ColumnTransformer([("atributos", transformador, COLUNAS_MODELO)], remainder="drop")


def regressao_logistica(C: float) -> Pipeline:
    return Pipeline([
        ("selecao", _seletor(escalar=True)),
        ("modelo", LogisticRegression(C=C, max_iter=2000)),
    ])


def arvore_rasa() -> Pipeline:
    return Pipeline([
        ("selecao", _seletor(escalar=False)),
        ("modelo", DecisionTreeClassifier(
            max_depth=config.PROFUNDIDADE_ARVORE,
            min_samples_leaf=config.MIN_FOLHA_ARVORE,
            random_state=config.SEMENTE,
        )),
    ])


def probabilidade(modelo, X: pd.DataFrame) -> np.ndarray:
    return modelo.predict_proba(X)[:, 1]


def bootstrap(modelo, X: pd.DataFrame, y: pd.Series, n: int = config.N_BOOTSTRAP,
              semente: int = config.SEMENTE) -> list:
    gerador = np.random.default_rng(semente)
    y = np.asarray(y)
    replicas = []
    for _ in range(n):
        indices = gerador.integers(0, len(X), size=len(X))
        replicas.append(clone(modelo).fit(X.iloc[indices], y[indices]))
    return replicas


def intervalo(replicas: list, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    estimativas = np.vstack([probabilidade(r, X) for r in replicas])
    return np.percentile(estimativas, 2.5, axis=0), np.percentile(estimativas, 97.5, axis=0)


def limiares(probabilidades_treino: np.ndarray) -> tuple[float, float]:
    p75, p95 = np.percentile(probabilidades_treino, config.PERCENTIS_NIVEL)
    return float(p75), float(p95)


def nivel(p: float, limites: tuple[float, float]) -> str:
    p75, p95 = limites
    if p >= p95:
        return config.NIVEIS_ATENCAO[2]
    if p >= p75:
        return config.NIVEIS_ATENCAO[1]
    return config.NIVEIS_ATENCAO[0]


def explicacao(tipo: str, modelo) -> dict:
    if tipo == "logistica":
        reg = modelo.named_steps["modelo"]
        return {
            "tipo": "coeficientes padronizados",
            "intercepto": float(reg.intercept_[0]),
            "valores": dict(zip(COLUNAS_MODELO, map(float, reg.coef_[0]))),
        }
    if tipo == "arvore":
        arvore = modelo.named_steps["modelo"]
        return {
            "tipo": "importância das variáveis",
            "valores": dict(zip(COLUNAS_MODELO, map(float, arvore.feature_importances_))),
        }
    return {
        "tipo": "taxa por regional",
        "valores": {r: float(v) for r, v in modelo.taxa_regional_.items()},
    }
