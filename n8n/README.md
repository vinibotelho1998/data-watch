# Integração n8n

O Webhook recebe um lote `{"rows":[...]}`, chama a API e executa JavaScript para resumir novas anomalias. `Respond to Webhook` preserva os códigos 409/422 e responde o resultado da ingestão. Uma etapa posterior filtra lotes sem alertas antes do destino opcional.

## Runtime local

O workflow tem ID estável `portfolioWatch05` e usa `http://data-watch:8005/ingest`. n8n e `data-watch` devem compartilhar a rede Compose. O JSON não acessa `$env`, não contém credenciais e é importado como inativo.

Este repositório não inclui um arquivo Compose para a integração. Para reproduzir a configuração validada, monte este diretório em `/workflows/data-watch:ro` no n8n e conecte o n8n e a API à mesma rede. O Code node usa um task runner JavaScript. A validação utilizou `N8N_RUNNERS_MODE=external` e um serviço `task-runners`, com imagem `n8nio/runners:2.44.7`, da mesma versão do n8n. O broker escuta apenas na rede interna dos contêineres e os serviços compartilham um token local de autenticação configurado fora dos workflows. Não copie esse token para os JSONs. O acesso a variáveis de ambiente dos nós pode permanecer bloqueado.

Com os serviços iniciados, execute na pasta do seu Compose:

```powershell
docker compose exec n8n n8n import:workflow --input=/workflows/data-watch/data-watch.json
docker compose exec n8n n8n publish:workflow --id=portfolioWatch05
docker compose restart n8n
```

O restart faz o processo registrar o webhook publicado no banco. A publicação é restrita à instância local; a porta do serviço deve ficar em `127.0.0.1:5678`. Para interromper o webhook, execute `n8n unpublish:workflow --id=portfolioWatch05` no mesmo serviço e reinicie-o.

## Teste real

Na raiz deste projeto:

```powershell
python n8n/verify_webhook.py --base-url http://127.0.0.1:5678 --report n8n/validation.json
```

O script usa HTTP de verdade, passando pelo n8n e pela API. Ele cria um ponto **sintético extremo** com timestamp novo, verifica um alerta, repete o ponto e exige zero novo alerta, provoca um conflito 409 e envia uma medida inválida que deve retornar 422. A execução acrescenta uma linha à base de demonstração; timestamps diferentes permitem repetir o teste sem limpar dados.

Ele não usa mocks, não acessa o modelo diretamente e não envia notificações. `/webhook/data-watch-ingest` exige workflow publicado. A rota `/webhook-test/data-watch-ingest` só funciona durante **Listen for Test Event** no editor. Executar um workflow pela CLI não substitui essa validação HTTP.

**Validação realizada:** importação e publicação na imagem `docker.n8n.io/n8nio/n8n:2.44.7`, com API em contêiner e quatro casos aprovados. O [registro da execução HTTP](validation.json) contém os status observados: inserção com um alerta, retry sem novo alerta, conflito 409 e medida inválida 422. A transformação JavaScript executou no runner externo `n8nio/runners:2.44.7`. A [conferência do runtime](runtime-validation.json) registra o modo `external` e os quatro estados `success` no banco do n8n, incluindo o término após a resposta ao webhook.

## Destino de alertas

O nó **Webhook de destino opcional** continua desabilitado e usa `http://host.docker.internal:9000/alerts` como exemplo. Nenhum receptor nessa porta está incluído. Configure um webhook local seu antes de habilitá-lo.

O filtro anterior só encaminha respostas 200 com `alert_count > 0`. Duplicatas, conflitos e lotes sem anomalias não são enviados. A resposta ao solicitante já foi enviada antes dessa etapa: ela confirma a ingestão, **não** a entrega da notificação. Se o destino falhar, repetir a ingestão não recria o alerta; consulte a execução e repita a entrega. O projeto não implementa outbox nem garantia de entrega externa.

## Fora do Compose

Na mesma máquina, a API pode usar `http://127.0.0.1:8005/ingest`. Se apenas n8n está no Docker Desktop, use `http://host.docker.internal:8005/ingest` e uma interface acessível no host. Se ambos são contêineres, prefira o nome de serviço na mesma rede, como no JSON fornecido.

## Referências verificadas

- [Server CLI: importação, publicação e reinício](https://docs.n8n.io/hosting/cli-commands/).
- [Webhook e seus modos de resposta](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/).
- [HTTP Request: resposta completa e Never Error](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/).
- [Task runners e modo externo](https://docs.n8n.io/hosting/configuration/task-runners/).

`Never Error` trata respostas HTTP da API como dados, para preservar o status na resposta. Indisponibilidade de DNS, conexões recusadas e timeout continuam interrompendo o workflow.

