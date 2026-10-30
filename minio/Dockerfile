FROM golang:1.24.8-alpine AS build

ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z

RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${MINIO_VERSION}" \
    https://github.com/minio/minio.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /minio .

FROM alpine:3.22

RUN apk add --no-cache ca-certificates curl \
    && addgroup -S minio \
    && adduser -S -G minio -u 10001 minio \
    && mkdir /data \
    && chown minio:minio /data
COPY --from=build /minio /usr/local/bin/minio

USER minio
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
