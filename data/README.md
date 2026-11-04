# Shanghai T2DM dataset

Os CSVs reais ficam neste diretório e não são incluídos na imagem como dados fictícios. Os arquivos inspecionados têm delimitador `;` e as colunas:

- `Date`: data/hora no formato `YYYY-MM-DD HH:MM:SS`.
- `CGM (mg / dl)`: leitura CGM em mg/dL.
- `CBG (mg / dl)`: leitura de glicemia capilar separada; não é a coluna usada pelo simulador.

O valor de `Date` não contém offset. O projeto interpreta esses horários como `Asia/Shanghai` por padrão, por ser o fuso local associado ao dataset; ajuste `DATASET_TIMEZONE` caso a documentação da distribuição indique outra política.

Os nomes observados seguem o formato `<prefixo>_<registro>_<data>.csv`. Não há coluna de paciente nos exemplos. O leitor usa o primeiro token como identificador do paciente, em vez de fabricar um paciente por CSV. Isso mantém `2001_0_20201102.csv` e `2001_1_20201117.csv` associados ao mesmo identificador (`2001`), enquanto `2000_0_20201230.csv` usa `2000`. Essa é uma inferência baseada no padrão dos nomes e na repetição de `2001`; confirme-a com a documentação oficial do dataset se ela estiver disponível.

Configuração Compose padrão para esse formato:

```dotenv
DATASET_PATIENT_COLUMN=
DATASET_PATIENT_FROM_FILENAME=true
DATASET_TIME_COLUMN=Date
DATASET_GLUCOSE_COLUMN=CGM (mg / dl)
DATASET_GLUCOSE_UNIT=mg/dL
DATASET_TIME_FORMAT=%Y-%m-%d %H:%M:%S
DATASET_TIMEZONE=Asia/Shanghai
```

O programa pula linhas com dados incompletos/inválidos e ordena as leituras por instante. Coloque aqui outros arquivos originais somente se seguirem o mesmo formato ou ajuste as variáveis de ambiente conforme a documentação deles.
