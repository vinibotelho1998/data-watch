# Dados

`history.csv` e `replay.csv` foram criados pelo gerador `src/data_watch/generate.py` com `numpy.random.default_rng(42)`. Não são logs de usuários, servidores ou empresas. A série `demo-api` e todas as datas/medidas são artificiais.

O gerador cria 720 amostras em intervalos de cinco minutos. Há variação senoidal leve no volume, latência e CPU, além de ruído. O histórico contém 600 pontos sem falhas injetadas. O replay contém os 120 seguintes, com 12 alterações em posições fixas: três picos de latência, três rajadas de erros, três picos de tráfego e três saturações de CPU.

`is_anomaly` e `anomaly_kind` são a verdade sintética usada somente na avaliação. Eles não são descobertos por um humano nem pelo modelo. `source` informa `synthetic-generator-v1`. O código extrai explicitamente apenas os campos operacionais para inferência.

Regeneração: `python -m data_watch.generate --seed 42`. Datas fixas e seed permitem repetir o experimento; versões de dependências estão registradas em `requirements.lock`. O relatório guarda os hashes dos arquivos para identificar a versão efetivamente avaliada.

Os incidentes injetados são abruptos e simples. Eles não representam a distribuição ou o custo de incidentes reais. Taxas de precisão, recall e falsos positivos deste material não devem ser apresentadas como desempenho em produção.

