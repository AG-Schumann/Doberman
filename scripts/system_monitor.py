#!/usr/bin/env python3
import psutil
import requests
import Doberman
import time

period = 1
# specify disks etc like this: device:name,device:name
# eg en0ps1:network or md0:raid,md1:home
nics = dict(map(lambda s: s.split(':'), os.environ['NICS'].split(',')))
disks = dict(map(lambda s: s.split(':'), os.environ['DISKS'].split(',')))
net_io = psutil.net_io_counters(True)
last_recv = {n:net_io[n].bytes_recv for n in nics}
last_sent = {n:net_io[n].bytes_sent for n in nics}
disk_io = psutil.disk_io_counters(True)
last_read = {d:disk_io[d].read_bytes for d in disks}
last_write = {d:disk_io[d].write_bytes for d in disks}

def monitor():
    n_cpus = psutil.cpu_count()
    load_1, load_5, load_15 = psutil.getloadavg()
    ret = f'load1={load1/n_cpus:.2f},load5={load_5/n_cpus:.2f},load15={load_15/n_cpus:.2f}'
    mem = psutil.virtual_memory()
    ret += f',mem_avail={mem.available/mem.total:.2f}'
    swap = psutil.swap_memory()
    if swap.total > 0:
        ret += f',swap_used={swap.used/swap.total:.2f}'
    else:
        ret += f',swap_used=0'
    temp_dict = psutil.sensors_temperatures()
    if 'coretemp' in temp_dict.keys():
        for row in temp_dict['coretemp']:
            if 'Package' in row.label:  # Fujitsu Intel core servers
                socket = row.label[-1]  # max 10 sockets per machine
               ret += f',cpu_{socket}_temp={row.current}'
    elif len(temp_dict) == 1:
        key = list(temp_dict.keys())[0]
        fields['cpu_0_temp'] = temp_dict[key][0].current
        ret += f',cpu_0_temp={temp_dict[key][0].current}'
    else:
        print(f'Couldn\'t read out CPU temperatures')
    net_io = psutil.net_io_counters(True)
    for nic, name in nics.items():
        recv_kbytes = (net_io[nic].bytes_recv - last_recv[nic]) >> 10
        last_recv[nic] = net_io[nic].bytes_recv
        ret += f',{name}_recv={recv_kbytes/period:.3f}'
        sent_kbytes = (net_io[nic].bytes_sent - last_sent[nic]) >> 10
        last_sent[nic] = net_io[nic].bytes_sent
        ret += f',{name}_sent={sent_kbytes/period:.3f}'
    disk_io = psutil.disk_io_counters(True)
    for disk, name in disks.items():
        read_kbytes = (disk_io[disk].read_bytes - last_read[disk]) >> 10
        last_read[disk] = disk_io[disk].read_bytes
        ret += f',{name}_read={read_kbytes/period:.3f}'
        write_kbytes = (disk_io[disk].write_bytes - last_write[disk]) >> 10
        last_write[disk] = disk_io[disk].write_bytes
        ret += f',{name}_write={write_kbytes/period:.3f}'
    return ret

def main(client):
    sh = Doberman.utils.SignalHandler()
    url = f'http://192.168.131.2:8096/api/v2/query?org={os.environ["DOBERMAN_EXPERIMENT_NAME"]}&precision=ms&bucket=sysmon'
    headers = {'Authorization': f'Token {os.environ["INFLUX_TOKEN"]}'}
    while sh.run():
        try:
            fields=monitor()
            now = int(time.time()*1000)
            data = f'sysmon,host={hostname} {fields} {now}'
            requests.post(url, headers=headers, data=data)
        except Exception as e:
            print(f'Caught a {type(e)}: {e}')
        time.sleep(period)

if __name__ == '__main__':
    with MongoClient(os.environ['DOBERMAN_MONGO_URI']) as client:
        main(client)
