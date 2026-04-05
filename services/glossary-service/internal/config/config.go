package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr        string
	DatabaseURL     string
	JWTSecret       string
	AuthServiceURL       string
	BookServiceURL       string
	InternalServiceToken string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:       getEnv("HTTP_ADDR", ":8088"),
		DatabaseURL:    os.Getenv("DATABASE_URL"),
		JWTSecret:      os.Getenv("JWT_SECRET"),
		AuthServiceURL: getEnv("AUTH_SERVICE_URL", "http://localhost:8081"),
		BookServiceURL:       getEnv("BOOK_SERVICE_URL", "http://localhost:8082"),
		InternalServiceToken: getEnv("INTERNAL_SERVICE_TOKEN", ""),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if len(c.JWTSecret) < 32 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 32 characters")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
