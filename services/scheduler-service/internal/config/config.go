package config

import (
	"fmt"
	"os"
	"time"
)

type Config struct {
	HTTPAddr        string        // health/readiness listener
	DatabaseURL     string        // scheduler-service's own Postgres DB (per-service rule)
	ChatInternalURL string        // where eod_distill claims are enqueued (the WS-3.0 trigger)
	NotificationURL string        // WS-3.6 content-free nudge sink (optional)
	InternalToken   string        // X-Internal-Token for the trigger
	ConsumerName    string        // lease owner / audit
	TickInterval    time.Duration // how often the driver scans for due rows
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:        getEnv("HTTP_ADDR", ":8095"),
		DatabaseURL:     os.Getenv("DATABASE_URL"),
		ChatInternalURL: getEnv("CHAT_SERVICE_INTERNAL_URL", "http://chat-service:8090"),
		NotificationURL: os.Getenv("NOTIFICATION_SERVICE_INTERNAL_URL"),
		InternalToken:   os.Getenv("INTERNAL_SERVICE_TOKEN"),
		ConsumerName:    getEnv("SCHEDULER_CONSUMER_NAME", "scheduler-1"),
		TickInterval:    getDurationEnv("SCHEDULER_TICK_INTERVAL", time.Minute),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if c.InternalToken == "" {
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

func getDurationEnv(k string, def time.Duration) time.Duration {
	if v := os.Getenv(k); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return def
}
