import os
import json
import shutil
# from PIL import Image

# get cureent path
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


""" def resizeAndSavePointer(pointerFile: str):
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

 """


def buildRROApk(pointerFile: str):
    if not os.path.exists(os.path.join(rrosDir, f'RRO_{getFileName(pointerFile)}.apk')):
        # resizeAndSavePointer(pointerFile)

        print('Buiilding RRO Apk...')
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


def pushRepo():
    os.chdir(repoDir)
    os.system('git add .')
    os.system('git commit -m "update pointers"')
    os.system('git push')
    os.chdir(rootDir)
    os.system('git add repo')
    os.system('git commit -m "update repo"')
    os.system('git push')


# start
with open(os.path.join(rootDir, 'data', 'pointers.json'), 'r') as f:
    pointers = json.load(f)

for i in pointers['requests']:
    pointerFile = i['fileName']
    downloaded = False

    if not os.path.exists(os.path.join(pointersDir, pointerFile)):
        downloaded = True
        downloadPointer(pointerFile)

    isRROBuilt = buildRROApk(pointerFile)
    print(f'{pointerFile} | Downloaded-{downloaded} | RRO Builded-{isRROBuilt}')

# pushRepo()
print('Stopping gradle daemon...')
os.system('./gradlew --stop')
