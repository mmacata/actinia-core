# -*- coding: utf-8 -*-
#######
# actinia-core - an open source REST API for scalable, distributed, high
# performance processing of geographical data that uses GRASS GIS for
# computational tasks. For details, see https://actinia.mundialis.de/
#
# Copyright (c) 2016-2018 Sören Gebbert and mundialis GmbH & Co. KG
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#######

"""
Tests: Common test case base
"""
import atexit
import unittest
import signal
import time
import os
from actinia_core.resources.common.config import global_config
import actinia_core.resources.common.redis_interface as redis_interface
from actinia_core.resources.common.app import flask_app

__license__ = "GPLv3"
__author__ = "Sören Gebbert"
__copyright__ = "Copyright 2016-2018, Sören Gebbert and mundialis GmbH & Co. KG"
__maintainer__ = "Sören Gebbert"
__email__ = "soerengebbert@googlemail.com"

redis_pid = None
custom_graas_cfg = False

# Set this variable to use a graas config file in a docker container
if "GRAAS_CUSTOM_TEST_CFG" in os.environ:
    custom_graas_cfg = str(os.environ["GRAAS_CUSTOM_TEST_CFG"])


def setup_environment():

    # If docker config
    if custom_graas_cfg is not False:
        global_config.read(custom_graas_cfg)
        return

    global redis_pid
    # Set the port to the test redis server
    global_config.REDIS_SERVER_SERVER = "localhost"
    global_config.REDIS_SERVER_PORT = 7000

    # home = os.getenv("HOME")

    # GRASS

    # Setup the test environment
    global_config.GRASS_GIS_BASE="/usr/local/grass-7.5.svn"
    global_config.GRASS_GIS_START_SCRIPT="/usr/local/bin/grass75"
    # global_config.GRASS_DATABASE= "/usr/local/grass_test_db"
    # global_config.GRASS_DATABASE = "%s/graas/grass_test_db" % home

    # Start the redis server for user and logging management
    redis_pid = os.spawnl(os.P_NOWAIT, "/usr/bin/redis-server",
                          "common/redis.conf",
                          "--port %i" % global_config.REDIS_SERVER_PORT)
    time.sleep(1)


def stop_redis():
    global redis_pid
    # Kill th redis server
    if custom_graas_cfg is not False:
        return
    os.kill(redis_pid, signal.SIGTERM)

# Register the redis stop function
atexit.register(stop_redis)
# Setup the environment
setup_environment()


class CommonTestCaseBase(unittest.TestCase):
    """
    This is the base class for the common testing
    """
    @classmethod
    def setUpClass(cls):

        if custom_graas_cfg is not False:
            global_config.read(custom_graas_cfg)
            print(global_config)
        else:
            global_config.REDIS_SERVER_URL = "localhost"
            global_config.REDIS_SERVER_PORT = 7000

        redis_interface.connect(global_config.REDIS_SERVER_URL,
                                global_config.REDIS_SERVER_PORT)

    @classmethod
    def tearDownClass(cls):
        redis_interface.disconnect()

    def setUp(self):
        # We need to set the application context
        self.app_context = flask_app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

