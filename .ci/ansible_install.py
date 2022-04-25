#!/usr/bin/env python

import ci_lib

batches = [
    [
        'aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws',
    ]
]

ci_lib.run_batches(batches)
