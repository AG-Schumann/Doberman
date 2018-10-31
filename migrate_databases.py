import psycopg2
import pymongo
import tqdm
import sys

conn_sql = "host='localhost' dbname='GeMSEDB' user='postgres' password='low-background'"
conn_mongo = "mongodb://doberman:l0wbackground@localhost:27017"

try:
    print('Connecting to sql...')
    db_sql = psycopg2.connect(conn_sql)
except Exception as e:
    print('Failed! %s' % e)
    sys.exit(1)

try:
    print('Connecting to mongo...')
    db_mongo = pymongo.MongoClient(**conn_mongo)
except Exception as e:
    print('Failed! %s' % e)
    db_sql.close()
    sys.exit(1)

def getDataTableNames():
    select_str = "SELECT relname FROM pg_class WHERE relkind='r' AND relname ~ '^data';"
    cur = db_sql.cursor()
    cur.execute(select_str)
    names = [t[0] for t in cur.fetchall()]
    cur.close()
    return names

def getEntryCount(tablename):
    count_str = 'SELECT count(*) FROM %s;' % tablename
    cur = db_sql.cursor()
    for row in cur.execute(count_str):
        num = row[0]
    cur.close()
    return num

def getEntriesFromTable(tablename):
    select_str = "SELECT datetime,data,status FROM %s;" % tablename
    cur = db_sql.cursor()
    cur.execute(select_str)
    for row in cur.fetchall():
        yield row
    cur.close()

errors = []
broken = False
for table in tqdm.tqdm(getDataTableNames(), desc='Tables'):
    #tqdm.tqdm.write('Migrating %s...' % table)
    collection_name = table.split('_', maxsplit=1)[1]
    db_mongo.create_collection(collection_name)
    collection = db_mongo['data'][table.split('_',maxsplit=1)[1]]
    collection.create_index('when')
    fields = ['when', 'data', 'status']
    for i,entry in tqdm.tqdm(enumerate(getEntriesFromTable(table)), desc=table, leave=False, total=getEntryCount(table)):
        try:
            ret = collection.insert_one(dict(zip(fields, entry)))
            if ret.acknowledged != True:
                errors.append((table, i))
        except KeyboardInterrupt:
            broken = True
            break
    if broken:
        break

if len(errors):
    print('\n\nErrors:')
    print(errors)
else:
    print('\n\nNo errors')
db_sql.close()
db_mongo.close()

