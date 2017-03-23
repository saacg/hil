# Copyright 2013-2014 Massachusetts Open Cloud Contributors
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

"""Unit tests for client library"""
import haas
from haas import model, api, deferred, server, config
from haas.model import db
from haas.network_allocator import get_network_allocator
import pytest
import json
import requests
import os
import tempfile
import subprocess
import time
from subprocess import check_call, Popen
from urlparse import urljoin
import requests
from requests.exceptions import ConnectionError
#from haas.client.base import ClientBase
#from haas.client.auth import db_auth
#from haas.client.client import Client
#from haas.client import errors


ep = "http://127.0.0.1:5000" or os.environ.get('HAAS_ENDPOINT')
username = "hil_user" or os.environ.get('HAAS_USERNAME')
password = "hil_pass1234" or os.environ.get('HAAS_PASSWORD')

#sess = db_auth(username, password)
#C = Client(ep, sess)  # Initializing client library
MOCK_SWITCH_TYPE = 'http://schema.massopencloud.org/haas/v0/switches/mock'
OBM_TYPE_MOCK = 'http://schema.massopencloud.org/haas/v0/obm/mock'
OBM_TYPE_IPMI = 'http://schema.massopencloud.org/haas/v0/obm/ipmi'


def make_config():
    """ This function creates haas.cfg with desired options
    and writes to a temporary directory.
    It returns a tuple where (tmpdir, cwd) = ('location of haas.cfg', 'pwdd')
    """
    tmpdir = tempfile.mkdtemp()
    cwd = os.getcwd()
    os.chdir(tmpdir)
    with open('haas.cfg', 'w') as f:
        config = '\n'.join([
            '[general]',
            '[devel]',
            'dry_run=True',
            '[auth]',
            'require_authentication = True',

            '[headnode]',
            'base_imgs = base-headnode, img1, img2, img3, img4',
            '[database]',
            'uri = sqlite:///%s/haas.db' % tmpdir,
            '[extensions]',
            'haas.ext.auth.database =',
            'haas.ext.switches.mock =',
            'haas.ext.switches.nexus =',
            'haas.ext.switches.dell =',
            'haas.ext.switches.brocade =',
            'haas.ext.obm.mock =',
            'haas.ext.obm.ipmi =',
            'haas.ext.network_allocators.vlan_pool =',
            '[haas.ext.network_allocators.vlan_pool]',
            'vlans = 1001-1040',

        ])
        f.write(config)
        return (tmpdir, cwd)


def cleanup((tmpdir, cwd)):
    """ Cleanup crew, when all tests are done.
    It will shutdown the haas server,
    delete any files and folders created for the tests.
    """

    os.remove('haas.cfg')
    os.remove('haas.db')
    os.chdir(cwd)
    os.rmdir(tmpdir)


def initialize_db():
    """ Creates an  database as defined in haas.cfg."""
    check_call(['haas-admin', 'db', 'create'])
    check_call(['haas', 'create_admin_user', username, password])


def run_server(cmd):
    """This function starts a haas server.
    The arguments in 'cmd' will be a list of arguments like required to start a
    haas server like ['haas', 'serve', '5000']
    It will return a handle which can be used to terminate the server when
    tests finish.
    """
    proc = Popen(cmd)
    return proc


