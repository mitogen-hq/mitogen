#!/usr/bin/env python
import ci_lib

containers = ci_lib.container_specs(ci_lib.DISTRO_SPECS.split())
ci_lib.pull_container_images(containers)
