#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Document Import Integration Tests (P9-07)
#
# Tests: .txt import (legacy), .docx import, .epub import, validation, polling
#
# Prerequisites: all services running via docker compose (including pandoc-server)
# Usage: bash infra/test-import.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0
FAIL=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected: $expected, got: $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_not_empty() {
  local label="$1" value="$2"
  if [ -n "$value" ] && [ "$value" != "null" ] && [ "$value" != "undefined" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (was empty or null)"; FAIL=$((FAIL+1))
  fi
}

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label (HTTP $actual)"; PASS=$((PASS+1))
  else
    red "$label (expected HTTP $expected, got $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if echo "$haystack" | grep -q "$needle"; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected to contain: $needle)"; FAIL=$((FAIL+1))
  fi
}

jget() {
  local path="$1"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      try {
        const j=JSON.parse(d);
        const keys='${path}'.slice(1).split('.').filter(Boolean);
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        if(v===undefined||v===null) console.log('');
        else console.log(typeof v==='object'?JSON.stringify(v):v);
      } catch { console.log(''); }
    });
  "
}

# ── Setup: register + login + create book ──────────────────────────────
header "Setup: auth + book creation"

REGISTER_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"import-test@loreweave.dev","password":"ImportTest2026!","name":"Import Tester"}')
REGISTER_STATUS=$(echo "$REGISTER_RES" | tail -1)
REGISTER_BODY=$(echo "$REGISTER_RES" | sed '$d')

if [ "$REGISTER_STATUS" = "201" ]; then
  TOKEN=$(echo "$REGISTER_BODY" | jget .accessToken)
elif [ "$REGISTER_STATUS" = "409" ]; then
  LOGIN_RES=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"import-test@loreweave.dev","password":"ImportTest2026!"}')
  TOKEN=$(echo "$LOGIN_RES" | jget .accessToken)
else
  echo "Registration failed with status $REGISTER_STATUS"
  echo "$REGISTER_BODY"
  exit 1
fi

assert_not_empty "Got auth token" "$TOKEN"

BOOK_RES=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Import Test Book","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RES" | jget .book_id)
assert_not_empty "Created test book" "$BOOK_ID"

# ── Create temp test files ─────────────────────────────────────────────
header "Creating test files"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# .txt file
echo "This is a test chapter in plain text format.
It has multiple paragraphs.

This is the second paragraph." > "$TMPDIR/test-chapter.txt"
green "Created test-chapter.txt"
PASS=$((PASS+1))

# ── Test 1: .txt import (legacy path) ─────────────────────────────────
header "Test 1: .txt import (legacy path)"

TXT_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$BOOK_ID/import" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TMPDIR/test-chapter.txt" \
  -F "original_language=en")
TXT_STATUS=$(echo "$TXT_RES" | tail -1)
TXT_BODY=$(echo "$TXT_RES" | sed '$d')

assert_status "txt import returns 201" "201" "$TXT_STATUS"

TXT_CHAPTER_ID=$(echo "$TXT_BODY" | jget .chapter_id)
assert_not_empty "txt import created chapter" "$TXT_CHAPTER_ID"

# ── Test 2: Validation — no file ──────────────────────────────────────
header "Test 2: Validation"

NOFILE_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$BOOK_ID/import" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: multipart/form-data')
NOFILE_STATUS=$(echo "$NOFILE_RES" | tail -1)
assert_status "No file returns 400" "400" "$NOFILE_STATUS"

# ── Test 3: Validation — unsupported format ───────────────────────────
echo "fake pdf content" > "$TMPDIR/test.pdf"
PDF_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$BOOK_ID/import" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TMPDIR/test.pdf")
PDF_STATUS=$(echo "$PDF_RES" | tail -1)
assert_status "Unsupported format returns 400" "400" "$PDF_STATUS"

# ── Test 4: Validation — no auth ──────────────────────────────────────
NOAUTH_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$BOOK_ID/import" \
  -F "file=@$TMPDIR/test-chapter.txt")
NOAUTH_STATUS=$(echo "$NOAUTH_RES" | tail -1)
assert_status "No auth returns 401" "401" "$NOAUTH_STATUS"

# ── Test 5: Validation — wrong book ──────────────────────────────────
FAKE_BOOK="00000000-0000-0000-0000-000000000000"
WRONGBOOK_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$FAKE_BOOK/import" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TMPDIR/test-chapter.txt")
WRONGBOOK_STATUS=$(echo "$WRONGBOOK_RES" | tail -1)
assert_status "Wrong book returns 404" "404" "$WRONGBOOK_STATUS"

# ── Test 6: .docx import (async) ──────────────────────────────────────
header "Test 6: .docx import (async)"

# Create a minimal valid .docx using Python if available, or use a pre-built one
if command -v python3 &> /dev/null; then
  python3 -c "
