# Trade-offs and Deliberate Shortcuts

Three features we intentionally left out of this prototype — and what a real production system would add.

---

## 1 — No real login system (OAuth / SSO)

**What we did instead:** A simple username/password check using `test-{id}` / `pass-{id}`. No tokens, no sessions, no "Sign in with Google".

**What production would need:**
- Integration with corporate login providers like Okta or Azure AD (so employees use their work email).
- Secure tokens (JWTs) with expiry, stored safely in cookies.
- Role-based access — e.g. only certain users can approve emissions, others can only upload.

**Why we skipped it:** Real SSO needs actual corporate accounts to test against. It doesn't change how the CSV parsing or emission calculations work — which is what this prototype demonstrates.

---

## 2 — No background processing for large files

**What we did instead:** When you upload a CSV, the server processes it immediately and makes you wait until it's done.

**What production would need:**
- A task queue so uploads return instantly with a "processing…" status.
- The heavy work happens in the background; the UI shows a progress bar.
- If something fails, it retries automatically.

**Why we skipped it:** Adding a task queue means extra components. For the small sample files we're testing with, synchronous processing finishes in under a second — so there's no real benefit here.

---

## 3 — No inline editing of flagged rows

**What we did instead:** Reviewers can approve or reject a flagged row, but can't fix the data (e.g. type in a missing distance value).

**What production would need:**
- An edit form that lets reviewers correct raw values (like filling in a missing distance).
- The system re-calculates emissions from the corrected inputs.
- Every correction is logged in the audit trail with who changed what and when.

**Why we skipped it:** Building an inline editor with recalculation adds frontend and backend complexity. The approve/reject flow already shows how the review workflow operates.

---
