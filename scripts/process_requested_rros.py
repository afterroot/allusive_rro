import os
import sys
import json
import shutil
import subprocess
from PIL import Image
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

from compile_rro import build_rro, package_magisk_module

# get current path
rootDir = os.getcwd()

repoDir = os.path.join(rootDir, "repo")
pointersDir = os.path.join(repoDir, "pointers")
rrosDir = os.path.join(repoDir, "rros")
modulesDir = os.path.join(repoDir, "modules")

# functions


def downloadPointer(pointerFile: str) -> bool:
    # check if directory exists
    if not os.path.exists(pointersDir):
        os.makedirs(pointersDir)

    target_file = os.path.join(pointersDir, pointerFile)
    if os.path.exists(target_file):
        return True

    res = subprocess.run(
        [
            "gsutil",
            "-q",
            "cp",
            f"gs://pointer-replacer.appspot.com/pointers/{pointerFile}",
            pointersDir,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if res.returncode != 0 or not os.path.exists(target_file):
        print(f"[!] Warning: Could not download {pointerFile} from Cloud Storage.")
        return False

    subprocess.run(
        ["git", "add", target_file],
        cwd=repoDir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def getFileName(path: str) -> str:
    return os.path.splitext(path)[0]


def buildRRO(pointerFile: str, pointerName: str = None, force: bool = False):
    img_path = os.path.join(pointersDir, pointerFile)
    if not os.path.exists(img_path):
        print(f"[!] Warning: Image {img_path} does not exist. Cannot build RRO.")
        return False

    stem = getFileName(pointerFile)
    out_apk = os.path.join(rrosDir, f"RRO_{stem}.apk")
    out_zip = os.path.join(modulesDir, f"RRO_{stem}.zip")
    out_apk_mouse = os.path.join(rrosDir, f"RRO_mouse_{stem}.apk")
    out_zip_mouse = os.path.join(modulesDir, f"RRO_mouse_{stem}.zip")

    os.makedirs(rrosDir, exist_ok=True)
    os.makedirs(modulesDir, exist_ok=True)

    built_any = False

    if not os.path.exists(out_apk) or not os.path.exists(out_zip) or force:
        build_rro(
            image_path=img_path,
            output_apk=out_apk,
            pointer_type="touch",
            verbose=False,
        )
        package_magisk_module(
            apk_path=out_apk,
            output_zip=out_zip,
            pointer_type="touch",
            pointer_name=pointerName,
            module_name=f"Pointer Replacer RRO - {pointerName if pointerName else stem}",
            verbose=False,
        )
        built_any = True

    if not os.path.exists(out_apk_mouse) or not os.path.exists(out_zip_mouse) or force:
        build_rro(
            image_path=img_path,
            output_apk=out_apk_mouse,
            pointer_type="mouse",
            verbose=False,
        )
        package_magisk_module(
            apk_path=out_apk_mouse,
            output_zip=out_zip_mouse,
            pointer_type="mouse",
            pointer_name=pointerName,
            module_name=f"Pointer Replacer RRO (Mouse) - {pointerName if pointerName else stem}",
            verbose=False,
        )
        built_any = True

    if built_any:
        # add RRO apks and Magisk zips to git
        subprocess.run(
            ["git", "add", out_apk, out_zip, out_apk_mouse, out_zip_mouse],
            cwd=repoDir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    else:
        return False


def init_firestore():
    try:
        keyJson = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    except KeyError:
        keyJson = "release/pointer-replacer-sa.json"

    cred = credentials.Certificate(keyJson)
    firebase_admin.initialize_app(cred)

    return firestore.client()


def update_firestore(documentId: str, hasRRO: bool, pointer_exists: bool = True):
    if not documentId:
        return
    if pointer_exists:
        batch.update(
            db.collection("pointers").document(documentId),
            {"hasRRO": hasRRO, "rroVersion": 2 if hasRRO else 1},
        )
    batch.update(
        db.collection("requests").document(documentId), {"isRequestClosed": hasRRO}
    )


# start

db = init_firestore()
batch = db.batch()

with open(os.path.join(rootDir, "data", "pointers.json"), "r") as f:
    pointers = json.load(f)

# Filter open requests where isRequestClosed is False
open_requests = [
    req for req in pointers.get("requests", []) if not req.get("isRequestClosed", False)
]
print(f"[*] Processing {len(open_requests)} open request(s)...")

if not open_requests:
    print("No open requests to process. Exiting.")
    sys.exit(0)

for i in open_requests:
    pointerFile = i["fileName"]
    docId = i.get("documentId")
    forceBuild = i.get("force", False)
    exclude = i.get("exclude", False)

    pointerName = None
    pointer_exists = True
    if docId:
        try:
            doc_snap = db.collection("pointers").document(docId).get()
            if doc_snap.exists:
                pointerName = doc_snap.to_dict().get("name")
            else:
                pointer_exists = False
        except Exception as e:
            print(f"[!] Could not fetch pointer name for {docId}: {e}")

    name_display = f" ({pointerName})" if pointerName else ""

    # Handle deleted pointers
    if not pointer_exists:
        print(f"[!] Closed (deleted): {pointerFile}{name_display}")
        if docId:
            batch.update(
                db.collection("requests").document(docId),
                {"isRequestClosed": True, "status": "pointer_deleted"},
            )
        i["isRequestClosed"] = True
        continue

    if not exclude:
        if not os.path.exists(os.path.join(pointersDir, pointerFile)):
            download_ok = downloadPointer(pointerFile)
        else:
            download_ok = True

        if download_ok:
            isRROBuilt = buildRRO(
                pointerFile, pointerName=pointerName, force=forceBuild
            )
            if isRROBuilt:
                print(f"[✓] Built: {pointerFile}{name_display}")
            else:
                print(f"[-] Up-to-date: {pointerFile}{name_display}")
        else:
            print(f"[!] Failed download: {pointerFile}{name_display}")
    else:
        print(f"[-] Excluded: {pointerFile}{name_display}")

    hasRRO = os.path.exists(
        os.path.join(rrosDir, f"RRO_{getFileName(pointerFile)}.apk")
    ) and os.path.exists(
        os.path.join(modulesDir, f"RRO_{getFileName(pointerFile)}.zip")
    )

    update_firestore(i.get("documentId"), hasRRO, pointer_exists=pointer_exists)
    i["isRequestClosed"] = hasRRO

try:
    batch.commit()
except Exception as e:
    print(f"[!] Error committing batch to Firestore: {e}")

# update pointers.json
with open(os.path.join(rootDir, "data", "pointers.json"), "w") as f:
    json.dump(pointers, f, indent=2, sort_keys=True, separators=(",", ": "))

print("Done.")
