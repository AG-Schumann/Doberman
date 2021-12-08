#!/usr/bin/env python3
import psutil
import Doberman
import time
from pymongo import MongoClient
import os

period = 2
n_cpus = psutil.cpu_count()
# ignore nics and disks that look like these:
ignore_nics = ['lo']
ignore_disks = ['loop', 'ram', 'boot']

# setup disk and network rate caching
net_io = psutil.net_io_counters(True)
last_recv = {}
last_sent = {}
for nic in net_io:
    if any([n in nic for n in ignore_nics]):
        continue
    last_recv[nic] = net_io[nic].bytes_recv
    last_sent[nic] = net_io[nic].bytes_sent
disk_io = psutil.disk_io_counters(True)
last_read = {}
last_write = {}
for disk in disk_io:
    if any([d in disk for d in ignore_disks]):
        continue
    last_read[disk] = disk_io[disk].read_bytes
    last_write[disk] = disk_io[disk].write_bytes

def monitor():
    load_1, load_5, load_15 = psutil.getloadavg()
    fields = {'load1': load_1 / n_cpus, 'load5': load_5 / n_cpus, 'load15': load_15 / n_cpus}
    mem = psutil.virtual_memory()
    fields['mem_avail'] = mem.available / mem.total
    swap = psutil.swap_memory()
    if swap.total > 0:
        fields['swap_used'] = swap.used / swap.total
    else:
        fields['swap_used'] = 0.
    temp_dict = psutil.sensors_temperatures()
    if 'coretemp' in temp_dict.keys():
        for row in temp_dict['coretemp']:
            if 'Package' in row.label:  # Fujitsu Intel core servers
                socket = row.label[-1]  # max 10 sockets per machine
                fields[f'cpu_{socket}_temp'] = row.current
    elif len(temp_dict) == 1:
        key = list(temp_dict.keys())[0]
        fields['cpu_0_temp'] = temp_dict[key][0].current
    else:
        print(f'Couldn\'t read out CPU temperatures')
        fields['cpu_0_temp'] = -1.
    net_io = psutil.net_io_counters(True)
    for nic in last_recv:
        recv_kbytes = (net_io[nic].bytes_recv - last_recv[nic]) >> 10
        last_recv[nic] = net_io[nic].bytes_recv
        fields[f'{nic}_recv'] = recv_kbytes / period

        sent_kbytes = (net_io[nic].bytes_sent - last_sent[nic]) >> 10
        last_sent[nic] = net_io[nic].bytes_sent
        fields[f'{nic}_sent'] = sent_kbytes / period
    disk_io = psutil.disk_io_counters(True)
    for disk in last_read:
        read_kbytes = (disk_io[disk].read_bytes - last_read[disk]) >> 10
        last_read[disk] = disk_io[disk].read_bytes
        fields[f'{disk}_read'] = read_kbytes / period

        write_kbytes = (disk_io[disk].write_bytes - last_write[disk]) >> 10
        last_write[disk] = disk_io[disk].write_bytes
        fields[f'{disk}_write'] = write_kbytes / period
    return fields

class DumbLogger(object):
    def __init__(self):
        pass

    def error(self, message):
        print(message)

def main(client):
    sh = Doberman.utils.SignalHandler()
    db = Doberman.Database(client, experiment_name=os.environ['DOBERMAN_EXPERIMENT_NAME'],
            bucket_override='sysmon')
    db.logger = DumbLogger() # in case we need to print a message
    tags = {'host': db.hostname}
    while sh.run:
        try:
            fields = monitor()
            db.write_to_influx(topic='sysmon', tags=tags, fields=fields)
        except Exception as e:
            print(f'Caught a {type(e)}: {e}')
        time.sleep(period)

if __name__ == '__main__':
    with MongoClient(os.environ['DOBERMAN_MONGO_URI']) as client:
        main(client)