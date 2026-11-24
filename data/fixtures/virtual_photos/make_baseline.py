"""얼굴 찾기 기준선: 장면 속 얼굴마다 21명 중 누구인지 Rekognition으로 고르고 정답표와 맞춰 본다.

한 번에 21명과 비교하려고 정면 얼굴 21장을 격자 한 장(gallery.jpg)으로 붙이고,
장면 얼굴 조각을 source, 격자를 target으로 CompareFaces 한 번 부른다(얼굴 1개당 호출 1번, 새 AWS 자원 없음).
사용: AWS_PROFILE=<팀 프로필> python3 make_baseline.py <이 폴더>   → <이 폴더>/baseline.json
가상 사진만 보낸다. 실제 아이 사진을 이 스크립트에 넣지 않는다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

PACK = sys.argv[1]
THRESH = 80.0
COLS, CELL = 7, 240


def aws(*args, tries=6):
    for n in range(tries):
        p = subprocess.run(["aws", "--region", os.environ.get("AWS_REGION", "ap-northeast-2"), "rekognition", *args,
                            "--output", "json"], capture_output=True, text=True)
        if p.returncode == 0:
            return json.loads(p.stdout)
        if "Throttl" in p.stderr or "ProvisionedThroughput" in p.stderr:
            time.sleep(2 ** n)
            continue
        raise RuntimeError(p.stderr.strip()[-300:])
    raise RuntimeError("throttled")


def tmp_jpeg(im):
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, dir=TMP)
    im.save(f, "JPEG", quality=92)
    f.close()
    return f.name


def detect(path):
    return aws("detect-faces", "--image-bytes", f"fileb://{path}")["FaceDetails"]


def crop(im, box, scale=1.8):
    w, h = im.size
    cx, cy = (box["Left"] + box["Width"] / 2) * w, (box["Top"] + box["Height"] / 2) * h
    half = max(box["Width"] * w, box["Height"] * h) * scale / 2
    c = im.crop((max(0, cx - half), max(0, cy - half), min(w, cx + half), min(h, cy + half)))
    if min(c.size) < 120:
        c = c.resize((max(120, c.size[0] * 120 // min(c.size)), max(120, c.size[1] * 120 // min(c.size))))
    return c


TMP = tempfile.mkdtemp(prefix="baseline_")
manifest = json.load(open(f"{PACK}/manifest.json"))
keys = [c["key"] for c in manifest["children"]]

# 1. 격자: 정면 사진에서 얼굴만 잘라 7×3으로 붙인다.
grid = Image.new("RGB", (COLS * CELL, -(-len(keys) // COLS) * CELL), "white")
for i, k in enumerate(keys):
    path = f"{PACK}/faces/{k}_front.jpg"
    im = Image.open(path).convert("RGB")
    face = max(detect(path), key=lambda f: f["BoundingBox"]["Width"])
    grid.paste(crop(im, face["BoundingBox"], 1.6).resize((CELL - 20, CELL - 20)), ((i % COLS) * CELL + 10, (i // COLS) * CELL + 10))
gallery = f"{TMP}/gallery.jpg"
grid.save(gallery, "JPEG", quality=92)
assert len(detect(gallery)) == len(keys), "격자에서 21명 얼굴이 다 잡히지 않음"


def cell_of(box):
    gw, gh = grid.size
    cx, cy = (box["Left"] + box["Width"] / 2) * gw, (box["Top"] + box["Height"] / 2) * gh
    i = int(cy // CELL) * COLS + int(cx // CELL)
    return keys[i] if 0 <= i < len(keys) else None


def identify(face_path):
    r = aws("compare-faces", "--source-image-bytes", f"fileb://{face_path}", "--target-image-bytes", f"fileb://{gallery}",
            "--similarity-threshold", "0")
    sims = {}
    for m in r["FaceMatches"]:
        k = cell_of(m["Face"]["BoundingBox"])
        if k:
            sims[k] = max(sims.get(k, 0), round(m["Similarity"], 1))
    return sims


def run(photo):
    path = f"{PACK}/{photo['file']}"
    im = Image.open(path).convert("RGB")
    faces = []
    for f in detect(path):
        if f["Confidence"] < 90:
            continue
        try:
            sims = identify(tmp_jpeg(crop(im, f["BoundingBox"])))
        except RuntimeError as e:   # 조각에서 얼굴을 못 찾는 경우(옆얼굴·작은 얼굴)
            sims = {"error": str(e)[-80:]}
        faces.append(sims)
    return photo["file"], faces


targets = [p for p in manifest["photos"] if p["kind"] in ("solo", "small_group", "group", "blurry", "no_face", "unknown_kids", "face_side")]
with ThreadPoolExecutor(4) as pool:
    found = dict(pool.map(run, targets))

# 2. 채점
summary, rows, same, diff, margin = {}, [], [], [], []
for p in targets:
    truth = {c["key"] for c in p["children"]}
    tags, faces = [], found[p["file"]]
    for sims in faces:
        if "error" in sims or not sims:
            continue
        best = max(sims, key=sims.get)
        if best in truth:
            same.append(sims[best])
            margin.append(round(sims[best] - max([v for k, v in sims.items() if k != best], default=0), 1))
        diff += [v for k, v in sims.items() if k not in truth]
        if sims[best] >= THRESH:
            tags.append(best)
    kind = "scene" if p["kind"] in ("solo", "small_group", "group") else p["kind"]
    s = summary.setdefault(kind, {"photos": 0, "children": 0, "found": 0, "tags": 0, "wrong": 0, "faces_detected": 0})
    s["photos"] += 1
    s["children"] += len(truth)
    s["faces_detected"] += len(faces)
    s["found"] += len(truth & set(tags))
    s["tags"] += len(tags)
    s["wrong"] += sum(t not in truth for t in tags)
    rows.append({"file": p["file"], "truth": sorted(truth), "tags": tags, "faces": faces})
for s in summary.values():
    s["recall"] = round(s["found"] / s["children"], 3) if s["children"] else None
    s["wrong_rate"] = round(s["wrong"] / s["tags"], 3) if s["tags"] else 0.0


def dist(v):
    v = sorted(v)
    return {"n": len(v), "min": v[0], "p05": v[len(v) // 20], "median": v[len(v) // 2], "max": v[-1]} if v else {}


out = {"date": time.strftime("%Y-%m-%d"), "region": "ap-northeast-2", "threshold": THRESH,
       "method": "장면 얼굴 조각(source) 대 정면 21명 격자(target) CompareFaces, 가장 비슷한 아이가 기준 이상이면 태그",
       "summary": summary, "same_child_similarity": dist(same), "other_child_similarity": dist(diff),
       "best_minus_second": dist(margin), "photos": rows}
json.dump(out, open(f"{PACK}/baseline.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("summary", "same_child_similarity", "other_child_similarity", "best_minus_second")}, ensure_ascii=False, indent=1))
