"""VLAN based ``network_allocator`` implementation."""

import logging

from haas.network_allocator import NetworkAllocator, set_network_allocator
from haas.model import db
from haas.config import cfg


def get_vlan_list():
    """Return a list of vlans in the module's config section.

    This is for use by the ``create_bridges`` script.
    """
    vlan_str = cfg.get(__name__, 'vlans')
    returnee = []
    for r in vlan_str.split(","):
        r = r.strip().split("-")
        if len(r) == 1:
            returnee.append(int(r[0]))
        else:
            returnee += range(int(r[0]), int(r[1])+1)
    return returnee


class VlanAllocator(NetworkAllocator):
    """A allocator of VLANs. The interface is as specified in
    ``NetworkAllocator``.
    """

    def get_new_network_id(self):
        vlan = Vlan.query.filter_by(available=True).first()
        if not vlan:
            return None
        vlan.available = False
        returnee = str(vlan.vlan_no)
        return returnee

    def free_network_id(self, net_id):
        vlan = Vlan.query.filter_by(vlan_no=net_id).first()
        if not vlan:
            logger = logging.getLogger(__name__)
            logger.error('vlan %s does not exist in database', net_id)
            return
        vlan.available = True

    def populate(self):
        vlan_list = get_vlan_list()
        for vlan in vlan_list:
            if Vlan.query.filter_by(vlan_no=vlan).count() == 1:
                # Already created by a previous call; leave it alone.
                continue
            db.session.add(Vlan(vlan))
        db.session.commit()

    def legal_channels_for(self, net_id):
        return ["vlan/native",
                "vlan/" + net_id]

    def is_legal_channel_for(self, channel_id, net_id):
        return channel_id in self.legal_channels_for(net_id)

    def get_default_channel(self):
        return "vlan/native"

    def validate_network_id(self, net_id):
        try:
            return 1 <= int(net_id) <= 4096
        except ValueError:
            return False


class Vlan(db.Model):
    """A VLAN for the Dell switch

    This is used to track which vlan numbers are available; when a Network is
    created, it must allocate a Vlan, to ensure that:

    1. The VLAN number it is using is unique, and
    2. The VLAN number is actually allocated to the HaaS; on some deployments
       we may have specific vlan numbers that we are allowed to use.
    """
    id = db.Column(db.Integer, primary_key=True)
    vlan_no = db.Column(db.Integer, nullable=False, unique=True)
    available = db.Column(db.Boolean, nullable=False)

    def __init__(self, vlan_no):
        self.vlan_no = vlan_no
        self.available = True


def setup(*args, **kwargs):
    set_network_allocator(VlanAllocator())
