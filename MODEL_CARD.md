# Model card

- **Tarefa:** detectar pontos incomuns de uma série de métricas operacionais.
- **Modelo:** Isolation Forest com 200 árvores, `contamination="auto"`, seed 42 e um worker.
- **Features:** requisições, `error_count / requests`, latência em ms e CPU percentual. Não entram timestamp, rótulo, tipo da falha ou nome da série.
- **Score:** negativo de `score_samples`; valores maiores são mais anômalos. A decisão usa `score > threshold`, não a função `predict` padrão da biblioteca.
- **Limiar:** quantil 0,98 dos scores do próprio histórico. Isso é uma heurística de treinamento, não uma taxa garantida de falso positivo em dados futuros.
- **Histórico:** 600 pontos sintéticos de cinco em cinco minutos, de 2025-01-01 00:00 UTC a 2025-01-03 01:55 UTC.
- **Teste:** 120 pontos seguintes e 12 falhas injetadas, sem ajuste de hiperparâmetros pelo resultado.
- **Baseline:** `latency_ms > 300 OR error_rate > 0.10 OR cpu_percent > 90`.
- **Resultado:** o baseline superou Isolation Forest neste teste. Métricas e eventos estão em `reports/evaluation.json`.
- **Artefato:** `var/model.joblib` com estimador, janela de treino, limiar, features, seed, série, hash do histórico e versão do scikit-learn.
- **Uso pretendido:** estudar comparação com baseline, avaliação temporal, inferência persistida e idempotência.
- **Fora de escopo:** detecção confiável de incidentes reais, diagnóstico de causa, múltiplas séries, previsões, garantias de alertas e operação sem revisão humana.

O modelo não aprende padrões temporais porque não recebe features de tempo. Ele pode falhar em valores extremos de uma única dimensão, mudanças graduais e mudanças de regime. Pontos sintéticos favorecem interpretações simples; um teste real deveria incluir sazonalidade, incidentes rotulados com critérios claros e períodos sem incidente muito mais longos.

A versão deriva da identidade da implementação, seed, quantil, hash do histórico e versão da biblioteca. Ela identifica a configuração registrada, mas não assina o conteúdo binário. Um artefato joblib de terceiros não deve ser carregado apenas porque possui um identificador de versão.

