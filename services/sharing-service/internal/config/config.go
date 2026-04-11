package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr               string
	DatabaseURL            string
	JWTSecret              string
	BookServiceInternalURL string
	InternalServiceToken   string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:               getEnv("HTTP_ADDR", ":8083"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		JWTSecret:              os.Getenv("JWT_SECRET"),
		BookServiceInternalURL: os.Getenv("BOOK_SERVICE_INTERNAL_URL"),
		InternalServiceToken:   os.Getenv("INTERNAL_SERVICE_TOKEN"),
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
	if c.BookServiceInternalURL == "" {
		return nil, fmt.Errorf("BOOK_SERVICE_INTERNAL_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
