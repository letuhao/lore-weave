package object_store

import (
	"context"
	"testing"
)

func TestObjectKey_Shape(t *testing.T) {
	k := ObjectKey("00000000-0000-0000-0000-000000000001", "2025-11")
	want := "events/00000000-0000-0000-0000-000000000001/2025-11.parquet"
	if k != want {
		t.Fatalf("ObjectKey: got %q want %q", k, want)
	}
}

func TestInMemory_PutGetRoundTrip(t *testing.T) {
	s := NewInMemory()
	blob := []byte("hello-archive")
	if err := s.Put(context.Background(), "lw-event-archive", "events/r/2025-11.parquet", blob); err != nil {
		t.Fatal(err)
	}
	got, err := s.Get(context.Background(), "lw-event-archive", "events/r/2025-11.parquet")
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(blob) {
		t.Fatalf("round-trip: got %q want %q", got, blob)
	}
}

func TestInMemory_PutEmptyArgs(t *testing.T) {
	s := NewInMemory()
	if err := s.Put(context.Background(), "", "k", []byte{}); err == nil {
		t.Fatal("expected empty bucket error")
	}
	if err := s.Put(context.Background(), "b", "", []byte{}); err == nil {
		t.Fatal("expected empty key error")
	}
}

func TestInMemory_GetMissing(t *testing.T) {
	s := NewInMemory()
	if _, err := s.Get(context.Background(), "b", "k"); err == nil {
		t.Fatal("expected not-found error")
	}
}

func TestInMemory_Exists(t *testing.T) {
	s := NewInMemory()
	ok, _ := s.Exists(context.Background(), "b", "k")
	if ok {
		t.Fatal("expected not exists")
	}
	_ = s.Put(context.Background(), "b", "k", []byte("x"))
	ok, _ = s.Exists(context.Background(), "b", "k")
	if !ok {
		t.Fatal("expected exists after Put")
	}
}

func TestInMemory_GetReturnsCopy(t *testing.T) {
	// Defensive: callers MUST NOT see internal mutation if they mutate
	// the returned slice.
	s := NewInMemory()
	_ = s.Put(context.Background(), "b", "k", []byte("hello"))
	got, _ := s.Get(context.Background(), "b", "k")
	got[0] = 'X'
	got2, _ := s.Get(context.Background(), "b", "k")
	if string(got2) != "hello" {
		t.Fatalf("Get must return copy; got mutated %q", got2)
	}
}

func TestFailingStore_AlwaysFails(t *testing.T) {
	f := &FailingStore{}
	if err := f.Put(context.Background(), "b", "k", []byte{}); err == nil {
		t.Fatal("expected forced failure")
	}
	if _, err := f.Get(context.Background(), "b", "k"); err == nil {
		t.Fatal("expected forced failure")
	}
}
