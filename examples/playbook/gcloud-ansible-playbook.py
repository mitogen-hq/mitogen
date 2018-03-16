#!/usr/bin/env python

import os
import sys

import googleapiclient.discovery


def main():
    project = 'mitogen-load-testing'
    zone = 'asia-south1-c'
    group_name = 'micro-debian9'

    client = googleapiclient.discovery.build('compute', 'v1')
    resp = client.instances().list(project=project, zone=zone).execute()

    ips = []
    for inst in resp['items']:
        if inst['status'] == 'RUNNING' and inst['name'].startswith(group_name):
            ips.extend(
                bytes(config['natIP'])
                for interface in inst['networkInterfaces']
                for config in interface['accessConfigs']
            )

    print 'Addresses:', ips
    os.execvp('ansible-playbook', [
        'anisble-playbook',
        '--user=dw',
        '--inventory-file=' + ','.join(ips) + ','
    ] + sys.argv[1:])


if __name__ == '__main__':
    main()
