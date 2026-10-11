import os
import json
import shutil
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

    print(f"Downloading {pointerFile}...")
    ret = os.system(
        f"gsutil cp gs://pointer-replacer.appspot.com/pointers/{pointerFile} {pointersDir}"
    )
    if ret != 0 or not os.path.exists(target_file):
        print(f"[!] Warning: Could not download {pointerFile} from Cloud Storage.")
        return False

    os.chdir(repoDir)
    os.system(f"git add {target_file}")
    os.chdir(rootDir)
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
        print(f"Building Touch RRO 2.0 Apk & Module ZIP for {pointerFile} ({pointerName or stem})... | Force: {force}")
        build_rro(image_path=img_path, output_apk=out_apk, pointer_type="touch")
        package_magisk_module(
            apk_path=out_apk,
            output_zip=out_zip,
            pointer_type="touch",
            pointer_name=pointerName,
            module_name=f"Pointer Replacer RRO - {pointerName if pointerName else stem}",
        )
        built_any = True

    if not os.path.exists(out_apk_mouse) or not os.path.exists(out_zip_mouse) or force:
        print(f"Building Mouse RRO 2.0 Apk & Module ZIP for {pointerFile} ({pointerName or stem})... | Force: {force}")
        build_rro(image_path=img_path, output_apk=out_apk_mouse, pointer_type="mouse")
        package_magisk_module(
            apk_path=out_apk_mouse,
            output_zip=out_zip_mouse,
            pointer_type="mouse",
            pointer_name=pointerName,
            module_name=f"Pointer Replacer RRO (Mouse) - {pointerName if pointerName else stem}",
        )
        built_any = True

    if built_any:
        # add RRO apks and Magisk zips to git
        os.chdir(repoDir)
        os.system(f"git add {out_apk} {out_zip} {out_apk_mouse} {out_zip_mouse}")
        os.chdir(rootDir)
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

for i in pointers["requests"]:
    pointerFile = i["fileName"]
    docId = i.get("documentId")
    forceBuild = i.get("force", False)
    exclude = i.get("exclude", False)
    downloaded = False

    pointerName = None
    pointer_exists = True
    if docId:
        try:
            doc_snap = db.collection("pointers").document(docId).get()
            if doc_snap.exists:
                pointerName = doc_snap.to_dict().get("name")
            else:
                pointer_exists = False
                print(f"[!] Pointer document {docId} does not exist in Firestore (deleted).")
        except Exception as e:
            print(f"Could not fetch pointer name for {docId}: {e}")

    # Handle deleted pointers
    if not pointer_exists:
        print(f"Skipping build for deleted pointer {docId} ({pointerFile}) and closing request.")
        if docId:
            batch.update(
                db.collection("requests").document(docId),
                {"isRequestClosed": True, "status": "pointer_deleted"},
            )
        index = pointers["requests"].index(i)
        pointers["requests"][index]["isRequestClosed"] = True
        continue

    if not exclude:
        if not os.path.exists(os.path.join(pointersDir, pointerFile)):
            download_ok = downloadPointer(pointerFile)
            downloaded = download_ok
        else:
            download_ok = True

        if download_ok:
            isRROBuilt = buildRRO(pointerFile, pointerName=pointerName, force=forceBuild)
        else:
            isRROBuilt = False
            print(f"[!] Skipping RRO build for {pointerFile} because image could not be downloaded.")

        print(f"{pointerFile} ({pointerName or 'No Name'}) | Downloaded-{downloaded} | RRO Built-{isRROBuilt}")
    else:
        print(f"{pointerFile} | Downloaded-Excluded | RRO Built-Excluded")

    hasRRO = os.path.exists(
        os.path.join(rrosDir, f"RRO_{getFileName(pointerFile)}.apk")
    ) and os.path.exists(
        os.path.join(modulesDir, f"RRO_{getFileName(pointerFile)}.zip")
    )

    if i.get("isRequestClosed") == False:
        update_firestore(i.get("documentId"), hasRRO, pointer_exists=pointer_exists)

    index = pointers["requests"].index(i)
    pointers["requests"][index]["isRequestClosed"] = hasRRO

print("Updating in Firestore...")
try:
    batch.commit()
except Exception as e:
    print(f"[!] Error committing batch to Firestore: {e}")

# update pointers.json
print("Updating pointers.json...")
with open(os.path.join(rootDir, "data", "pointers.json"), "w") as f:
    json.dump(pointers, f, indent=2, sort_keys=True, separators=(",", ": "))

print("Done!")
