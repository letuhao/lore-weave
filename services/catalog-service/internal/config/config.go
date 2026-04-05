package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr                     string
	DatabaseURL                  string
	BookServiceInternalURL       string
	SharingServiceInternalURL    string
	TranslationServiceInternalURL string
	InternalServiceToken          string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:                      getEnv("HTTP_ADDR", ":8084"),
		DatabaseURL:                   os.Getenv("DATABASE_URL"),
		BookServiceInternalURL:        getEnv("BOOK_SERVICE_INTERNAL_URL", "http://localhost:8082"),
		SharingServiceInternalURL:     getEnv("SHARING_SERVICE_INTERNAL_URL", "http://localhost:8083"),
		TranslationServiceInternalURL: getEnv("TRANSLATION_SERVICE_INTERNAL_URL", "http://localhost:8087"),
		InternalServiceToken:          getEnv("INTERNAL_SERVICE_TOKEN", ""),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
