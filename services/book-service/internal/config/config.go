package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	HTTPAddr          string
	DatabaseURL       string
	JWTSecret         string
	BooksStorageBucket string
	QuotaBytesDefault int64
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:           getEnv("HTTP_ADDR", ":8082"),
		DatabaseURL:        os.Getenv("DATABASE_URL"),
		JWTSecret:          os.Getenv("JWT_SECRET"),
		BooksStorageBucket: getEnv("BOOKS_STORAGE_BUCKET", "loreweave-dev-books"),
		QuotaBytesDefault:  getInt64("QUOTA_BYTES_DEFAULT", 100*1024*1024),
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

func getInt64(k string, def int64) int64 {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return def
	}
	return n
}
