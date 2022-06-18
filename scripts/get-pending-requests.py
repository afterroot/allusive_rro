import os
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# get current path
rootDir = os.getcwd()


def init_firestore():
    try:
        keyJson = os.environ['GOOGLE_APPLICATION_CREDENTIALS']
    except KeyError:
        keyJson = 'release/pointer-replacer-sa.json'

    cred = credentials.Certificate(keyJson)
    firebase_admin.initialize_app(cred)

    return firestore.client()


db = init_firestore()

with open(os.path.join(rootDir, 'data', 'pointers.json'), 'r') as f:
    pointers = json.load(f)

requestsRef = db.collection('requests')

query_open_requests = requestsRef.where(
    'isRequestClosed', '==', False).stream()

requests = []
for doc in query_open_requests:
    doc_dict = doc.to_dict()
    # convert timestapmp to string
    doc_dict['timestamp'] = doc_dict['timestamp'].__str__()
    pointers['requests'].append(doc_dict)
    requests.append(doc_dict)

removed_dups = [i for n, i in enumerate(
    pointers['requests']) if i not in pointers['requests'][n + 1:]]

pointers['requests'] = removed_dups

# update pointers.json
print('Updating pointers.json...')
with open(os.path.join(rootDir, 'data', 'pointers.json'), 'w') as f:
    json.dump(pointers, f,
              indent=2,
              sort_keys=True,
              separators=(',', ': '))
