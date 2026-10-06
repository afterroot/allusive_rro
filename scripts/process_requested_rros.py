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


def downloadPointer(pointerFile: str):
    # check if directory exists
    if not os.path.exists(pointersDir):
        os.makedirs(pointersDir)

    print(f"Downloading {pointerFile}...")
    os.system(
        f"gsutil cp gs://pointer-replacer.appspot.com/pointers/{pointerFile} {pointersDir}"
    )
    os.chdir(repoDir)
    os.system(f"git add {os.path.join(pointersDir, pointerFile)}")
    os.chdir(rootDir)


def getFileName(path: str) -> str:
    return os.path.splitext(path)[0]


def buildRRO(pointerFile: str, pointerName: str = None, force: bool = False):
    stem = getFileName(pointerFile)
    out_apk = os.path.join(rrosDir, f"RRO_{stem}.apk")
    out_zip = os.path.join(modulesDir, f"RRO_{stem}.zip")

    os.makedirs(rrosDir, exist_ok=True)
    os.makedirs(modulesDir, exist_ok=True)

    if not os.path.exists(out_apk) or not os.path.exists(out_zip) or force:
        img_path = os.path.join(pointersDir, pointerFile)
        print(f"Building RRO 2.0 Apk & Module ZIP for {pointerFile} ({pointerName or stem})... | Force: {force}")
        build_rro(image_path=img_path, output_apk=out_apk)
        package_magisk_module(
            apk_path=out_apk,
            output_zip=out_zip,
            pointer_name=pointerName,
            module_name=f"Pointer Replacer RRO - {pointerName if pointerName else stem}",
        )

        # add RRO apk and Magisk zip to git
        os.chdir(repoDir)
        os.system(f"git add {out_apk} {out_zip}")
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


def update_firestore(documentId: str, hasRRO: bool):
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
    if docId:
        try:
            doc_snap = db.collection("pointers").document(docId).get()
            if doc_snap.exists:
                pointerName = doc_snap.to_dict().get("name")
        except Exception as e:
            print(f"Could not fetch pointer name for {docId}: {e}")

    if not exclude:
        if not os.path.exists(os.path.join(pointersDir, pointerFile)):
            downloaded = True
            downloadPointer(pointerFile)

        isRROBuilt = buildRRO(pointerFile, pointerName=pointerName, force=forceBuild)
        print(f"{pointerFile} ({pointerName or 'No Name'}) | Downloaded-{downloaded} | RRO Built-{isRROBuilt}")
    else:
        print(f"{pointerFile} | Downloaded-Excluded | RRO Built-Excluded")

    hasRRO = os.path.exists(
        os.path.join(rrosDir, f"RRO_{getFileName(pointerFile)}.apk")
    ) and os.path.exists(
        os.path.join(modulesDir, f"RRO_{getFileName(pointerFile)}.zip")
    )

    if i["isRequestClosed"] == False:
        update_firestore(i["documentId"], hasRRO)

    index = pointers["requests"].index(i)
    pointers["requests"][index]["isRequestClosed"] = hasRRO

print("Updating in Firestore...")
batch.commit()

# update pointers.json
print("Updating pointers.json...")
with open(os.path.join(rootDir, "data", "pointers.json"), "w") as f:
    json.dump(pointers, f, indent=2, sort_keys=True, separators=(",", ": "))

print("Done!")
