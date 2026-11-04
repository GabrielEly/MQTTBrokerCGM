FROM ipfs/kubo:latest

COPY bootstrap.sh /bootstrap.sh
COPY config.sh /config.sh
COPY swarm.key /data/ipfs/swarm.key

RUN chmod +x /bootstrap.sh
RUN chmod +x /config.sh

ENTRYPOINT ["/bootstrap.sh"]