# -*- coding: utf-8 -*-

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>
Licensed under LGPLv3, see LICENSE.txt for terms and conditions.

Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
https://zato.io
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import logging
import os

# Click
import click

# Distribute
import pkg_resources

# Zato
from zato.discourse_importer import run as _run

# ################################################################################################################################

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ################################################################################################################################

curdir = os.path.dirname(os.path.abspath(__file__))
default_config = os.path.normpath(os.path.join(curdir, '..', '..', '..', 'config.ini'))

# ################################################################################################################################

def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    click.echo(pkg_resources.get_distribution('zato-discourse-importer').version)
    ctx.exit()

@click.group()
@click.option('-v', '--version', is_flag=True, is_eager=True, expose_value=False, callback=print_version)
def main():
    pass

@click.command(context_settings=dict(allow_extra_args=True, ignore_unknown_options=True))
@click.argument('path', type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True), default=default_config)
@click.pass_context
def run(ctx, path, *args, **kwargs):
    _run.handle(path)

main.add_command(run)

if __name__ == '__main__':
    main()
