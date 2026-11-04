#!/bin/sh

echo "Config IPFS (privado)..."

API_PORT="${IPFS_API_PORT:-5001}"
GATEWAY_PORT="${IPFS_GATEWAY_PORT:-8080}"

# API, Gateway e Swarm
ipfs config Addresses.API "/ip4/0.0.0.0/tcp/${API_PORT}"
ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/${GATEWAY_PORT}"

echo "Removendo bootstrap público..."
ipfs bootstrap rm --all
ipfs config --json AutoConf.Enabled false
ipfs config --json Bootstrap '[]'
ipfs config --json Swarm.EnableAutoNAT false
ipfs config --json Swarm.EnableHolePunching false
ipfs config --json Swarm.EnableRelayHop false
ipfs config --json Discovery.MDNS.Enabled false