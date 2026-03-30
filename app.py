from flask import Flask, render_template, jsonify, request
from scraper import get_walmart_deals, get_sams_deals
import threading
import time

app = Flask(__name__)

_cache: dict[str, dict] = {}
_cache_time: dict[str, float] = {}
_locks: dict[str, threading.Lock] = {
    "walmart": threading.Lock(),
    "sams": threading.Lock(),
}
CACHE_TTL = 1800


def get_cached(key: str, fetcher):
    now = time.time()
    if key in _cache and (now - _cache_time.get(key, 0)) < CACHE_TTL:
        return _cache[key]
    with _locks[key]:
        # Re-check after acquiring lock (another thread may have just fetched)
        now = time.time()
        if key in _cache and (now - _cache_time.get(key, 0)) < CACHE_TTL:
            return _cache[key]
        _cache[key] = fetcher()
        _cache_time[key] = time.time()
        return _cache[key]


def bust(key: str, fetcher):
    _cache.pop(key, None)
    _cache_time.pop(key, None)
    return get_cached(key, fetcher)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/deals")
def api_deals():
    retailer = request.args.get("retailer", "walmart")
    fn = get_sams_deals if retailer == "sams" else get_walmart_deals
    return jsonify(get_cached(retailer, fn))


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    retailer = request.args.get("retailer", "walmart")
    fn = get_sams_deals if retailer == "sams" else get_walmart_deals
    return jsonify(bust(retailer, fn))


def _prewarm():
    time.sleep(1)
    print("[prewarm] Walmart...")
    get_cached("walmart", get_walmart_deals)
    print("[prewarm] Sam's Club...")
    get_cached("sams", get_sams_deals)
    print("[prewarm] Listo.")


if __name__ == "__main__":
    threading.Thread(target=_prewarm, daemon=True).start()
    app.run(debug=False, port=5004)
