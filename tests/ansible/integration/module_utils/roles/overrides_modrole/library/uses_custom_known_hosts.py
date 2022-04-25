#!/usr/bin/python

import json
import ansible.module_utils.basic

def main():
    print(json.dumps({
        'path': ansible.module_utils.basic.path()
    }))

if __name__ == '__main__':
    main()
