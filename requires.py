# Copyright 2018 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ipaddress
import json
import socket

# the reactive framework unfortunately does not grok `import as` in conjunction
# with decorators on class instance methods, so we have to revert to `from ...`
# imports
from charms.reactive import (
    Endpoint,
    all_flags_set,
    clear_flag,
    set_flag,
    when,
    when_not,
)

import charmhelpers.contrib.storage.linux.ceph as ch_ceph


class CephRBDMirrorRequires(Endpoint):

    def __init__(self, endpoint_name, relation_ids=None, unique_id=None):
        """Initialize unique ID.

        This is used when requesting a key from Ceph.

        The constructor exists mainly for testing purposes.
        """
        if unique_id:
            self.unique_id = unique_id
        else:
            self.unique_id = socket.gethostname()
        self.key_name = '{}_key'.format(self.unique_id)
        super().__init__(endpoint_name, relation_ids=relation_ids)

    @when('endpoint.{endpoint_name}.joined')
    def joined(self):
        set_flag(self.expand_name('{endpoint_name}.connected'))

    @when('endpoint.{endpoint_name}.changed')
    def changed(self):
        flags = (
            self.expand_name(
                'endpoint.{endpoint_name}.changed.auth'),
            self.expand_name(
                'endpoint.{endpoint_name}.changed.' + self.key_name),
            self.expand_name(
                'endpoint.{endpoint_name}.changed.ceph-public-address'),
        )
        if all_flags_set(*flags):
            for flag in (flags):
                clear_flag(flag)
            set_flag(self.expand_name('{endpoint_name}.available'))

    @when_not('endpoint.{endpoint_name}.joined')
    def broken(self):
        clear_flag(self.expand_name('{endpoint_name}.available'))
        clear_flag(self.expand_name('{endpoint_name}.connected'))

    def request_key(self):
        for relation in self.relations:
            relation.to_publish['unique_id'] = self.unique_id

    def get_current_request(self):
        """
        Retrieve the current Ceph broker request.

        If no request has been created yet then create a new one.
        """
        json_rq = self.all_joined_units.received['broker_req']
        current_request = ch_ceph.CephBrokerRq()
        if json_rq:
            try:
                j = json.loads(json_rq)
                current_request.set_ops(j['ops'])
            except (KeyError, json.decoder.JSONDecodeError):
                raise
        return current_request

    def create_replicated_pool(self, name, replicas=3, weight=None,
                               pg_num=None, group=None, namespace=None,
                               app_name=None, max_bytes=None,
                               max_objects=None):
        """Request replicated pool setup.
        """
        # Ensure type of numeric values before sending over the wire
        replicas = int(replicas) if replicas else None
        weight = float(weight) if weight else None
        pg_num = int(pg_num) if pg_num else None
        max_bytes = int(max_bytes) if max_bytes else None
        max_objects = int(max_objects) if max_objects else None

        current_request = self.get_current_request()
        current_request.add_op_create_replicated_pool(
            name="{}".format(name),
            replica_count=replicas,
            pg_num=pg_num,
            weight=weight,
            group=group,
            namespace=namespace,
            app_name=app_name,
            max_bytes=max_bytes,
            max_objects=max_objects)
        ch_ceph.send_request_if_needed(current_request,
                                       relation=self.endpoint_name)

    def create_erasure_pool(self, name, erasure_profile=None, weight=None,
                            group=None, app_name=None, max_bytes=None,
                            max_objects=None):
        """Request erasure coded pool setup.
        """
        # Ensure type of numeric values before sending over the wire
        weight = float(weight) if weight else None
        max_bytes = int(max_bytes) if max_bytes else None
        max_objects = int(max_objects) if max_objects else None

        current_request = self.get_current_request()
        current_request.add_op_create_erasure_pool(
            name="{}".format(name),
            erasure_profile=erasure_profile,
            weight=weight,
            group=group,
            app_name=app_name,
            max_bytes=max_bytes,
            max_objects=max_objects)
        ch_ceph.send_request_if_needed(current_request,
                                       relation=self.endpoint_name)

    @property
    def auth(self):
        return self.all_joined_units.received['auth']

    @property
    def key(self):
        return self.all_joined_units.received[self.key_name]

    def mon_hosts(self):
        """
        NOTE(fnordahl): As much as this should and could have been a property
        we have pre-existing interfaces providing this as a function.  To be
        able to use the same code for relation adaption etc in
        ``charms.openstack`` we must keep having this as a function unless we
        go back and change both to being properties.
        """
        for relation in self.relations:
            for unit in relation.units:
                try:
                    addr = ipaddress.ip_address(
                        unit.received.get('ceph-public-address', ''))
                except ValueError:
                    continue
                port = 6789
                if isinstance(addr, ipaddress.IPv6Address):
                    yield '[{}]:{}'.format(addr, port)
                else:
                    yield '{}:{}'.format(addr, port)

    @property
    def public_network(self):
        pass

    @property
    def cluster_network(self):
        pass

    @property
    def pools(self):
        return self.all_joined_units.received['pools']
