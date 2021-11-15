#!/usr/bin/env python3
import psutil
import Doberman
import time

period = 2
# specify disks etc like this: device:name,device:name
# eg en0ps1:network or md0:raid,md1:home
nics = dict(map(lambda s: s.split(':'), os.environ.get('NICS', '').split(',')))
disks = dict(map(lambda s: s.split(':'), os.environ.get('DISKS', '').split(',')))
net_io = psutil.net_io_counters(True)
last_recv = {n:net_io[n].bytes_recv for n in nics}
last_sent = {n:net_io[n].bytes_sent for n in nics}
disk_io = psutil.disk_io_counters(True)
last_read = {d:disk_io[d].read_bytes for d in disks}
last_write = {d:disk_io[d].write_bytes for d in disks}

def monitor():
    n_cpus = psutil.cpu_count()
    load_1, load_5, load_15 = psutil.getloadavg()
    fields = {'load1': load1 / n_cpus, 'load5': load_5 / n_cpus, 'load15', load_15 / n_cpus}
    mem = psutil.virtual_memory()
    fields['mem_avail'] = mem.available / mem.total
    swap = psutil.swap_memory()
    if swap.total > 0:
        fields['swap_used'] = swap.used / swap.total
    else:
        fields['swap_used'] = 0
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
        fields['cpu_0_temp'] = None
    net_io = psutil.net_io_counters(True)
    for nic, name in nics.items():
        recv_kbytes = (net_io[nic].bytes_recv - last_recv[nic]) >> 10
        last_recv[nic] = net_io[nic].bytes_recv
        fields[f'{name}_recv'] = recv_kbytes / period

        sent_kbytes = (net_io[nic].bytes_sent - last_sent[nic]) >> 10
        last_sent[nic] = net_io[nic].bytes_sent
        fields[f'{name}_sent'] = sent_kbytes / period
    disk_io = psutil.disk_io_counters(True)
    for disk, name in disks.items():
        read_kbytes = (disk_io[disk].read_bytes - last_read[disk]) >> 10
        last_read[disk] = disk_io[disk].read_bytes
        fields[f'{name}_read'] = read_kbytes / period

        write_kbytes = (disk_io[disk].write_bytes - last_write[disk]) >> 10
        last_write[disk] = disk_io[disk].write_bytes
        fields[f'{name}_write'] = write_kbytes / period
    return fields

def main(client):
    sh = Doberman.utils.SignalHandler()
    db = Doberman.Database(client = MongoClient, experiment_name = os.environ['DOBERMAN_EXPERIMENT_NAME'])
    while sh.run():
        try:
            fields = monitor()
            db.write_to_influx(topic = 'sysmon', tags = {'hostname': hostname}, fields = fields)
        except Exception as e:
            print(f'Caught a {type(e)}: {e}')
        time.sleep(period)

if __name__ == '__main__':
    with MongoClient(os.environ['DOBERMAN_MONGO_URI']) as client:
        main(client)