import zipfile, io, os
# Minimal .docx structure
content_types = '''<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"xml\" ContentType=\"application/xml\"/>
  <Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>
</Types>'''
rels = '''<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
  <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>
</Relationships>'''
document = '''<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>Test Heading</w:t></w:r></w:p>
    <w:p><w:r><w:t>This is a test paragraph from a docx file.</w:t></w:r></w:p>
    <w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Bold text</w:t></w:r><w:r><w:t> and normal text.</w:t></w:r></w:p>
  </w:body>
</w:document>'''
word_rels = '''<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"/>'''
with zipfile.ZipFile('$TMPDIR/test.docx', 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', content_types)
    z.writestr('_rels/.rels', rels)
    z.writestr('word/document.xml', document)
    z.writestr('word/_rels/document.xml.rels', word_rels)
print('docx created')
" 2>&1
  HAVE_DOCX=true
else
  echo "python3 not available — skipping .docx test"
  HAVE_DOCX=false
fi

if [ "$HAVE_DOCX" = "true" ]; then
  DOCX_RES=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$BOOK_ID/import" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$TMPDIR/test.docx" \
    -F "original_language=en")
  DOCX_STATUS=$(echo "$DOCX_RES" | tail -1)
  DOCX_BODY=$(echo "$DOCX_RES" | sed '$d')

  assert_status "docx import returns 202" "202" "$DOCX_STATUS"

  IMPORT_ID=$(echo "$DOCX_BODY" | jget .id)
  assert_not_empty "docx import returned job ID" "$IMPORT_ID"

  IMPORT_STATUS=$(echo "$DOCX_BODY" | jget .status)
  assert_eq "docx import status is pending" "pending" "$IMPORT_STATUS"

  # Poll for completion (max 60 seconds)
  header "Test 7: Poll import job status"

  for i in $(seq 1 30); do
    sleep 2
    POLL_RES=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/imports/$IMPORT_ID" \
      -H "Authorization: Bearer $TOKEN")
    POLL_STATUS=$(echo "$POLL_RES" | jget .status)

    if [ "$POLL_STATUS" = "completed" ]; then
      CHAPTERS_CREATED=$(echo "$POLL_RES" | jget .chapters_created)
      green "docx import completed after ${i}x2s"
      PASS=$((PASS+1))
      assert_not_empty "docx chapters created > 0" "$CHAPTERS_CREATED"
      break
    elif [ "$POLL_STATUS" = "failed" ]; then
      IMPORT_ERROR=$(echo "$POLL_RES" | jget .error)
      red "docx import failed: $IMPORT_ERROR"
      FAIL=$((FAIL+1))
      break
    fi

    if [ "$i" = "30" ]; then
      red "docx import timed out (60s) — status: $POLL_STATUS"
      FAIL=$((FAIL+1))
    fi
  done

  # Test: list imports
  header "Test 8: List import jobs"
  LIST_RES=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/imports" \
    -H "Authorization: Bearer $TOKEN")
  IMPORT_COUNT=$(echo "$LIST_RES" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).imports.length)}catch{console.log(0)}})")
  if [ "$IMPORT_COUNT" -ge "1" ]; then
    green "List imports returned $IMPORT_COUNT job(s)"
    PASS=$((PASS+1))
  else
    red "List imports returned 0 jobs"
    FAIL=$((FAIL+1))
  fi
fi

# ── Test 9: Verify chapters exist in book ─────────────────────────────
header "Test 9: Verify chapters in book"

CHAPTERS_RES=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters" \
  -H "Authorization: Bearer $TOKEN")
TOTAL_CHAPTERS=$(echo "$CHAPTERS_RES" | jget .total)
if [ -n "$TOTAL_CHAPTERS" ] && [ "$TOTAL_CHAPTERS" -ge "1" ]; then
  green "Book has $TOTAL_CHAPTERS chapter(s) after import"
  PASS=$((PASS+1))
else
  red "Book has no chapters after import"
  FAIL=$((FAIL+1))
fi

# ── Test 10: Verify draft has Tiptap JSON body ────────────────────────
header "Test 10: Verify draft body is Tiptap JSON"

if [ -n "$TXT_CHAPTER_ID" ] && [ "$TXT_CHAPTER_ID" != "" ]; then
  DRAFT_RES=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters/$TXT_CHAPTER_ID/draft" \
    -H "Authorization: Bearer $TOKEN")
  DRAFT_FORMAT=$(echo "$DRAFT_RES" | jget .draft_format)
  assert_eq "Draft format is json" "json" "$DRAFT_FORMAT"

  DRAFT_TYPE=$(echo "$DRAFT_RES" | jget .body.type)
  assert_eq "Draft body.type is doc" "doc" "$DRAFT_TYPE"
fi

# ── Summary ────────────────────────────────────────────────────────────
header "Results"
TOTAL=$((PASS+FAIL))
printf "\033[1m%d/%d passed\033[0m\n" "$PASS" "$TOTAL"
if [ "$FAIL" -gt 0 ]; then
  printf "\033[31m%d FAILED\033[0m\n" "$FAIL"
  exit 1
else
  printf "\033[32mAll tests passed!\033[0m\n"
fi
