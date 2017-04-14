import unittest
import pytest
from haas.test_common import \
    config_testsuite, config_merge, fail_on_log_warnings, \
    initial_db, newDB, releaseDB
from haas import api, config, deferred, model
from haas.flaskapp import app


class Test_port_revert(unittest.TestCase):

    def setUp(self):
        from haas.ext.switches.mock import LOCAL_STATE
        self.LOCAL_STATE = LOCAL_STATE
        fail_on_log_warnings()

        # Configure HaaS:
        config_testsuite()
        config_merge({
            'extensions': {
                'haas.ext.switches.mock': '',
                'haas.ext.obm.ipmi': '',
                'haas.ext.obm.mock': '',
                'haas.ext.network_allocators.null': None,
                'haas.ext.network_allocators.vlan_pool': '',
            },
            'haas.ext.network_allocators.vlan_pool': {
                'vlans': '100-200',
            },
        })
        config.load_extensions()

        newDB()  # Initialize the db schema
        initial_db()  # Populate the db with objects

        # Sanity check the start state:
        assert self.LOCAL_STATE['stock_switch_0']['free_port_0'] == {}

        self.request_context = app.test_request_context()
        self.request_context.push()

    def tearDown(self):
        self.request_context.pop()
        releaseDB()

    def test_no_nic(self):
        with pytest.raises(api.NotFoundError):
            # free_port_0 is not attached to a nic.
            api.port_revert('stock_switch_0', 'free_port_0')
        deferred.apply_networking()
        assert self.LOCAL_STATE['stock_switch_0']['free_port_0'] == {}

    def test_one_network(self):
        api.node_connect_network('runway_node_0',
                                 'nic-with-port',
                                 'runway_pxe',
                                 'vlan/native')
        deferred.apply_networking()

        net_id = model.Network.query.filter_by(label='runway_pxe')\
            .one().network_id
        assert self.LOCAL_STATE['stock_switch_0']['runway_node_0_port'] == {
            'vlan/native': net_id,
        }

        api.port_revert('stock_switch_0', 'runway_node_0_port')
        deferred.apply_networking()

        assert self.LOCAL_STATE['stock_switch_0']['runway_node_0_port'] == {},\
            "port_revert did not detach the port from the networks!"

        network = model.Network.query.filter_by(label='runway_pxe').one()
        assert model.NetworkAttachment.query.filter_by(
            network_id=network.id,
        ).first() is None, (
            "port_revert did not remove the network attachment object in "
            "the database!"
        )

    def test_two_networks(self):
        pxe_net_id = model.Network.query.filter_by(label='runway_pxe')\
            .one().network_id
        pub_net_id = model.Network.query.filter_by(label='stock_int_pub')\
            .one().network_id
        api.node_connect_network('runway_node_0',
                                 'nic-with-port',
                                 'runway_pxe',
                                 'vlan/native')
        deferred.apply_networking()
        assert self.LOCAL_STATE['stock_switch_0']['runway_node_0_port'] == {
            'vlan/native': pxe_net_id,
        }
        api.node_connect_network('runway_node_0',
                                 'nic-with-port',
                                 'stock_int_pub',
                                 'vlan/' + pub_net_id)
        deferred.apply_networking()
        assert self.LOCAL_STATE['stock_switch_0']['runway_node_0_port'] == {
            'vlan/native': pxe_net_id,
            'vlan/' + pub_net_id: pub_net_id,
        }
        api.port_revert('stock_switch_0', 'runway_node_0_port')
        deferred.apply_networking()
        assert self.LOCAL_STATE['stock_switch_0']['runway_node_0_port'] == {}
