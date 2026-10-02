#!/usr/bin/env python3
import subprocess
import time

CONTAINER_NAME = "referee-worker-1"
MAX_HEALS = 5

def check_and_heal():
    attempt = 1
    while True:
        try:
            # Check the container state directly inside the Docker engine
            status = subprocess.check_output(f"docker inspect -f '{{{{.State.Status}}}}' {CONTAINER_NAME}", shell=True).decode().strip()
            if status in ["restarting", "exited"]:
                print(f"[ALERT] Container {CONTAINER_NAME} is failing! Restarting worker...")
                subprocess.run("docker compose restart worker", shell=True)
                attempt += 1
                if attempt > MAX_HEALS:
                    print("[FATAL] Auto-heal threshold exhausted.")
                    break
        except Exception as e:
            print(f"Watchdog error: {e}")
        time.sleep(10)

if __name__ == "__main__":
    check_and_heal()
