package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	HTTPAddr               string
	DatabaseURL            string
	InternalServiceToken   string
	RedisURL               string
	BookServiceInternalURL string
	RefreshIntervalSeconds int
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:               getEnv("HTTP_ADDR", ":8089"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		InternalServiceToken:   getEnv("INTERNAL_SERVICE_TOKEN", ""),
		RedisURL:               os.Getenv("REDIS_URL"),
		BookServiceInternalURL: getEnv("BOOK_SERVICE_INTERNAL_URL", "http://localhost:8082"),
		RefreshIntervalSeconds: getInt("REFRESH_INTERVAL", 600),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if c.RedisURL == "" {
		return nil, fmt.Errorf("REDIS_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func getInt(k string, def int) int {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}