def populate_server():
    """
    Once the server is started, this function will populate some mock objects
    to faciliate testing of the client library
    """
    sess = requests.Session()
    sess.auth = (username, password)

    # Adding nodes, node-01 - node-06
    url_node = 'http://127.0.0.1:5000/node/'
    api_nodename = 'http://schema.massopencloud.org/haas/v0/obm/'

    for i in range(1, 10):
        obminfo = {
                "type": api_nodename + 'ipmi', "host": "10.10.0.0"+repr(i),
                "user": "ipmi_u", "password": "pass1234"
                }
        sess.put(
                url_node + 'node-0'+repr(i), data=json.dumps({"obm": obminfo})
                )
        sess.put(
                url_node + 'node-0' + repr(i) + '/nic/eth0', data=json.dumps(
                            {"macaddr": "aa:bb:cc:dd:ee:0" + repr(i)}
                            )
                     )

    # Adding Projects proj-01 - proj-03
    for i in ["proj-01", "proj-02", "proj-03"]:
        sess.put('http://127.0.0.1:5000/project/' + i)

    # Adding switches one for each driver
    url_switch = 'http://127.0.0.1:5000/switch/'
    api_name = 'http://schema.massopencloud.org/haas/v0/switches/'

    dell_param = {
            'type': api_name + 'powerconnect55xx', 'hostname': 'dell-01',
            'username': 'root', 'password': 'root1234'
            }
    nexus_param = {
            'type': api_name + 'nexus', 'hostname': 'nexus-01',
            'username': 'root', 'password': 'root1234', 'dummy_vlan': '333'
            }
    mock_param = {
            'type': api_name + 'mock', 'hostname': 'mockSwitch-01',
            'username': 'root', 'password': 'root1234'
            }
    brocade_param = {
            'type': api_name + 'brocade', 'hostname': 'brocade-01',
            'username': 'root', 'password': 'root1234',
            'interface_type': 'TenGigabitEthernet'
            }

    sess.put(url_switch + 'dell-01', data=json.dumps(dell_param))
    sess.put(url_switch + 'nexus-01', data=json.dumps(nexus_param))
    sess.put(url_switch + 'mock-01', data=json.dumps(mock_param))
    sess.put(url_switch + 'brocade-01', data=json.dumps(brocade_param))

    # Adding ports to the mock switch, Connect nics to ports:
    for i in range(1, 8):
        sess.put(url_switch + 'mock-01/port/gi1/0/' + repr(i))
        sess.post(
                url_switch + 'mock-01/port/gi1/0/' + repr(i) + '/connect_nic',
                data=json.dumps(
                    {'node': 'node-0' + repr(i), 'nic': 'eth0'}
                    )
                )

# Adding port gi1/0/8 to switch mock-01 without connecting it to any node.
    sess.put(url_switch + 'mock-01/port/gi1/0/8')

    # Adding Projects proj-01 - proj-03
    for i in ["proj-01", "proj-02", "proj-03"]:
        sess.put('http://127.0.0.1:5000/project/' + i)

    # Allocating nodes to projects
    url_project = 'http://127.0.0.1:5000/project/'
    # Adding nodes 1 to proj-01
    sess.post(
            url_project + 'proj-01' + '/connect_node',
            data=json.dumps({'node': 'node-01'})
            )
    # Adding nodes 2, 4 to proj-02
    sess.post(
            url_project + 'proj-02' + '/connect_node',
            data=json.dumps({'node': 'node-02'})
            )
    sess.post(
            url_project + 'proj-02' + '/connect_node',
            data=json.dumps({'node': 'node-04'})
            )
    # Adding node  3, 5 to proj-03
    sess.post(
            url_project + 'proj-03' + '/connect_node',
            data=json.dumps({'node': 'node-03'})
            )
    sess.post(
            url_project + 'proj-03' + '/connect_node',
            data=json.dumps({'node': 'node-05'})
            )

    # Assigning networks to projects
    url_network = 'http://127.0.0.1:5000/network/'
    for i in ['net-01', 'net-02', 'net-03']:
        sess.put(
                url_network + i,
                data=json.dumps(
                    {"owner": "proj-01", "access": "proj-01", "net_id": ""}
                    )
                )

    for i in ['net-04', 'net-05']:
        sess.put(
                url_network + i,
                data=json.dumps(
                    {"owner": "proj-02", "access": "proj-02", "net_id": ""}
                    )
                )


# -- SETUP --
def create_setup(request):
    dir_names = make_config()
    initialize_db()
    proc1 = run_server(['haas', 'serve', '5000'])
    proc2 = run_server(['haas', 'serve_networks'])
    time.sleep(1)
    populate_server()
    print("coming from create_setup")

    def fin():
        proc1.terminate()
        proc2.terminate()
        cleanup(dir_names)
        print("tearing down HIL setup")
#    request.addfinalizer(fin)


