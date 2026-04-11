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
		BookServiceInternalURL:        os.Getenv("BOOK_SERVICE_INTERNAL_URL"),
		SharingServiceInternalURL:     os.Getenv("SHARING_SERVICE_INTERNAL_URL"),
		TranslationServiceInternalURL: os.Getenv("TRANSLATION_SERVICE_INTERNAL_URL"),
		InternalServiceToken:          os.Getenv("INTERNAL_SERVICE_TOKEN"),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if c.InternalServiceToken == "" {
		return nil, fmt.Errorf("INTERNAL_SERVICE_TOKEN is required")
	}
	if c.BookServiceInternalURL == "" {
		return nil, fmt.Errorf("BOOK_SERVICE_INTERNAL_URL is required")
	}
	if c.SharingServiceInternalURL == "" {
		return nil, fmt.Errorf("SHARING_SERVICE_INTERNAL_URL is required")
	}
	if c.TranslationServiceInternalURL == "" {
		return nil, fmt.Errorf("TRANSLATION_SERVICE_INTERNAL_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
