# Arquitetura

O pipeline offline é `history.csv → validação → features numéricas → Isolation Forest → limiar histórico → model.joblib`. A avaliação consome `replay.csv` depois do treinamento. Seu rótulo serve apenas às métricas; o modelo recebe requisições, proporção de erros, latência e CPU.

O caminho online é `CSV/HTTP → validação completa → checagem de série e tempo → inferência → transação SQLite → resultado`. A API e o replay CLI compartilham a função de ingestão, evitando regras divergentes.

Uma conexão por operação usa timeout de 10 segundos e WAL. `BEGIN IMMEDIATE` reserva a escrita antes de verificar duplicatas, então dois retries concorrentes não conseguem inserir a mesma chave. O índice primário contém série e timestamp UTC; o hash do payload normalizado distingue duplicatas exatas de conflitos. Um conflito lança exceção, faz rollback do lote e vira HTTP 409. Validação de schema ocorre antes da transação e vira 422.

O score é calculado antes da transação para reduzir o tempo de bloqueio. Linhas duplicadas também passam pela inferência nessa versão, mas seus resultados persistidos não são substituídos nem geram novos alertas. A base registra a versão que avaliou a primeira inserção. Uma atualização de modelo requer reiniciar a API e uma política explícita para reprocessamento histórico.

O modelo atende uma única série e requer pontos posteriores à janela de treino. Ele não pressupõe chegada em ordem dentro dessa janela futura: ingestões atrasadas válidas podem ser persistidas, com consultas ordenadas por timestamp. O código não agrega múltiplas medições do mesmo intervalo.

O n8n cuida da borda de automação e formatação em JavaScript. Ele devolve o status da API, incluindo 409/422, e responde ao solicitante antes da etapa opcional de notificação. Somente lotes com novos alertas chegam ao destino opcional, que vem desabilitado. Persistência e entrega externa não formam uma transação única: se o receptor falhar, é preciso repetir a entrega do resumo, e repetir a ingestão não recria alertas. Um outbox transacional seria a evolução adequada para entrega garantida; não há alegação de exactly-once para notificações.

Não há cluster, broker, autenticação, retreinamento online ou registry externo. Essas omissões mantêm o fluxo auditável e executável localmente, sem mascarar as decisões de validação, avaliação e consistência.

