# Registro de decisões

Decisões tomadas na implementação que a Arquitetura, a Lista de Requisitos ou o Plano de Testes não fixavam, ou que os dados reais obrigaram a ajustar. Itens marcados **A CONFIRMAR** foram escolhidos sem dado que os sustente e devem ser revistos pelo time.

## Dados das vistorias (URBEL)

- **Arquivos usados (07/11/2026):** recursos 2021_09, 2022, 2023, 2024 e 2025 do conjunto "Vistorias realizadas em assentamentos de interesse social com classificação de risco". Os recursos marcados "DESATIVADO" no portal não entram. O arquivo de 2021 traz vistorias desde 1995; só 2021–2025 entram no modelo.
- **Variações de cabeçalho aceitas:** `DATA_EEXECUÇÃO` e `NÍVEL RISCO GEOLOGICO` (lote 2025) são aceitos como nomes conhecidos das colunas de data e nível. Qualquer outro nome é rejeitado (RF08).
- **Lote 2024 com cabeçalho trocado:** o cabeçalho diz `REGIONAL;DATA_EXECUCAO_VISTORIA`, mas os dados vêm em `DATA;REGIONAL`. A carga detecta isso (a coluna "data" não contém datas) e rejeita o arquivo. A ordem real está registrada no manifesto (`ordem_colunas`).
- **Nível "Muito baixo" (2 linhas do lote 2022):** não é um dos cinco níveis oficiais. Foi tratado como "Baixo" por decisão registrada no manifesto; o rótulo é 0 nos dois casos, então o modelo não muda.
- **Código reutilizado (D-02):** o `COD_VISTORIA` da URBEL não é único. O mesmo código aparece em vistorias com outra regional e outra data (692 códigos em 2021–2025, quase todos dentro do mesmo arquivo). A vistoria é identificada por código, regional e data (`id_vistoria`). Só a repetição exata dessa chave é descartada, valendo o lote mais recente do manifesto; as repetições são contadas no relatório. O teste contra vazamento usa a mesma chave.
- **Data com hora:** os lotes de 2023 em diante trazem hora. A janela de chuva continua terminando às 23h59 da véspera, como na Arquitetura, para manter um só critério em todos os anos.
- **Lacuna em 2023-S2:** só 5 vistorias válidas no segundo semestre de 2023 (muitos níveis em branco). Aparece na tabela de prevalência do relatório.

## Chuva

- **Convenção de tempo:** o valor horário do Open-Meteo no rótulo T é a chuva de (T−1 h, T]. Uma janela de N horas que termina em `fim` soma os rótulos em (fim − N h, fim]. Para uma vistoria, `fim` é a meia-noite local do dia da vistoria, então a janela termina às 23h59 da véspera.
- **Janela de 30 dias:** a leitura recente pede 32 dias passados (`past_days=32`), e não 3, para calcular os atributos de 7 e 30 dias. Continua sendo 1 chamada por ponto e por execução (cerca de 16 por dia).
- **Fim da janela na produção:** termina na última leitura válida do ponto, e não no instante da execução (TI-07). Na prática, a API do Open-Meteo preenche todas as horas passadas até o momento da consulta, então a regra de 48 h quase só dispara quando o agendamento para; nesse caso, quem aplica a regra é a própria página, no navegador.
- **Acumulado com hora ausente ou descartada:** a chuva de 24 h ou 72 h sai como `null` (a página mostra "—"), nunca como um valor menor ou como "Não choveu". O mesmo vale na página quando a última leitura passa de 48 h.
- **Regra dos 10% de horas ausentes:** vale para as janelas de 72 h, 7 dias e 30 dias (D-07). A janela de 24 h está contida na de 72 h e não tem regra própria. **A CONFIRMAR** o limite de 10%.
- **Leitura acima do máximo histórico:** é descartada (RNF12). Como o máximo do modelo meteorológico é baixo (23,5 mm/h na A521 e 34,3 mm/h na F501, 2021–2025), uma chuva extrema real seria descartada e o acumulado ficaria menor. Para não mostrar nível baixo num dia de chuva forte, a regional do ponto passa a "dados insuficientes" se houver leitura acima do máximo nas últimas 72 h. Regra a mais, no espírito de RF03.

## Mapeamento regional → ponto de chuva (A CONFIRMAR)

Ponto mais próximo do centro aproximado de cada regional: Barreiro, Centro-Sul e Oeste usam F501 (Cercadinho); Leste, Nordeste, Noroeste, Norte, Pampulha e Venda Nova usam A521 (Pampulha). Leste fica quase à mesma distância dos dois.

## Modelo

- **Semente:** 20261206. **Grade de C:** 0,01; 0,1; 1; 10, escolhido pelo menor Brier médio na validação em janela crescente.
- **Baseline:** taxa por regional e mês, puxada para a taxa da regional com força 20 (prior Beta).
- **"Margem clara" para a árvore vencer a logística:** AUC pelo menos 0,01 maior e Brier menor.
- **M-06 (monotonia):** grade de chuva com 24 h = x, 72 h = 1,5x, 7 dias = 2x, 30 dias = 3x e dias de chuva = min(⌊x/10⌋, 7). Um candidato com queda de probabilidade na grade não é escolhido.
- **Modelo publicado:** o mesmo treinado em 2021–2024 e avaliado em 2025. Não há reajuste com 2025 antes da publicação.
- **Faixas de chuva de 72 h para contar vistorias (RF02, RF03):** 0–10, 10–30, 30–60, 60–100 e 100 mm ou mais. **A CONFIRMAR.**
- **Profundidade 4 da árvore, 200 réplicas de bootstrap e limiares P75/P95:** como na Arquitetura. **A CONFIRMAR** com os dados.

## Primeiro treino com dados reais (07/11/2026)

Treino com 5.877 vistorias (2021–2024) e teste com 1.342 (2025). No teste: baseline com AUC 0,528 e Brier 0,171; regressão logística com AUC 0,523 e Brier 0,168; árvore com AUC 0,498 e Brier 0,166, além de falhar na monotonia. Nenhum candidato passou na M-01, e a regra escolheu o baseline. A Arquitetura previa esse caso: o baseline é publicado e a página declara isso. Qualquer mudança no modelo feita depois de ver o teste deve ser registrada no relatório da versão.

## Pendências do time

- Canal de contato público (RF10): definir e preencher `CONTATO` em `alertaencosta/config.py`.
- Conferir o canal da URBEL na página (hoje: telefone 156 da Prefeitura).
- Comparação com os pluviômetros do INMET (D-09): gravar o resultado em `dados/comparacao_inmet.txt` antes da publicação.
