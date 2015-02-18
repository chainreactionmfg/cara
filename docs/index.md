# cara: Capnproto Alternative RPC API

[![Build Status](https://img.shields.io/travis/chainreactionmfg/cara/master.svg)](https://travis-ci.org/chainreactionmfg/cara)
[![Coverage Status](https://img.shields.io/coveralls/chainreactionmfg/cara/master.svg)](https://coveralls.io/r/chainreactionmfg/cara)
[![Codacy Badge](https://img.shields.io/codacy/3cc5a370c923435e92b9ce1a7dbbbafe.svg)](https://www.codacy.com/public/fahhem/cara)
[![Documentation Status](https://readthedocs.org/projects/cara/badge/?version=latest&style=flat)](https://readthedocs.org/projects/cara/?badge=latest)
[![PyPI Version](https://img.shields.io/pypi/v/cara.svg)](https://pypi.python.org/pypi/cara)
[![PyPI License](https://img.shields.io/pypi/l/cara.svg)](https://pypi.python.org/pypi/cara)

## What is this?

This is a Python library that provides Cap'n proto as the schema layer on top
of an RPC layer.

Currently, cara works with pseud, but it has been designed to work with any RPC
library. If you use another one, feel free contact us to help integrate it.

## Getting Started

Once you've installed capnproto and cara, you should be ready to go.

This script installs capnp to /usr/local/, but feel free to put it anywhere, as
long as 'capnp' is on the PATH later on.

```bash
./install_capnp051.sh
```

From here, we're going to assume you want to use this with pseud as the RPC
layer. If you don't, then refer to your RPC layer's installation instructions.

### Installing pseud

pseud requires zeromq 4.1 or later, so install that first.

```bash
./install_zeromq41.sh
export CARA_EXTRA="[pseud]"
```

### Installing cara

Now you can install cara and this will build everything you need. If you're
using an extra, such as pseud, set `CARA_EXTRA` to that.

```bash
pip install .$CARA_EXTRA
```

### Using schemas with cara

Then you can define a schema in a `.capnp` file:

```bash
capnp compile -ocara filename.capnp
# Outputs filename_capnp.py
```

### Using structs, interfaces, etc.

Refer to [Structs](structs.md) and [Interfaces](interfaces.md), and
[Advanced Usage](advanced_usage.md) if you're interested.
