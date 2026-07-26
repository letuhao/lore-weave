module github.com/loreweave/glossary-service

go 1.25.0

require (
	github.com/go-chi/chi/v5 v5.3.1
	github.com/golang-jwt/jwt/v5 v5.3.1
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/contracts/adminjwt v0.0.0
	github.com/loreweave/foundation/contracts/platformjwt v0.0.0
	github.com/loreweave/grantclient v0.1.0
	github.com/loreweave/loreweave_extraction v0.0.0
	github.com/loreweave/loreweave_mcp v0.0.0
	github.com/loreweave/observability v0.1.0
	github.com/modelcontextprotocol/go-sdk v1.7.0-pre.3
	github.com/prometheus/client_golang v1.24.0
	github.com/redis/go-redis/v9 v9.21.0
	golang.org/x/text v0.40.0
)

require (
	go.uber.org/atomic v1.11.0 // indirect
	golang.org/x/time v0.15.0 // indirect
)

replace github.com/loreweave/foundation/contracts/adminjwt => ../../contracts/adminjwt

replace github.com/loreweave/foundation/contracts/platformjwt => ../../contracts/platformjwt

replace github.com/loreweave/grantclient => ../../sdks/go/grantclient

replace github.com/loreweave/loreweave_extraction => ../../sdks/go/loreweave_extraction

replace github.com/loreweave/loreweave_mcp => ../../sdks/go/loreweave_mcp

replace github.com/loreweave/observability => ../../sdks/go/observability

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cenkalti/backoff/v5 v5.0.3 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/felixge/httpsnoop v1.0.4 // indirect
	github.com/go-logr/logr v1.4.3 // indirect
	github.com/go-logr/stdr v1.2.2 // indirect
	github.com/google/jsonschema-go v0.4.3
	github.com/grpc-ecosystem/grpc-gateway/v2 v2.29.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/loreweave/loreweave_llm v0.0.0
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.2 // indirect
	github.com/prometheus/common v0.70.0 // indirect
	github.com/prometheus/procfs v0.21.1 // indirect
	github.com/segmentio/asm v1.1.3 // indirect
	github.com/segmentio/encoding v0.5.4 // indirect
	github.com/yosida95/uritemplate/v3 v3.0.2 // indirect
	go.opentelemetry.io/auto/sdk v1.2.1 // indirect
	go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp v0.69.0 // indirect
	go.opentelemetry.io/otel v1.44.0 // indirect
	go.opentelemetry.io/otel/exporters/otlp/otlptrace v1.44.0 // indirect
	go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp v1.44.0 // indirect
	go.opentelemetry.io/otel/metric v1.44.0 // indirect
	go.opentelemetry.io/otel/sdk v1.44.0 // indirect
	go.opentelemetry.io/otel/trace v1.44.0 // indirect
	go.opentelemetry.io/proto/otlp v1.10.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/oauth2 v0.36.0 // indirect
	golang.org/x/sync v0.22.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
	google.golang.org/genproto/googleapis/api v0.0.0-20260526163538-3dc84a4a5aaa // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20260526163538-3dc84a4a5aaa // indirect
	google.golang.org/grpc v1.81.1 // indirect
	google.golang.org/protobuf v1.36.11 // indirect
)

replace github.com/loreweave/loreweave_llm => ../../sdks/go/loreweave_llm
