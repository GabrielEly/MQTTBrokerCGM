# Simulador CGM com MQTT e FHIR R4

## Objetivo e arquitetura

Este protótipo reproduz leituras do Shanghai T2DM dataset por MQTT e as transforma em recursos `Observation` no formato JSON do HL7 FHIR R4. O `cgm-simulator` lê dados locais e publica no tópico `cgm/measurements`; o `observation-processor` valida cada mensagem e acrescenta um recurso por linha ao arquivo JSONL persistente. O simulador e o processador trocam medições pelo `mosquitto`; um serviço HTTP separado recebe Observations explicitamente para cifrar e registrar no IPFS e no PostgreSQL.

O fluxo MQTT apenas acrescenta as Observations ao JSONL local. Separadamente, o serviço HTTP `observation-storage` recebe Observations sob demanda, cifra cada uma com AES-256-GCM e uma chave de dados protegida por RSA-OAEP, envia o conteúdo cifrado ao nó IPFS e registra CID, paciente e horários em uma tabela PostgreSQL (`observation_references`).

## Estrutura

```text
.
├── cgm-simulator/             # Publicador MQTT e leitor CSV
├── data/                      # Dataset local
├── mosquitto/mosquitto.conf   # Configuração local do broker
├── observation-processor/     # Validador e construtor FHIR
├── output/                    # Arquivo persistente observations.jsonl
├── secrets/encryption/        # Chaves locais (não versionadas)
├── tests/                     # Testes unitários sem broker/dataset
├── docker-compose.yml
└── requirements-test.txt
```

## Dataset, mapeamento, unidade e fuso horário

Os arquivos de exemplo reais foram inspecionados em `data/`. São CSVs com delimitador `;`, coluna temporal `Date` (`YYYY-MM-DD HH:MM:SS`) e coluna CGM normalmente chamada `CGM (mg / dl)`. Alguns arquivos usam `CGM` (às vezes com espaços no cabeçalho); o leitor reconhece essas variantes e remove espaços externos dos nomes das colunas. A coluna `CBG` é uma medição capilar separada e não é usada como leitura CGM. Os padrões do Compose mapeiam a coluna temporal para `Date`, a glicose para `CGM (mg / dl)` e a unidade para `mg/dL`. Para outros arquivos/formats, confira os cabeçalhos e a documentação original e configure:

- `DATASET_PATIENT_COLUMN`: coluna com o identificador do paciente, se existir; quando vazia, os padrões do projeto usam o prefixo dos nomes de arquivo observados.
- `DATASET_PATIENT_FROM_FILENAME`: habilita a extração do primeiro token dos nomes `<prefixo>_<registro>_<data>.csv`.
- `DATASET_TIME_COLUMN`: coluna com o horário da medição (`Date` nos arquivos inspecionados).
- `DATASET_GLUCOSE_COLUMN`: coluna com a glicose CGM (`CGM (mg / dl)` nos arquivos inspecionados).
- `DATASET_GLUCOSE_UNIT`: unidade documentada (`mg/dL` nos arquivos inspecionados; também aceita `mmol/L`).
- `DATASET_TIME_FORMAT`: formato de `datetime.strptime` (`%Y-%m-%d %H:%M:%S` para os arquivos inspecionados).
- `DATASET_TIMEZONE`: fuso IANA usado somente para timestamps sem offset. O padrão é `Asia/Shanghai`, consistente com a origem geográfica indicada para o dataset; confirme-o na documentação dos dados ou substitua-o conforme necessário.

Nos arquivos disponíveis, não há coluna de paciente. Os nomes vistos são `2000_0_20201230.csv`, `2001_0_20201102.csv` e `2001_1_20201117.csv`. O código usa o primeiro token como identificador: assim os dois arquivos `2001_*` são associados a `2001`, e não se inventa um paciente diferente para cada CSV. Essa interpretação é inferida pelos nomes e pela repetição do prefixo `2001`; verifique-a contra a documentação oficial caso disponível. Não foram encontrados dados que sustentem tratar todos os arquivos como um único paciente.

O leitor ignora CSVs que não tenham as colunas de horário e CGM (como `Shanghai_T2DM_Summary.csv`), além de linhas sem horário e valor CGM; registra linhas de medição inválidas, valida valores positivos e finitos e ordena cronologicamente. Se um CSV contiver apenas uma das colunas configuradas, a carga falha com erro claro de mapeamento. É possível restringir a simulação com `PATIENT_ID`. O payload preserva unidade e valor originais; o processador converte explicitamente `mmol/L` para `mg/dL` (fator 18.0182) antes de construir a Observation. Não se infere a unidade pela magnitude.

