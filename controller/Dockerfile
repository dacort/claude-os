FROM golang:1.25-alpine AS builder

WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /claude-os-controller .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /claude-os-controller /claude-os-controller
USER nonroot:nonroot
ENTRYPOINT ["/claude-os-controller"]
