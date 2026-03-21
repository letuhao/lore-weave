package authpwd

import "testing"

func TestHashVerify(t *testing.T) {
	h, err := Hash("passw0rdLongEnough")
	if err != nil {
		t.Fatal(err)
	}
	ok, err := Verify("passw0rdLongEnough", h)
	if err != nil || !ok {
		t.Fatalf("verify: ok=%v err=%v", ok, err)
	}
	ok, err = Verify("wrong", h)
	if err != nil || ok {
		t.Fatalf("wrong password should fail: ok=%v err=%v", ok, err)
	}
}
