"use strict";

const HORA_MS = 60 * 60 * 1000;

const FRASES_NIVEL = {
  habitual: "Parecido com a maioria das situações do histórico.",
  elevado: "Mais alto que em 3 de cada 4 situações do histórico.",
  "muito elevado": "Mais alto que em 19 de cada 20 situações do histórico.",
};

const el = (id) => document.getElementById(id);

const porcentagem = (p) => `${Math.round(p * 100)}%`;

const dataHora = (iso) =>
  new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  });

const textoChuva = (mm, horas) => {
  if (mm === null || mm === undefined) {
    return "— (sem leitura completa no período)";
  }
  return mm === 0 ? `Não choveu nas últimas ${horas} horas` : `${mm.toLocaleString("pt-BR")} mm`;
};

function comIdadeConferida(regional, idadeMaximaHoras, agoraMs) {
  const ultima = regional.ultima_leitura ? Date.parse(regional.ultima_leitura) : NaN;
  const idadeHoras = (agoraMs - ultima) / HORA_MS;
  if (Number.isFinite(idadeHoras) && idadeHoras <= idadeMaximaHoras) {
    return regional;
  }
  const motivo = `a última leitura de chuva tem mais de ${idadeMaximaHoras} horas`;
  return {
    ...regional,
    estado: "dados_insuficientes",
    nivel: null,
    probabilidade: null,
    intervalo_95: null,
    chuva_24h_mm: null,
    chuva_72h_mm: null,
    motivos: regional.motivos.includes(motivo) ? regional.motivos : [...regional.motivos, motivo],
  };
}

function mostrarMotivos(motivos) {
  const lista = el("motivos");
  lista.replaceChildren(
    ...motivos.map((m) => {
      const item = document.createElement("li");
      item.textContent = m;
      return item;
    }),
  );
  lista.hidden = motivos.length === 0;
}

function mostrarRegional(dados, nome) {
  const bruto = dados.regionais.find((r) => r.regional === nome);
  if (!bruto) {
    el("resultado").hidden = true;
    return;
  }
  const r = comIdadeConferida(bruto, dados.idade_maxima_horas, Date.now());
  const calculado = r.estado === "calculado";

  el("titulo-regional").textContent = `Regional ${r.regional}`;
  const nivel = el("nivel");
  nivel.className = `nivel ${calculado ? r.nivel.replace(" ", "-") : "insuficiente"}`;
  nivel.textContent = calculado ? `Nível de atenção: ${r.nivel}` : "Dados insuficientes";

  el("explicacao").textContent = calculado
    ? `${FRASES_NIVEL[r.nivel]} De cada 100 vistorias feitas em situação parecida, ` +
      `cerca de ${Math.round(r.probabilidade * 100)} tiveram risco Alto ou Muito alto.`
    : "Não mostramos um nível agora, porque:";
  mostrarMotivos(calculado ? [] : r.motivos);

  el("probabilidade").textContent = calculado ? porcentagem(r.probabilidade) : "—";
  el("intervalo").textContent = calculado
    ? `entre ${porcentagem(r.intervalo_95[0])} e ${porcentagem(r.intervalo_95[1])} ` +
      "(o valor provável está nessa faixa)"
    : "—";
  el("chuva24").textContent = textoChuva(r.chuva_24h_mm, 24);
  el("chuva72").textContent = textoChuva(r.chuva_72h_mm, 72);
  el("vistorias").textContent = `${r.vistorias_na_faixa} (chuva de ${r.faixa_72h} em 72 horas)`;
  el("nota-chuva").textContent =
    `Chuva estimada por modelo meteorológico no ponto ${r.ponto_chuva}, ` +
    `não medida em pluviômetro. Última leitura: ${r.ultima_leitura ? dataHora(r.ultima_leitura) : "—"}.`;
  el("nota-baseline").hidden = !dados.baseline_em_uso;
  el("resultado").hidden = false;
}

function mostrarProcedencia(dados) {
  el("procedencia").textContent =
    `Atualizado em ${dataHora(dados.gerado_em)}. Modelo ${dados.versao_modelo}` +
    `${dados.baseline_em_uso ? " (referência sazonal)" : ""}; dados ${dados.versao_dados}. ` +
    `Fonte da chuva: ${dados.fonte_chuva}.`;
  el("atribuicao").textContent = dados.atribuicao;
}

function preencherLista(dados) {
  const select = el("regional");
  const opcoes = dados.regionais.map((r) => {
    const opcao = document.createElement("option");
    opcao.value = r.regional;
    opcao.textContent = r.regional;
    return opcao;
  });
  const vazia = document.createElement("option");
  vazia.value = "";
  vazia.textContent = "Selecione…";
  select.replaceChildren(vazia, ...opcoes);
  select.disabled = false;
  select.addEventListener("change", () => mostrarRegional(dados, select.value));

  let pedida = "";
  try {
    pedida = decodeURIComponent(window.location.hash.slice(1)).toUpperCase();
  } catch {
    pedida = "";
  }
  if (dados.regionais.some((r) => r.regional === pedida)) {
    select.value = pedida;
    mostrarRegional(dados, pedida);
  }
}

async function iniciar() {
  try {
    const resposta = await fetch("estimativas.json", { cache: "no-store" });
    if (!resposta.ok) {
      throw new Error(`HTTP ${resposta.status}`);
    }
    const dados = await resposta.json();
    preencherLista(dados);
    mostrarProcedencia(dados);
  } catch {
    const erro = el("erro");
    erro.textContent =
      "Não foi possível carregar as estimativas agora. Os canais oficiais acima continuam valendo.";
    erro.hidden = false;
  }
}

iniciar();
