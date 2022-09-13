import pymongo
import os

c = pymongo.MongoClient(os.environ['DOBERMAN_MONGO_URI'])

combined = []
depends_on = set()

db = c.pancake

for doc in db.sensors.find({'device': 'fsp_clippers'}):
    if 'pipelines' in doc:
        for pl in doc['pipelines']:
            if pl.startswith('alarm'):
                pl_doc = db.pipelines.find_one({'name': pl})
                depends_on |= set(pl_doc['depends_on'])
                for node in pl_doc['pipeline']:
                    node['name'] = f'{node["name"]}_{doc["name"]}'
                    if 'upstream' in node:
                        node['upstream'][0] = f'source_{doc["name"]}'
                    combined.append(node)

doc = {
        'name': 'alarm_ups',
        'pipeline': combined,
        'status': 'inactive',
        'node_config': {},
        'depends_on': list(depends_on)
        }
db.pipelines.update_one({'name': doc['name']}, {'$set': doc}, upsert=True)
