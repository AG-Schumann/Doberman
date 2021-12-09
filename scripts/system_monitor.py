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
last_recv = 0
last_sent = 0
for nic in net_io:
    if any([n in nic for n in ignore_nics]):
        continue
    last_recv += net_io[nic].bytes_recv
    last_sent += net_io[nic].bytes_sent
disk_io = psutil.disk_io_counters(True)
last_read = 0
last_write = 0
for disk in disk_io:
    if any([d in disk for d in ignore_disks]):
        continue
    last_read += disk_io[disk].read_bytes
    last_write += disk_io[disk].write_bytes

def monitor():
    load1, load5, load15 = psutil.getloadavg()
    fields = {'load1': load1 / n_cpus, 'load5': load5 / n_cpus, 'load15': load15 / n_cpus}
    cpu_percent = sorted(psutil.cpu_percent(percpu=True))
    fields['cpu0'] = cpu_percent[-1]
    fields['cpu1'] = cpu_percent[-2] if n_cpus > 1 else 0.

    mem = psutil.virtual_memory()
    fields['mem_pct'] = mem.percent
    swap = psutil.swap_memory()
    fields['swap_pct'] = swap.percent

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
    this_recv = 0
    this_sent = 0
    for nic in net_io:
        if any([n in nic for n in ignore_nics]):
            continue
        this_recv += net_io[nic].bytes_recv
        this_sent += net_io[nic].bytes_sent
    fields['network_recv'] = ((this_recv - last_recv)>>10)/period
    fields['network_sent'] = ((this_sent - last_sent)>>10)/period
    last_recv = this_recv
    last_sent = this_sent
    disk_io = psutil.disk_io_counters(True)
    this_read = 0
    this_write = 0
    for disk in disk_io:
        if any([d in disk for d in ignore_disks]):
            continue
        this_read += disk_io[disk].read_bytes
        this_write += disk_io[disk].write_bytes
    fields['disk_read'] = ((this_read - last_read)>>10) /period
    fields['disk_write'] = ((this_write - last_write)>>10) /period
    last_read = this_read
    last_write = this_write
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
