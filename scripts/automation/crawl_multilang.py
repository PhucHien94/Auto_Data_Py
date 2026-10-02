# -*- coding: utf-8 -*-
"""Gọi API search THẬT cho bản dịch KO/EN/RU/ZH của bộ keyword tiếng Việt.

Mục đích: tìm những keyword mà CÙNG MỘT Ý NGHĨA nhưng viết bằng ngôn ngữ khác
lại ra kết quả khác -> engine chưa xử lý nhất quán giữa các ngôn ngữ.

Quyết định thiết kế (user chốt 2026-09-14):
  - lang LUÔN = "vi". Chỉ CHUỖI QUERY đổi ngôn ngữ.
    Lý do: thăm dò cho thấy tham số lang tự nó đã làm đổi tập kết quả
    (query "sữa" với lang=ko trả 0/10 SKU trùng so với lang=vi). Giữ lang cố
    định thì khác biệt đo được chỉ đến từ chuỗi query, không lẫn biến locale.
  - Tiếng Nhật bị loại: API trả HTTP 400 cho cả lang=ja lẫn lang=jp.
    Thay bằng tiếng Trung (zh) - được API chấp nhận.

Ghi NDJSON từng dòng ngay khi có kết quả, và bỏ qua dòng đã có khi chạy lại,
nên gateway sập giữa chừng (đã xảy ra 10/09) thì chạy lại chỉ bù phần thiếu.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SEARCH_URL = "https://dev-gateway.martonline.lotte.vn/api/v2/{lang}/{store}/products/search"
LANGS = ["ko", "en", "ru", "zh"]


def call_search(query, store, lang_param, page_size, timeout=30):
    """Trả về (skus, names, resolved_mode, latency_ms, error)."""
    url = SEARCH_URL.format(lang=lang_param, store=store)
    body = {
        "query": query, "storeId": store, "page": 1, "pageSize": page_size,
        "sort": "relevance", "filters": {}, "lang": lang_param, "trace": False,
    }
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-search-mode": "adaptive"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - ghi lại mọi lỗi để đếm, không dừng cả batch
        return None, None, None, int((time.time() - t0) * 1000), str(e)
    ms = int((time.time() - t0) * 1000)
    products = data.get("products") or []
    skus = [str(p.get("sku")) for p in products]
    names = [p.get("name") or p.get("productName") for p in products]
    return skus, names, data.get("resolvedMode"), ms, None


def load_done(path):
    """Các cặp (test_id, lang) đã crawl xong ở lần chạy trước."""
    done = set()
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue  # dòng ghi dở do bị kill giữa chừng
                if not r.get("error"):
                    done.add((r["test_id"], r["lang"]))
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--translations", default="SmartSearch/test_data/multilang/translations.json")
    ap.add_argument("--out", default="SmartSearch/test_data/multilang/multilang_raw.ndjson")
    ap.add_argument("--store", default="nsg")
    ap.add_argument("--lang-param", default="vi",
                    help="giá trị lang gửi lên API. 'vi' (mặc định): giữ cố định, chỉ "
                         "chuỗi query đổi ngôn ngữ - cô lập biến. 'match': lang ĐI THEO "
                         "ngôn ngữ của query (query tiếng Hàn -> lang=ko) - mô phỏng "
                         "đúng người dùng thật đang đổi ngôn ngữ trên app.")
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--langs", default=",".join(LANGS))
    ap.add_argument("--limit", type=int, default=None, help="cắt bớt số query, để chạy thử")
    ap.add_argument("--sleep-ms", type=int, default=0)
    ap.add_argument("--progress-every", type=int, default=100)
    args = ap.parse_args()

    tpath = ROOT / args.translations
    opath = ROOT / args.out
    opath.parent.mkdir(parents=True, exist_ok=True)
    items = json.loads(tpath.read_text(encoding="utf-8"))["items"]
    if args.limit:
        items = items[: args.limit]
    langs = [x.strip() for x in args.langs.split(",") if x.strip()]

    done = load_done(opath)
    todo = [(it, lg) for it in items for lg in langs if (it["test_id"], lg) not in done]
    total = len(items) * len(langs)
    print(f"Bộ dịch: {len(items)} query x {len(langs)} ngôn ngữ = {total} request")
    print(f"Đã có sẵn (bỏ qua): {len(done)}   |   Cần gọi lần này: {len(todo)}")
    if args.lang_param == "match":
        print("lang gửi lên API = KHỚP ngôn ngữ query (query ko -> lang=ko, en -> lang=en)\n")
    else:
        print(f"lang gửi lên API = '{args.lang_param}' (CHỈ chuỗi query đổi ngôn ngữ)\n")

    # preflight: hỏng ngay từ đầu thì dừng luôn, đừng đốt cả batch
    _pre_lang = "vi" if args.lang_param == "match" else args.lang_param
    _, _, _, _, err = call_search("sữa", args.store, _pre_lang, 5)
    if err:
        sys.exit(f"Preflight thất bại - API không trả lời: {err}")
    print("Preflight OK - bắt đầu crawl.\n")

    t0 = time.time()
    n_err = 0
    with open(opath, "a", encoding="utf-8") as f:
        for i, (it, lg) in enumerate(todo):
            q = it[lg]
            # 'match': lang đi theo ngôn ngữ của chính chuỗi query. Đây là đường
            # mà người dùng thật đi khi họ đổi ngôn ngữ hiển thị trên app, khác
            # hẳn chế độ lang=vi cố định (chỉ đo khả năng hiểu chữ của engine).
            lang_sent = lg if args.lang_param == "match" else args.lang_param
            skus, names, mode, ms, err = call_search(q, args.store, lang_sent, args.page_size)
            if err:
                n_err += 1
            f.write(json.dumps({
                "test_id": it["test_id"], "lang": lg, "lang_sent": lang_sent,
                "vi": it["vi"], "query": q,
                "skus": skus, "names": names[:20] if names else None,
                "resolved_mode": mode, "latency_ms": ms, "error": err,
            }, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % args.progress_every == 0:
                el = time.time() - t0
                print(f"  ... {i + 1}/{len(todo)}, {el:.0f}s, "
                      f"{(i + 1) / el:.2f} req/s, lỗi={n_err}")
            if args.sleep_ms:
                time.sleep(args.sleep_ms / 1000)

    print(f"\nXong ({time.time() - t0:.0f}s). Lỗi: {n_err}/{len(todo)}")
    print(f"-> {opath}")


if __name__ == "__main__":
    main()
