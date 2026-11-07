"use strict";

const NOMES_TIPO = {
  baseline: "referência sazonal (regional e mês)",
  logistica: "regressão logística",
  arvore: "árvore de decisão rasa",
};

const el = (id) => document.getElementById(id);

function linha(celulas, tag = "td") {
  const tr = document.createElement("tr");
  tr.replaceChildren(
    ...celulas.map((texto) => {
      const celula = document.createElement(tag);
      celula.textContent = texto;
      return celula;
    }),
  );
  return tr;
}

function tabela(id, cabecalho, linhas) {
  el(id).replaceChildren(linha(cabecalho, "th"), ...linhas.map((l) => linha(l)));
}

function formatar(valor) {
  return Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}

function preencher(dados) {
  const tipo = NOMES_TIPO[dados.tipo_modelo] ?? dados.tipo_modelo;
  const metricas = dados.metricas_teste[dados.tipo_modelo];
  el("modelo-vigente").textContent =
    `Versão em uso: ${dados.versao_modelo}, ${tipo}. No teste de 2025, AUC ${formatar(metricas.auc)} ` +
    `(0,5 = acaso; 1 = perfeito) e Brier ${formatar(metricas.brier)} (quanto menor, melhor).` +
    (dados.baseline_em_uso
      ? " Nenhum modelo com chuva superou a referência sazonal, por isso ela está em uso."
      : "");

  el("titulo-explicacao").textContent =
    dados.explicacao.tipo === "taxa por regional"
      ? "Taxa histórica de risco alto por regional"
      : `Pesos do modelo (${dados.explicacao.tipo})`;
  const porRegional = dados.explicacao.tipo === "taxa por regional";
  const valores = Object.entries(dados.explicacao.valores).sort((a, b) =>
    porRegional ? a[0].localeCompare(b[0], "pt-BR") : Math.abs(b[1]) - Math.abs(a[1]),
  );
  tabela("explicacao", ["Variável", "Valor"], valores.map(([k, v]) => [k, formatar(v)]));

  el("mapeamento").textContent =
    "Ponto de chuva usado por regional: " +
    Object.entries(dados.regional_ponto)
      .map(([regional, ponto]) => `${regional}: ${ponto}`)
      .join("; ") +
    ".";

  tabela(
    "historico",
    ["Versão", "Publicada em", "Modelo", "Dados"],
    dados.historico
      .slice()
      .reverse()
      .map((h) => [h.versao, h.publicada_em.slice(0, 10), NOMES_TIPO[h.tipo] ?? h.tipo, h.versao_dados]),
  );

  if (dados.comparacao_inmet) {
    el("comparacao-inmet").textContent = dados.comparacao_inmet;
  }
  if (dados.contato) {
    el("contato").textContent = dados.contato;
  }
  el("atribuicao").textContent = dados.atribuicao;
}

fetch("como-funciona.json", { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
  .then(preencher)
  .catch(() => {
    el("modelo-vigente").textContent = "Não foi possível carregar os dados da versão em uso.";
  });
