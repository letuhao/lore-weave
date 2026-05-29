package prompt

import (
	"strings"
	"testing"

	"github.com/google/uuid"
)

func validContext(t *testing.T) PromptContext {
	t.Helper()
	s := uuid.New()
	return PromptContext{
		RealityID:      uuid.New(),
		SessionID:      &s,
		ActorUserRefID: uuid.New(),
		Intent:         IntentSessionTurn,
	}
}

func TestPromptContext_Validate_OK(t *testing.T) {
	c := validContext(t)
	if err := c.Validate(); err != nil {
		t.Fatalf("Validate() = %v; want nil", err)
	}
}

func TestPromptContext_Validate_MissingRealityID(t *testing.T) {
	c := validContext(t)
	c.RealityID = uuid.Nil
	if err := c.Validate(); err == nil {
		t.Fatalf("Validate() = nil; want RealityID zero error")
	}
}

func TestPromptContext_Validate_MissingActor(t *testing.T) {
	c := validContext(t)
	c.ActorUserRefID = uuid.Nil
	if err := c.Validate(); err == nil {
		t.Fatalf("Validate() = nil; want ActorUserRefID zero error")
	}
}

func TestPromptContext_Validate_InvalidIntent(t *testing.T) {
	c := validContext(t)
	c.Intent = Intent("turn_resolution") // not in 7-enum
	if err := c.Validate(); err == nil {
		t.Fatalf("Validate() = nil; want invalid intent error")
	}
}

func TestPromptContext_Validate_SessionTurnRequiresSession(t *testing.T) {
	c := validContext(t)
	c.SessionID = nil
	c.Intent = IntentSessionTurn
	err := c.Validate()
	if err == nil {
		t.Fatalf("Validate() = nil; want session_id required error")
	}
	if !strings.Contains(err.Error(), "SessionID") {
		t.Errorf("Validate() err = %v; want error mentioning SessionID", err)
	}
}

func TestPromptContext_Validate_NPCReplyRequiresSession(t *testing.T) {
	c := validContext(t)
	c.SessionID = nil
	c.Intent = IntentNPCReply
	if err := c.Validate(); err == nil {
		t.Fatalf("Validate() = nil; want session_id required for npc_reply")
	}
}

func TestPromptContext_Validate_WorldSeedNoSessionOK(t *testing.T) {
	c := validContext(t)
	c.SessionID = nil
	c.Intent = IntentWorldSeed
	if err := c.Validate(); err != nil {
		t.Errorf("Validate() = %v; want nil (world_seed has no session)", err)
	}
}

func TestPromptContext_Validate_AdminTierRequired(t *testing.T) {
	c := validContext(t)
	c.SessionID = nil
	c.Intent = IntentAdminTriggered
	if err := c.Validate(); err == nil {
		t.Fatalf("Validate() = nil; want AdminTier required for admin_triggered")
	}
	c.AdminTier = "tier_1"
	if err := c.Validate(); err != nil {
		t.Errorf("Validate() = %v; want nil after AdminTier set", err)
	}
}

func TestPromptContext_Validate_NegativeTemplateVersion(t *testing.T) {
	c := validContext(t)
	c.TemplateVersion = -1
	if err := c.Validate(); err == nil {
		t.Fatalf("Validate() = nil; want negative template_version error")
	}
}
