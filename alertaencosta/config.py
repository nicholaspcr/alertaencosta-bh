from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "dados"
DIR_URBEL = DIR_DADOS / "urbel"
DIR_CHUVA = DIR_DADOS / "chuva"
DIR_MODELOS = RAIZ / "modelos"
DIR_SITE = RAIZ / "site"

ARQUIVO_LOTES = DIR_URBEL / "lotes.json"
ARQUIVO_SERIE = DIR_CHUVA / "serie_horaria.csv"
ARQUIVO_META_CHUVA = DIR_CHUVA / "metadados.json"
ARQUIVO_VIGENTE = DIR_MODELOS / "VIGENTE"
ARQUIVO_HISTORICO = DIR_MODELOS / "historico.json"

FUSO_BH = ZoneInfo("America/Sao_Paulo")

REGIONAIS: tuple[str, ...] = (
    "BARREIRO",
    "CENTRO-SUL",
    "LESTE",
    "NORDESTE",
    "NOROESTE",
    "NORTE",
    "OESTE",
    "PAMPULHA",
    "VENDA NOVA",
)

NIVEIS_RISCO: dict[str, str] = {
    "sem risco": "Sem risco",
    "baixo": "Baixo",
    "medio": "Médio",
    "alto": "Alto",
    "muito alto": "Muito alto",
}
NIVEIS_ROTULO_1 = frozenset({"Alto", "Muito alto"})


@dataclass(frozen=True)
class Ponto:
    codigo: str
    nome: str
    latitude: float
    longitude: float


PONTOS: dict[str, Ponto] = {
    "A521": Ponto("A521", "Pampulha", -19.8839, -43.9694),
    "F501": Ponto("F501", "Cercadinho", -19.9800, -43.9586),
}

REGIONAL_PONTO: dict[str, str] = {
    "BARREIRO": "F501",
    "CENTRO-SUL": "F501",
    "OESTE": "F501",
    "LESTE": "A521",
    "NORDESTE": "A521",
    "NOROESTE": "A521",
    "NORTE": "A521",
    "PAMPULHA": "A521",
    "VENDA NOVA": "A521",
}

INICIO_PERIODO = date(2021, 1, 1)
FIM_PERIODO = date(2025, 12, 31)
ANOS_TREINO = (2021, 2022, 2023, 2024)
ANO_TESTE = 2025
VALIDACAO_JANELA_CRESCENTE = ((2021, 2022), 2023), ((2021, 2022, 2023), 2024)

JANELAS_HORAS: dict[str, int] = {
    "chuva_24h": 24,
    "chuva_72h": 72,
    "chuva_7d": 168,
    "chuva_30d": 720,
}
DIAS_CHUVA_LIMIAR_MM = 1.0
DIAS_CHUVA_MAXIMO = 30

IDADE_MAXIMA_HORAS = 48
MIN_VISTORIAS_FAIXA = 30
MAX_FRACAO_AUSENTE = 0.10

FAIXAS_72H_MM: tuple[float, ...] = (0.0, 10.0, 30.0, 60.0, 100.0)

SEMENTE = 20261206
N_BOOTSTRAP = 200
PERCENTIS_NIVEL = (75, 95)
GRADE_C = (0.01, 0.1, 1.0, 10.0)
PROFUNDIDADE_ARVORE = 4
MIN_FOLHA_ARVORE = 30
FORCA_PRIOR_BASELINE = 20.0
MARGEM_ARVORE_AUC = 0.01

NIVEIS_ATENCAO = ("habitual", "elevado", "muito elevado")

MODELO_METEOROLOGICO = "ecmwf_ifs"
URL_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
URL_RECENTE = "https://api.open-meteo.com/v1/forecast"
DIAS_PASSADOS_RECENTE = 32
ATRIBUICAO_OPEN_METEO = (
    "Dados meteorológicos: Open-Meteo.com (CC BY 4.0), modelo ECMWF IFS."
)

CONTATO: str | None = None
ARQUIVO_COMPARACAO_INMET = DIR_DADOS / "comparacao_inmet.txt"

AVISO = (
    "Estimativa estatística. Não é alerta oficial nem laudo técnico. "
    "Em emergência, ligue para a Defesa Civil: 199."
)
