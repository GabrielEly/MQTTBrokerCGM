# Nó IPFS adicional para a rede distribuída

Esta pasta permite subir mais nós IPFS em outras máquinas e conectá-los a um nó IPFS já existente.

## Como usar

1. Copie esta pasta para outra máquina.
2. Edite o arquivo `.env`.
3. Gere uma swarm.key que deve ser igual para cada no.
4. Defina `IPFS_BOOTSTRAP_PEERS` com o peer do nó principal, por exemplo:
5. Descomente o servico do netbird em ipfs-node/docker-compose.yml. Assim, um netbird ira ser gerado junto com o no ipfs.

```bash
IPFS_BOOTSTRAP_PEERS=/ip4/SEU_HOST/tcp/4001/p2p/SEU_PEER_ID
```

6. Inicie o nó:

```bash
docker compose up -d --build
```

### IMPORTANTE

Alguns arquivos `.sh` podem estar como CRLF. Dentro de sua IDE, você deve mudar todos os arquivos `.sh` para LF.

Arquivos `.sh` podem ser encontrados em `ipfs-node/ipfs`.


## Pontos de acesso
- API IPFS: http://localhost:5001
- Gateway: http://localhost:8084 (host port; container listens on 8080)
- Swarm: tcp://localhost:4001

Depois pode ser iniciado com:
```bash
docker compose start
```
E parado com:
```bash
docker compose stop
```
