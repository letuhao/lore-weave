package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr             string
	DatabaseURL          string
	JWTSecret            string
	InternalServiceToken string

	// Phase 2d — optional. Empty disables the LLM-jobs consumer (the
	// REST API stays usable; FE just falls back to polling job status
	// directly via provider-registry until the broker is configured).
	RabbitMQURL string

	// M5 (D-MOB-4) Web Push / VAPID. OPTIONAL: empty keys leave the push sender a no-op (the
	// service + in-app notifications run fine without push configured). When set, the PRIVATE key is
	// platform infra (never JWT_SECRET); the PUBLIC key is served to the FE so a browser can
	// subscribe. Subscriber is a mailto: contact required by the Web Push spec.
	VAPIDPublicKey  string
	VAPIDPrivateKey string
	VAPIDSubscriber string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:             getEnv("HTTP_ADDR", ":8091"),
		DatabaseURL:          os.Getenv("DATABASE_URL"),
		JWTSecret:            os.Getenv("JWT_SECRET"),
		InternalServiceToken: os.Getenv("INTERNAL_SERVICE_TOKEN"),
		RabbitMQURL:          os.Getenv("RABBITMQ_URL"),
		VAPIDPublicKey:       os.Getenv("VAPID_PUBLIC_KEY"),
		VAPIDPrivateKey:      os.Getenv("VAPID_PRIVATE_KEY"),
		VAPIDSubscriber:      getEnv("VAPID_SUBSCRIBER", "mailto:ops@loreweave.dev"),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if len(c.JWTSecret) < 32 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 32 characters")
	}
	if c.InternalServiceToken == "" {
		return nil, fmt.Errorf("INTERNAL_SERVICE_TOKEN is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
