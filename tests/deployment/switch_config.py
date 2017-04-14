# Copyright 2013-2017 Massachusetts Open Cloud Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the
# License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS
# IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied.  See the License for the specific language
# governing permissions and limitations under the License.

"""Deployment Tests - These tests are intended for our
internal setup only and will most likely not work on
other HaaS configurations. This test is for the dell switch only"""


from haas import api, model, deferred, server
from haas.model import db
from haas.test_common import config, config_testsuite, fresh_database, \
    fail_on_log_warnings, with_request_context, site_layout, config_merge, \
    NetworkTest, network_create_simple

import pytest
import json

DELL = 'http://schema.massopencloud.org/haas/v0/switches/powerconnect55xx'


@pytest.fixture
def configure():
    config_testsuite()
    config_merge({
        'haas.ext.switches.dell': {
            'save': 'True'
         }
    })
    config.load_extensions()


fail_on_log_warnings = pytest.fixture(autouse=True)(fail_on_log_warnings)
fresh_database = pytest.fixture(fresh_database)


@pytest.fixture
def server_init():
    server.register_drivers()
    server.validate_state()


with_request_context = pytest.yield_fixture(with_request_context)

site_layout = pytest.fixture(site_layout)

pytestmark = pytest.mark.usefixtures('configure',
                                     'server_init',
                                     'fresh_database',
                                     'with_request_context',
                                     'site_layout')


@pytest.fixture
def not_dell():
    """open the site-layout file to see if we don't have a dell switch"""

    with open('site-layout.json') as layout_data:
        layout = json.load(layout_data)
    return layout['switches'][0]['type'] != DELL


@pytest.mark.skipif(not_dell(), reason="Skipping because not a dell switch")
class TestSwitchSavingToFlash(NetworkTest):
    """ saves the running config to the flash memory. Test is only for the dell
        switch"""

    def get_config(self, config_type):
        """returns the switch configuration file"""

        switch = model.Switch.query.one()
        session = switch.session()
        config = session._get_config(config_type)
        session.disconnect()
        return config

    def test_saving_config_file(self):

        api.project_create('anvil-nextgen')
        nodes = self.collect_nodes()

        # Create two networks
        network_create_simple('net-0', 'anvil-nextgen')
        network_create_simple('net-1', 'anvil-nextgen')

        # save the old startup config before performing a networking action
        old_startup_config = self.get_config('startup')
        # Connect n0 and n1 to net-0 and net-1 respectively
        api.node_connect_network(nodes[0].label,
                                 nodes[0].nics[0].label,
                                 'net-0')

        api.node_connect_network(nodes[1].label,
                                 nodes[1].nics[0].label,
                                 'net-1')

        deferred.apply_networking()

        # get the running config, and the new startup config
        running_config = self.get_config('running')
        new_startup_config = self.get_config('startup')

        assert new_startup_config == running_config
        assert new_startup_config != old_startup_config

        # cleanup
        api.node_detach_network(nodes[0].label,
                                nodes[0].nics[0].label,
                                'net-0')

        api.node_detach_network(nodes[1].label,
                                nodes[1].nics[0].label,
                                'net-1')

        deferred.apply_networking()
