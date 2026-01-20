import os
import sys
import time
import threading
from queue import Queue

import requests
from tqdm import tqdm
from dotenv import load_dotenv

# -----------------------------------------------------
# LOAD CREDENTIALS
# -----------------------------------------------------

load_dotenv()

USER = os.getenv("SENTINEL_USER")
PASS = os.getenv("SENTINEL_PASS")

if not USER or not PASS:
    print("ERROR: set SENTINEL_USER and SENTINEL_PASS in .env")
    sys.exit(1)

# -----------------------------------------------------
# CONFIG
# -----------------------------------------------------

CONFIG = {
    "workers": 10,
    "chunk_mb": 16,
    "max_retries": 3,
    "download_dir": "downloads",
    "timeout": 60,
    "backoff_429": 30,
}

# -----------------------------------------------------
# DOWNLOADER CLASS
# -----------------------------------------------------

class CDSEDownloader:
    """
    Copernicus Data Space Ecosystem downloader
    Works for Sentinel-1 and Sentinel-2
    """

    def __init__(self, user, password):
        self.user = user
        self.password = password

        self.token = None
        self.token_time = 0
        self.lock = threading.Lock()

        os.makedirs(CONFIG["download_dir"], exist_ok=True)

    # -------------------------------------------------

    def get_token(self):
        """Refresh token if older than 10 min"""

        with self.lock:
            if self.token and time.time() - self.token_time < 600:
                return self.token

            url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

            r = requests.post(
                url,
                data={
                    "grant_type": "password",
                    "username": self.user,
                    "password": self.password,
                    "client_id": "cdse-public",
                },
                timeout=20,
            )

            r.raise_for_status()

            self.token = r.json()["access_token"]
            self.token_time = time.time()

            return self.token

    # -------------------------------------------------

    def get_meta(self, pid):
        url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({pid})"

        h = {"Authorization": f"Bearer {self.get_token()}"}

        r = requests.get(url, headers=h, timeout=20)
        r.raise_for_status()

        return r.json()

    # -------------------------------------------------

    def download_one(self, pid):
        """
        Download single product with resume & retry
        """

        meta = self.get_meta(pid)

        name = meta.get("Name", pid) + ".zip"
        size = meta.get("ContentLength")

        out = os.path.join(CONFIG["download_dir"], name)

        downloaded = os.path.getsize(out) if os.path.exists(out) else 0

        url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({pid})/$value"

        headers = {
            "Authorization": f"Bearer {self.get_token()}",
            "Range": f"bytes={downloaded}-",
        }

        for attempt in range(1, CONFIG["max_retries"] + 1):

            try:
                with requests.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=CONFIG["timeout"],
                ) as r:

                    # ---- AUTH EXPIRED ----
                    if r.status_code in [401, 403]:
                        self.token = None
                        headers["Authorization"] = f"Bearer {self.get_token()}"
                        continue

                    # ---- RATE LIMIT ----
                    if r.status_code == 429:
                        print(f"429 received, sleeping {CONFIG['backoff_429']}s")
                        time.sleep(CONFIG["backoff_429"])
                        continue

                    r.raise_for_status()

                    mode = "ab" if downloaded else "wb"

                    with open(out, mode) as f, tqdm(
                        desc=name[-40:],
                        total=size,
                        initial=downloaded,
                        unit="B",
                        unit_scale=True,
                    ) as bar:

                        for chunk in r.iter_content(
                            chunk_size=CONFIG["chunk_mb"] * 1024 * 1024
                        ):
                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))

                # ---- VERIFY SIZE ----
                final = os.path.getsize(out)

                if size and final != size:
                    raise Exception(
                        f"Size mismatch {final} != {size}"
                    )

                return out

            except Exception as e:
                print(f"[Attempt {attempt}] Error {pid}: {e}")

                time.sleep(5 * attempt)

        raise Exception(f"FAILED after retries: {pid}")

# -----------------------------------------------------
# WORKERS
# -----------------------------------------------------

def worker(q, dl):
    while True:
        pid = q.get()

        try:
            file = dl.download_one(pid)
            print("READY:", file)

        except Exception as e:
            print("ERROR:", pid, e)

        q.task_done()

# -----------------------------------------------------
# MAIN
# -----------------------------------------------------

def run(ids):

    dl = CDSEDownloader(USER, PASS)

    q = Queue()

    # start workers
    for _ in range(CONFIG["workers"]):
        t = threading.Thread(target=worker, args=(q, dl), daemon=True)
        t.start()

    for pid in ids:
        pid = pid.strip()
        if pid:
            q.put(pid)

    q.join()


def read_ids(path):
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python sentinel_downloader.py ids.txt")
        sys.exit(1)

    ids = read_ids(sys.argv[1])

    print(f"Downloading {len(ids)} products with {CONFIG['workers']} workers")

    run(ids)
