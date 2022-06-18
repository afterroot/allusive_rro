import os
import json
import shutil
from PIL import Image
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# get current path
rootDir = os.getcwd()

repoDir = os.path.join(rootDir, 'repo')
pointersDir = os.path.join(repoDir, 'pointers')
rrosDir = os.path.join(repoDir, 'rros')

# functions


def downloadPointer(pointerFile: str):
    # check if directory exists
    if not os.path.exists(pointersDir):
        os.makedirs(pointersDir)

    print(f'Downloading {pointerFile}...')
    os.system(
        f'gsutil cp gs://pointer-replacer.appspot.com/pointers/{pointerFile} {pointersDir}')
    os.chdir(repoDir)
    os.system(f'git add {os.path.join(pointersDir, pointerFile)}')
    os.chdir(rootDir)


def getFileName(path: str) -> str:
    return os.path.splitext(path)[0]


def resizeAndSavePointer(pointerFile: str):
    print(f'Saving {pointerFile}...')
    im = Image.open(os.path.join(pointersDir, pointerFile))
    im.resize((49, 49)).save(
        os.path.join(rootDir, 'app', 'src', 'main', 'res',
                     'drawable-hdpi-v4', 'pointer_spot_touch.png'))
    im.resize((33, 33)).save(
        os.path.join(rootDir, 'app', 'src', 'main', 'res',
                     'drawable-mdpi-v4', 'pointer_spot_touch.png'))
    im.resize((66, 66)).save(
        os.path.join(rootDir, 'app', 'src', 'main', 'res',
                     'drawable-xhdpi-v4', 'pointer_spot_touch.png'))


def buildRROApk(pointerFile: str, force: bool = False):
    if not os.path.exists(os.path.join(rrosDir, f'RRO_{getFileName(pointerFile)}.apk')) or force:
        resizeAndSavePointer(pointerFile)

        print(f'Building RRO Apk... | Force: {force}')
        if os.name == 'nt':
            os.system(
                f'gradlew assembleRelease -PpointerName={pointerFile} --daemon')
        else:
            os.system(
                f'./gradlew assembleRelease -PpointerName={pointerFile} --daemon')

        # check if directory exists
        if not os.path.exists(rrosDir):
            os.makedirs(rrosDir)

        shutil.copyfile(os.path.join(rootDir, 'app', 'build', 'outputs', 'apk', 'release', 'app-release.apk'),
                        os.path.join(rrosDir, f'RRO_{getFileName(pointerFile)}.apk'))

        # add RRO apk to git
        os.chdir(rrosDir)
        os.system('git add ' + os.path.join(rrosDir,
                  f'RRO_{getFileName(pointerFile)}.apk'))
        os.chdir(rootDir)
        return True
    else:
        return False


def init_firestore():
    try:
        keyJson = os.environ['GOOGLE_APPLICATION_CREDENTIALS']
    except KeyError:
        keyJson = 'release/pointer-replacer-sa.json'

    cred = credentials.Certificate(keyJson)
    firebase_admin.initialize_app(cred)

    return firestore.client()


def update_firestore(documentId: str, hasRRO: bool):
    batch.update(db.collection('pointers').document(
        documentId), {'hasRRO': hasRRO})
    batch.update(db.collection('requests').document(
        documentId), {'isRequestClosed': hasRRO})


# start

db = init_firestore()
batch = db.batch()

with open(os.path.join(rootDir, 'data', 'pointers.json'), 'r') as f:
    pointers = json.load(f)

for i in pointers['requests']:
    pointerFile = i['fileName']
    forceBuild = i.get('force', False)
    exclude = i.get('exclude', False)
    downloaded = False

    if not exclude:
        if not os.path.exists(os.path.join(pointersDir, pointerFile)):
            downloaded = True
            downloadPointer(pointerFile)

        isRROBuilt = buildRROApk(pointerFile, forceBuild)
        print(f'{pointerFile} | Downloaded-{downloaded} | RRO Built-{isRROBuilt}')
    else:
        print(f'{pointerFile} | Downloaded-Excluded | RRO Built-Excluded')

    hasRRO = os.path.exists(os.path.join(
        rrosDir, f'RRO_{getFileName(pointerFile)}.apk'))

    update_firestore(i['documentId'], hasRRO)

    index = pointers['requests'].index(i)
    pointers['requests'][index]['isRequestClosed'] = hasRRO

print('Updating in Firestore...')
batch.commit()

# update pointers.json
print('Updating pointers.json...')
with open(os.path.join(rootDir, 'data', 'pointers.json'), 'w') as f:
    json.dump(pointers, f,
              indent=2,
              sort_keys=True,
              separators=(',', ': '))

print('Stopping gradle daemon...')
if os.name == 'nt':
    os.system('gradlew --stop')
else:
    os.system('./gradlew --stop')