## Configuração

As configurações abaixo são disponibilizadas pelo Compose. Pode-se defini-las em um arquivo `.env` na raiz ou no ambiente:

| Variável | Padrão | Uso |
|---|---|---|
| `MQTT_HOST` | `mosquitto` | Host do broker na rede Compose |
| `MQTT_PORT` | `1883` | Porta MQTT |
| `MQTT_TOPIC` | `cgm/measurements` | Tópico de medições |
| `SIM_INTERVAL_SECONDS` | `1` | Intervalo entre publicações |
| `SIM_START_DELAY_SECONDS` | `2` | Pequeno atraso para o processador assinar o tópico |
| `CGM_DEVICE_ID` | `cgm-sim-01` | Identificador estável do dispositivo |
| `DATASET_PATH` | `/app/data` | Caminho do volume de dados no contêiner |
| `SIM_REPEAT` | `false` | Recomeça a leitura ao fim do dataset |
| `PATIENT_ID` | vazio | Filtra um paciente específico |
| `IPFS_API_URL` | `http://ipfs-node:5001` | API do nó IPFS na rede Docker |
| `STORAGE_API_PORT` | `8000` | Porta local da API de armazenamento |
| `ENCRYPTION_PRIVATE_KEY_PATH` | `/run/secrets/observations-private.pem` | Caminho interno da chave privada usada para descriptografar recursos |
| `POSTGRES_DB` | `observations` | Banco que guarda as referências |
| `POSTGRES_USER` | `observations` | Usuário do PostgreSQL |
| `POSTGRES_PASSWORD` | obrigatório | Senha definida no `.env` da raiz |
| `POSTGRES_PORT` | `5432` | Porta local do PostgreSQL no host |

Os mapeamentos de coluna, unidade e horário estão descritos na seção anterior e em [data/README.md](data/README.md). O simulador termina com erro claro se o dataset ou qualquer mapeamento necessário estiver ausente ou incompatível.
O processador grava em `/app/output/observations.jsonl` dentro do contêiner, mapeado para `output/observations.jsonl` na pasta do projeto. Esse caminho é fixo para garantir que a saída permaneça no host.

### Perfis do Docker Compose

Os serviços estão separados em perfis para permitir iniciar apenas o necessário. No PowerShell, na raiz do projeto:

```powershell
# Somente fluxo CGM: Mosquitto, processador e simulador (saída apenas em output/)
docker compose --profile cgm up --build

# Somente nó IPFS
docker compose --profile ipfs up --build

# Somente API de armazenamento, PostgreSQL e o IPFS necessário para a API
docker compose --profile storage up --build

# Projeto completo: CGM, API/PostgreSQL e IPFS
docker compose --profile cgm --profile storage up --build
```

O perfil `storage` também habilita o serviço IPFS, pois a API depende dele. As portas do host são vinculadas somente a `127.0.0.1` (API `5001`, gateway `8084`).

Configure `POSTGRES_PASSWORD` no `.env` da raiz antes de iniciar os perfis `storage` ou o projeto completo. Gere uma chave RSA local antes de subir o serviço de armazenamento. A chave pública é montada como somente leitura na API; a chave privada permanece no host e não deve ser compartilhada nem versionada.

```powershell
docker compose build observation-storage
docker compose run --rm encryption-keygen
```

Para armazenar uma Observation, inicie o perfil `storage` ou o projeto completo e envie-a explicitamente ao endpoint `POST http://localhost:8000/observations`; de outro contêiner na rede principal, use `http://observation-storage:8000/observations`. A API do host está vinculada somente a `127.0.0.1`. Cada chamada bem-sucedida gera um arquivo cifrado individual no IPFS. A tabela `observation_references` mantém `observation_id`, `patient_id`, `cid`, `observed_at` e `created_at`; o identificador de paciente é extraído da referência FHIR (`urn:uuid:` ou `Patient/`). O PostgreSQL persiste em um volume Docker e sua porta fica disponível somente em `127.0.0.1:5432`.

Para recuperar os recursos de um paciente, consulte `GET http://localhost:8000/observations?patient_id=<identificador>`. A API busca os CIDs associados ao paciente no PostgreSQL, baixa cada recurso do IPFS, descriptografa-o com `private.pem` e retorna uma lista JSON de Observations. Se não houver recursos associados, retorna `[]`. Erros do IPFS retornam HTTP 502 e indisponibilidade do banco retorna HTTP 503. A chave privada é montada somente para leitura no serviço da API; mantenha-a protegida e não a compartilhe.

