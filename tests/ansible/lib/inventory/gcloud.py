#!/usr/bin/env python

import json
import os
import sys

if not os.environ.get('MITOGEN_GCLOUD_GROUP'):
    sys.stdout.write('{}')
    sys.exit(0)

import googleapiclient.discovery


def main():
    project = 'mitogen-load-testing'
    zone = 'europe-west1-d'
    group_name = 'micro-debian9'

    client = googleapiclient.discovery.build('compute', 'v1')
    resp = client.instances().list(project=project, zone=zone).execute()

    ips = []
    for inst in resp['items']:
        if inst['status'] == 'RUNNING' and inst['name'].startswith(group_name):
            ips.extend(
                #bytes(config['natIP'])
                bytes(interface['networkIP'])
                for interface in inst['networkInterfaces']
                #for config in interface['accessConfigs']
            )

    sys.stderr.write('Addresses: %s\n' % (ips,))
    sys.stdout.write(json.dumps({
        os.environ['MITOGEN_GCLOUD_GROUP']: {
            'hosts': ips
        }
    }, indent=4))


if __name__ == '__main__':
    main()
