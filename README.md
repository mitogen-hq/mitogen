
# Mitogen

<!-- [![Build Status](https://travis-ci.org/dw/mitogen.png?branch=master)](https://travis-ci.org/dw/mitogen}) -->
<a href="https://mitogen.networkgenomics.com/">Please see the documentation</a>.

![screencast](https://i.imgur.com/eBM6LhJ.gif)

[![Total alerts](https://img.shields.io/lgtm/alerts/g/dw/mitogen.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/dw/mitogen/alerts/)

[![Build Status](https://travis-ci.org/dw/mitogen.svg?branch=master)](https://travis-ci.org/dw/mitogen)

[![Pipelines Status](https://dev.azure.com/dw-mitogen/Mitogen/_apis/build/status/dw.mitogen?branchName=master)](https://dev.azure.com/dw-mitogen/Mitogen/_build/latest?definitionId=1?branchName=master)

## Installing mitogen

This can be used to install or upgrade mitogen.  You can add the next two
lines to your shell profile to make it more permanent. If you want to enable
it only for a specific directory, you may want to check
[direnv](https://direnv.net/).

```bash
pip install -U mitogen
export ANSIBLE_STRATEGY_PLUGINS=$(mitogen -p)
export ANSIBLE_STRATEGY=mitogen_linear
```
