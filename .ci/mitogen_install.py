#!/usr/bin/env python

import ci_lib

batches = [
]

if ci_lib.have_docker():
    batches.append([
        'aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws',
    ])


ci_lib.run_batches(batches)
