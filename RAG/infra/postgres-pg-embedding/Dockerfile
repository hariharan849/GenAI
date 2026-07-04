FROM postgres:18-trixie

ARG PG_EMBEDDING_REF=055b71946024d72abecd8302fcfa17fe1bfb22f1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-18 \
    && git clone https://github.com/neondatabase/pg_embedding.git /tmp/pg_embedding \
    && cd /tmp/pg_embedding \
    && git checkout "${PG_EMBEDDING_REF}" \
    && make \
    && make install \
    && cd / \
    && rm -rf /tmp/pg_embedding \
    && apt-get purge -y --auto-remove build-essential git postgresql-server-dev-18 \
    && rm -rf /var/lib/apt/lists/*
