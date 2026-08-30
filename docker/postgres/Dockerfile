# Keep the already-validated PostgreSQL 17.11 Alpine base immutable. The digest
# is the linux/amd64 image used by this project's Windows Docker Desktop setup.
FROM postgres:17.11-alpine3.24@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73

# pgvector v0.8.6 resolves to this immutable upstream commit. Build with
# portable compiler flags so the image does not depend on the builder CPU.
ADD https://github.com/pgvector/pgvector.git#8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c /tmp/pgvector

RUN apk add --no-cache --virtual .pgvector-build-deps \
        build-base=0.5-r4 \
    && cd /tmp/pgvector \
    && make clean \
    && make OPTFLAGS="" with_llvm=no \
    && make install with_llvm=no \
    && mkdir -p /usr/share/doc/pgvector \
    && cp LICENSE README.md /usr/share/doc/pgvector/ \
    && rm -rf /tmp/pgvector \
    && apk del .pgvector-build-deps

COPY docker/postgres/init/001-enable-vector.sql /docker-entrypoint-initdb.d/001-enable-vector.sql
