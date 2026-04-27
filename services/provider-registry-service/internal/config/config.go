package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr               string
	DatabaseURL            string
	JWTSecret              string
	UsageBillingServiceURL string
	InternalServiceToken   string

	// Phase 2c — optional. Empty = NoopNotifier (terminal events not
	// published anywhere; caller can still poll). Set in production
	// docker-compose; tests + dev-without-RabbitMQ keep working.
	RabbitMQURL string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:               getEnv("HTTP_ADDR", ":8085"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		JWTSecret:              os.Getenv("JWT_SECRET"),
		UsageBillingServiceURL: os.Getenv("USAGE_BILLING_SERVICE_URL"),
		InternalServiceToken:   os.Getenv("INTERNAL_SERVICE_TOKEN"),
		RabbitMQURL:            os.Getenv("RABBITMQ_URL"),
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
	if c.UsageBillingServiceURL == "" {
		return nil, fmt.Errorf("USAGE_BILLING_SERVICE_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