Exemplo de envio manual de um recurso existente no JSONL:

```powershell
$observation = Get-Content .\output\observations.jsonl -TotalCount 1
Invoke-RestMethod -Method Post -Uri http://localhost:8000/observations `
  -ContentType "application/json" -Body $observation
```

Uma chamada `curl` equivalente:

```bash
curl -X POST http://localhost:8000/observations \
  -H "Content-Type: application/json" \
  --data-binary @observation.json
```

O envelope usa AES-256-GCM para os dados e RSA-OAEP com SHA-256 para proteger a chave AES. A função `decrypt_observation` em `observation-processor/src/storage.py` pode ser usada com o arquivo IPFS baixado e `private.pem`. Perder a chave privada impede a recuperação das Observations cifradas. O JSONL local permanece em texto claro, conforme o comportamento existente e não é enviado automaticamente à API.

Para consultar as referências mais recentes:

```powershell
docker compose exec postgres psql -U observations -d observations -c "SELECT patient_id, cid, observed_at FROM observation_references ORDER BY observed_at DESC;"
```

## Execução

Requisitos: Docker com Docker Compose. Depois de colocar o dataset e preencher as variáveis conforme a documentação original:

```bash
docker compose --profile cgm --profile storage up --build
```

Os serviços têm perfis explícitos; por isso, use os comandos de perfil acima em vez de `docker compose up` sem opções. `--build` atualiza as imagens antes de iniciar os serviços; use-o após alterações no código para evitar executar uma versão antiga. O perfil `cgm` inicia o broker com verificação de saúde, o processador e então o simulador. A saída é criada em `output/observations.jsonl` na raiz do projeto. Para acompanhar os serviços CGM:

```bash
docker compose --profile cgm logs -f cgm-simulator
docker compose --profile cgm logs -f observation-processor
docker compose --profile cgm logs -f mosquitto
```

Encerre com `Ctrl+C` ou `docker compose down`. Não use `docker compose down -v` se quiser preservar a saída. `output/observations.jsonl` está em um bind mount e permanece no host.

## Contratos e saída

Exemplo ilustrativo de mensagem (não representa uma linha real do dataset):

```json
{"patient":"p-017","device":"cgm-sim-01","time":"2026-10-05T08:15:00+08:00","glucose":142,"unit":"mg/dL"}
```

Para mensagens válidas, o processador cria uma Observation com código LOINC `99504-3`, referência a `Patient/{patient}`, `Device/{device}`, horário original da medição e `valueQuantity` normalizada em `mg/dL`. Cada linha de `output/observations.jsonl` contém um recurso JSON individual, não um Bundle FHIR. O `id` da Observation é um hash estável dos campos da medição para facilitar a identificação de repetições; não há deduplicação nem servidor FHIR.

```json
{
    "resourceType": "Observation", 
    "id": "d1cc48d8950244f284367b62786ecdfe91ee6c767d44a041a9a6b6a706f23709", 
    "status": "final", 
    "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category", 
                "code": "laboratory", 
                "display": "Laboratory"
            }]
    }], 
    "code": {
        "coding": [{
            "system": "http://loinc.org", 
            "code": "99504-3", 
            "display": "Glucose [Mass/volume] in Interstitial fluid"
        }], 
        "text": "Glicose intersticial"
    }, 
    "subject": {
        "reference": "urn:uuid:2085"
    }, 
    "effectiveDateTime": "2020-09-07T22:08:00+08:00", 
    "valueQuantity": {
        "value": 81, 
        "unit": "mg/dL", 
        "system": "http://unitsofmeasure.org", 
        "code": "mg/dL"
    }, 
    "device": {
        "reference": "urn:uuid:cgm-sim-01"
    }
}
```

Mensagens JSON inválidas ou com campos/tipos/unidades não suportados são registradas e descartadas sem interromper o processador. Não são aplicadas regras clínicas.

## Limitações do protótipo

- O leitor implementado aceita arquivos CSV; outros formatos devem ser convertidos ou suportados após inspeção da documentação real.
- O mapeamento de colunas, formato do horário, unidade e eventual significado do nome de arquivo precisam ser confirmados pelo usuário contra os dados originais.
- O broker não usa autenticação nem TLS. QoS 0 pode perder mensagens e não há reconexão avançada, fila persistente ou deduplicação.
- As referências Patient/Device são referências lógicas; nenhum recurso Patient ou Device é criado e não há validação contra servidor FHIR.
