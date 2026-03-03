"""Delete all questions via the Quest API."""
import requests

BASE = "http://127.0.0.1:5001"
TOKEN = requests.post(f"{BASE}/api/auth/token").json()["token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

questions = requests.get(f"{BASE}/api/questions", headers=HEADERS).json()
print(f"Found {len(questions)} questions. Deleting...")

for q in questions:
    r = requests.delete(f"{BASE}/api/questions/{q['id']}", headers=HEADERS)
    status = "ok" if r.status_code in (200, 204) else f"FAILED ({r.status_code})"
    print(f"  Q{q['id']}: {status}")

remaining = requests.get(f"{BASE}/api/questions", headers=HEADERS).json()
print(f"\nDone. Remaining questions: {len(remaining)}")
