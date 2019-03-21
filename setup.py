#!/usr/bin/env python

#
# netmetr-client
# Copyright (C) 2018 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#

from setuptools import setup

DESCRIPTION = "Netmetr client (basically a wrapper around RMBT binary)"

setup(
    name='netmetr',
    version="1.4.2",
    author='CZ.NIC, z.s.p.o. (http://www.nic.cz/)',
    author_email='martin.prudek@nic.cz',
    packages=[
        'netmetr',
    ],
    url='https://gitlab.labs.nic.cz/turris/netmetr-client',
    license='GPLv3+',
    description=DESCRIPTION,
    long_description=open('README.rst').read(),
    install_requires=[
        'pyserial',
    ],
    entry_points={
        "console_scripts": [
            "netmetr = netmetr.__main__:main",
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)'
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
