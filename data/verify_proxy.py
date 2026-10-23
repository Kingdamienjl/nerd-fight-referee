import requests, json
URL = "http://litellm:4000/v1/chat/completions"
BODY = {"model": "harvester-extract",
        "messages": [{"role": "user", "content": "Reply with the word: pong"}],
        "max_tokens": 8}

def attempt(label, headers):
    try:
        r = requests.post(URL, json=BODY, headers=headers, timeout=90)
        print(f"{label}: HTTP {r.status_code} -> {r.text[:220]}")
    except Exception as e:
        print(f"{label}: EXC {type(e).__name__}: {e}")

attempt("NO-AUTH", {"Content-Type": "application/json"})
attempt("SK-TEST", {"Content-Type": "application/json", "Authorization": "Bearer sk-test"})
print("PROXY TEST DONE")
