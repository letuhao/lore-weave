package api

// world_map_list answered `{"maps": []}` for a world the caller does not own.
//
// WHY THAT IS A DEFECT EVEN THOUGH NOTHING LEAKS. The listing query is owner-scoped
// (`WHERE world_id=$1 AND owner_user_id=$2`), so no other account's map was ever
// reachable and this was never an information disclosure. The defect is that an empty
// list is the SAME SENTENCE as "your world has no maps yet". Four siblings in this
// service refuse such a request by name -- world_get, world_map_get, world_map_delete
// and world_delete all answer "not found" -- and world_map_list was the one that
// answered as if the question had been asked about an empty world of the caller's own.
//
// FOUND 2026-08-21 by the tool deep-dive's tenancy probe, which calls each world/map tool
// with another account's id. It flagged this one because it returned a RESULT where its
// siblings returned an error; reading the SQL showed the result was empty rather than
// foreign, so the finding is honesty, not security.
//
// IT IS WORSE THROUGH AN AGENT THAN THROUGH THE UI. The same batch measured the cost of
// this exact shape: asked to show a world that demonstrably existed, the model answered
// "I don't have a record of a world named Emberfall Reach" and offered to build it from
// scratch -- which would have duplicated the author's world. A tool that says "no maps"
// when it means "not your world" feeds that same false-absence answer.
//
// The new check is owner-scoped too, so it is still no existence oracle: a world that
// exists under another account and a world that exists nowhere both answer "world not
// found".

import (
	"testing"

	"github.com/google/uuid"
)

func TestWorldMapListRefusesAWorldTheCallerDoesNotOwn(t *testing.T) {
	s, _ := dbTestServer(t)

	// Owner A makes a world and puts a map in it, so the world is NOT empty. That matters:
	// if A's world had no maps, an empty answer to B would be indistinguishable from the
	// truthful one and the test could pass without the fix.
	ownerA := uuid.New()
	ctxA := identityCtxForTest(t, ownerA)
	_, wout, err := s.toolWorldCreate(ctxA, nil, worldCreateIn{Name: "A's World"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	worldID := wout.World.WorldID
	if _, _, err := s.toolWorldMapCreate(ctxA, nil, worldMapCreateIn{
		WorldID: worldID, Name: "A's Map",
	}); err != nil {
		t.Fatalf("world_map_create: %v", err)
	}

	ctxB := identityCtxForTest(t, uuid.New())
	_, out, err := s.toolWorldMapList(ctxB, nil, mapListIn{WorldID: worldID})
	if err == nil {
		t.Fatalf("listing another owner's world returned %d map(s) and no error; an empty list "+
			"reads as 'your world has no maps yet', the false-absence shape the siblings refuse",
			len(out.Maps))
	}
	if got := err.Error(); got != errNoSuchWorld.Error() {
		t.Fatalf("refusal = %q, want %q (the wording its four siblings already use)",
			got, errNoSuchWorld.Error())
	}
}

func TestWorldMapListRefusesAWorldThatExistsNowhere(t *testing.T) {
	// Same sentence for "not yours" and "no such world" — otherwise the refusal becomes an
	// existence oracle for another account's worlds.
	s, _ := dbTestServer(t)
	ctx := identityCtxForTest(t, uuid.New())

	_, _, err := s.toolWorldMapList(ctx, nil, mapListIn{WorldID: uuid.New().String()})
	if err == nil {
		t.Fatal("a world_id that exists nowhere must be refused, not answered with an empty list")
	}
	if got := err.Error(); got != errNoSuchWorld.Error() {
		t.Fatalf("refusal = %q, want %q — it must not differ from the not-yours wording", got,
			errNoSuchWorld.Error())
	}
}

func TestWorldMapListStillListsTheCallersOwnEmptyWorld(t *testing.T) {
	// The bystander check. The refusal above must not have taught the tool to refuse a world
	// the caller genuinely owns that genuinely has no maps — that IS the honest empty case.
	s, _ := dbTestServer(t)
	ctx := identityCtxForTest(t, uuid.New())

	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "My Empty World"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}

	_, out, err := s.toolWorldMapList(ctx, nil, mapListIn{WorldID: wout.World.WorldID})
	if err != nil {
		t.Fatalf("listing my own empty world failed: %v", err)
	}
	if out.Maps == nil {
		t.Fatal("Maps must be an empty slice, never nil — a nil marshals to null and reads as 'unknown'")
	}
	if len(out.Maps) != 0 {
		t.Fatalf("a world with no maps returned %d", len(out.Maps))
	}
}
