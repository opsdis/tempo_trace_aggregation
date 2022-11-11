# -*- coding: utf-8 -*-
"""
    Copyright (C) 2022  Anders Håål and Redbridge AB

    This file is part of tta - Tempo trace aggregation.

    indis is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    indis is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with tta.  If not, see <http://www.gnu.org/licenses/>.

"""

import base64
import json
import re
import time
from hashlib import md5
from typing import List, Dict, Any, Set, Tuple
import requests
from tempo_trace_aggregation.logging import Log

TWO_HOURS = 7200.0

log = Log(__name__)

EMPTY_RESPONSE = 'No traces found'
SERVICE_NODE_SUB_TITLE = "Service Node"


class EmptyResponse(Exception):
    pass


class RestConnection:
    def __init__(self):
        self.url: str = ''
        self.username: str = ''
        self.password: str = ''
        self.headers: Dict[str, str] = {}
        self.timeout = 15

    def get_headers(self):
        headers = self.headers
        if self.username and self.password:
            b64_auth = base64.b64encode(f"{self.username}:{self.password}")
            headers['Authorization'] = f"Basic {b64_auth}"
        return headers


class Node:
    def __init__(self):

        self.arc__failed: float = 0.0
        self.arc__passed: float = 1.0
        self.detail__role: str = ''
        self.id: str = ''
        self.mainStat: float = 0.0
        self.secondaryStat: float = 0.0
        self.subTitle: str = ''
        self.title: str = ''

    def to_params(self):
        params: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key != 'id':
                params[key] = str(value)

        return params

    def to_params_id(self):
        params: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            params[key] = str(value)

        return params


class Edge:
    def __init__(self):
        self.source: str = ""
        self.target: str = ""
        self.mainStat: float = 0.0
        self.secondaryStat: float = 0.0

    def get_id(self):
        return f"{self.source}:{self.target}"

    def to_params(self):
        params: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            params[key] = str(value)

        return params


class TempoTraces:
    def __init__(self, graph: str, connection: RestConnection, tag: str, tag_filter: str = ".*",
                 use_tag_as_node: bool = True, service_node_sub_title: str = SERVICE_NODE_SUB_TITLE,
                 trace_threshold_ms: float = 40.0):
        self.graph = graph
        self._connection = connection
        self.tag = tag
        self.tag_filter = tag_filter
        self.use_tag_as_node = use_tag_as_node
        self.service_node_sub_title = service_node_sub_title
        self.trace_threshold_ms = trace_threshold_ms

    def execute(self,
                start_time: int = int(time.time() - TWO_HOURS),
                end_time: int = int(time.time()),
                search_mode: str = 'ingesters') -> Tuple[List[Node], List[Edge]]:

        start = time.time()
        log.info_fmt({'graph': self.graph, 'tag': self.tag}, "Search tags")
        # Get all values for the selected tag, e.g. service.name
        try:
            all_service_tags = self._api_call(f"/search/tag/{self.tag}/values")
        except EmptyResponse:
            log.warn_fmt({'graph': self.graph, 'url': f"/search/tag/{self.tag}/values"}, f"{EMPTY_RESPONSE}")
            return list(), list()

        nodes: Dict[str, Node] = {}
        span_to_node: Dict[str, Set[str]] = {}
        node_span_parent: Dict[str, Set[str]] = {}

        # Iterate over values of the tag and match against regular expression in tag_filter
        # e.g. tag_filer = "cortex.*)
        for tag_value in all_service_tags['tagValues']:
            if not re.search(self.tag_filter, tag_value):
                continue
            try:
                s_t = time.time()
                # Get all trace id for the specific tag_value e.g cortex-ingester, cortex-compactor and
                # for the time period start_time to end_time
                all_traces = self._api_call(f"/search?tags={self.tag}%3D{tag_value}&start={start_time}&end={end_time}")
                log.info_fmt({'graph': self.graph, 'tag': self.tag, 'tag_value': tag_value,
                              'response_time': (time.time() - s_t)},
                             "Search traces")
            except EmptyResponse:
                log.info_fmt({'graph': self.graph, 'url': f"/search?tags={self.tag}%3D{tag_value}"},
                             f"{EMPTY_RESPONSE}")
                continue

            # high level node for the service
            if self.use_tag_as_node:
                service_node_id = md5(str.encode(f"{tag_value}##service")).hexdigest()
                if service_node_id not in nodes:
                    service_node = Node()
                    service_node.id = service_node_id
                    service_node.title = tag_value
                    service_node.subTitle = SERVICE_NODE_SUB_TITLE
                    nodes[service_node_id] = service_node
                    if service_node_id not in span_to_node:
                        span_to_node[service_node_id] = set()
                    span_to_node[service_node_id].add(service_node_id)
                service_node = nodes[service_node_id]

            # If the above search include traces
            if 'traces' in all_traces:
                log.info_fmt(
                    {'graph': self.graph, 'tag': self.tag, 'tag_value': tag_value, 'count': len(all_traces['traces'])},
                    "Number of traces")
                for trace in all_traces['traces']:
                    # Only use traces where the rootTraceName is existing and set
                    # The rootTraceName is missing if the trace is not "completed" yet
                    # Typical the rootServiceName is set to '<root span not yet received>'
                    if 'rootTraceName' in trace:
                        try:
                            s_t = time.time()
                            # Fetch the complete trace with the search_mode that define if the search should be done
                            # on the blocks, ingesters or both (all)
                            trace_spans = self._api_call(f"/traces/{trace['traceID']}?mode={search_mode}")
                            log.info_fmt({'graph': self.graph, 'tag': self.tag, 'tag_value': tag_value,
                                          'trace_id': trace['traceID'],
                                          'response_time': (time.time() - s_t)}, "Fetch trace")
                        except EmptyResponse:
                            log.info_fmt({'graph': self.graph, 'url': f"/traces/{trace['traceID']}"},
                                         f"{EMPTY_RESPONSE}")
                            continue

                        # All spans are located in the key batches. This is a list of dict with 'resource' and
                        # 'instrumentationLibrarySpans'
                        # resource include a list of attributes for the span with key value, e.g.
                        # {'key': 'service.name', 'value': {'stringValue': 'cortex-distributor'}}
                        # {'key': 'ip', 'value': {'stringValue': '10.62.133.95'}}
                        for span_resources in trace_spans['batches']:

                            # The first in the list is the key service.name
                            # TODO - if this in the future is not sorted we need to loop through the list
                            service = span_resources['resource']['attributes'][0]['value']['stringValue']
                            # Get all the spanid
                            # Where are the spans?
                            # Depending on trace framework the span data can be in different part of the returned trace
                            # Better would be to define otel, zipkin etc as a config
                            # scopeSpans is when the otel collector is used
                            span_key = "scopeSpans"
                            if 'instrumentationLibrarySpans' in span_resources:
                                span_key = 'instrumentationLibrarySpans'

                            for spans in span_resources[span_key]:
                                for span in spans['spans']:
                                    if 'name' in span:
                                        # Get the span name and create an encoding of the combination of
                                        # service and span name, e.g. 'cortex-ingester##/cortex.Ingester/Push'
                                        # This is used as the Node identity
                                        node_id = md5(str.encode(f"{service}##{span['name']}")).hexdigest()
                                        if node_id not in nodes:
                                            node = Node()
                                            node.id = node_id
                                            node.title = service
                                            node.subTitle = span['name']
                                            nodes[node_id] = node
                                        node = nodes[node_id]
                                        # Do stuff with metrics
                                        node.mainStat += 1
                                        node.secondaryStat += \
                                            ((node.secondaryStat + float(span['endTimeUnixNano']) - float(
                                                span['startTimeUnixNano']))
                                             / node.mainStat) / 1000000
                                        if node.secondaryStat > self.trace_threshold_ms:
                                            node.arc__failed = 1.0
                                            node.arc__passed = 0.0
                                        else:
                                            node.arc__failed = 0.0
                                            node.arc__passed = 1.0

                                        if self.use_tag_as_node:
                                            service_node.mainStat += 1
                                        # Keep track node id to parent span

                                        if 'parentSpanId' in span:
                                            if node_id not in node_span_parent:
                                                node_span_parent[node_id] = set()
                                            node_span_parent[node_id].add(span['parentSpanId'])
                                        elif self.use_tag_as_node:
                                            if node_id not in node_span_parent:
                                                node_span_parent[node_id] = set()
                                            node_span_parent[node_id].add(service_node_id)

                                        if node_id not in span_to_node:
                                            span_to_node[span['spanId']] = set()
                                        span_to_node[span['spanId']].add(node_id)
        # Create edges
        edges: Dict[str, Edge] = {}
        if nodes:
            for node_id_taget, spans in node_span_parent.items():
                for span_id in spans:
                    if span_id in span_to_node:
                        for node_id_source in span_to_node[span_id]:
                            edge = Edge()
                            edge.source = node_id_source
                            edge.target = node_id_taget
                            if f"{edge.source}#{edge.target}" not in edges:
                                edges[f"{edge.source}#{edge.target}"] = edge
                            edge = edges[f"{edge.source}#{edge.target}"]
                            edge.mainStat += 1
                    else:
                        log.info_fmt(
                            {'graph': self.graph, 'span_id': span_id},
                            "Missing span id in node graph when creating edges")

        log.info_fmt(
            {'graph': self.graph, 'nodes': len(nodes.values()), 'edges': len(edges.values()),
             'time': time.time() - start},
            "Read traces from tempo")

        if nodes and edges:
            return list(nodes.values()), list(edges.values())
        else:
            return list(), list()

    def _api_call(self, url_path: str) -> Dict[str, Any]:
        try:
            r = requests.get(url=f"{self._connection.url}{url_path}", headers=self._connection.headers,
                             timeout=self._connection.timeout)
            if r.status_code == 200:
                response = r.json()
                if response:
                    return response

        except Exception as err:
            log.error_fmt({'graph': self.graph, 'tag': self.tag, 'url': url_path, 'error': err.__str__()},
                          "Connection to tempo failed")
        raise EmptyResponse()


class NodeGraphAPI:
    def __init__(self, graph: str, connection: RestConnection):
        self.graph = graph
        self._connection = connection

    def delete_graph(self):
        try:
            requests.delete(f"{self._connection.url}/api/graphs/{self.graph}",
                          headers=self._connection.headers, timeout=self._connection.timeout)
            #requests.post(f"{self._connection.url}/api/controller/{self.graph}/delete-all",
                          #headers=self._connection.headers, timeout=self._connection.timeout)
        except Exception as err:
            log.error_fmt(
                {'graph': self.graph, 'operation': 'delete-all', 'error': err.__str__()},
                "Connection to nodegraph_provider failed")

    def update_nodes(self, nodes: List[Node], edges: List[Edge]):
        """
        This method is deprecated
        :param nodes:
        :param edges:
        :return:
        """
        self.delete_graph()

        start = time.time()
        try:
            for node in nodes:
                r = requests.get(f"{self._connection.url}/api/nodes/{self.graph}/{node.id}",
                                 headers=self._connection.headers, timeout=self._connection.timeout)
                if r.status_code == 404:
                    requests.post(f"{self._connection.url}/api/nodes/{self.graph}", headers=self._connection.headers,
                                  timeout=self._connection.timeout,
                                  data=json.dumps(node.to_params_id()))
                elif r.status_code == 200:
                    requests.put(f"{self._connection.url}/api/nodes/{self.graph}/{node.id}",
                                 headers=self._connection.headers, timeout=self._connection.timeout,
                                 params=node.to_params())
                else:
                    log.warn_fmt({'graph': self.graph, 'object': 'node', 'operation': 'create/update',
                                  'status_code': r.status_code}, "Failed to create/update node")
        except Exception as err:
            log.error_fmt({'graph': self.graph, 'object': 'node', 'operation': 'create/update', 'error': err.__str__()},
                          "Connection to nodegraph_provider failed")

        try:
            for edge in edges:
                r = requests.get(f"{self._connection.url}/api/edges/{self.graph}/{edge.source}/{edge.target}",
                                 headers=self._connection.headers, timeout=self._connection.timeout)
                if r.status_code == 404:
                    requests.post(f"{self._connection.url}/api/edges/{self.graph}", headers=self._connection.headers,
                                  timeout=self._connection.timeout,
                                  data=json.dumps(edge.to_params()))

                elif r.status_code == 200:
                    requests.put(f"{self._connection.url}/api/edges/{self.graph}/{edge.source}/{edge.target}",
                                 headers=self._connection.headers, timeout=self._connection.timeout,
                                 params=node.to_params())
                else:
                    log.warn_fmt({'graph': self.graph, 'object': 'edge', 'operation': 'create/update',
                                  'status_code': r.status_code}, "Failed to create/update edge")

        except Exception as err:
            log.error_fmt({'graph': self.graph, 'object': 'edge', 'operation': 'create/update', 'error': err.__str__()},
                          "Connection to nodegraph_provider failed")

        log.info_fmt(
            {'graph': self.graph, 'nodes': len(nodes), 'edges': len(edges), 'time': time.time() - start},
            "Update nodegraph_provider")

    def batch_update_nodes(self, nodes: List[Node], edges: List[Edge]):

        start = time.time()

        batch = {'nodes': [], 'edges': []}

        for node in nodes:
            batch['nodes'].append(node.to_params_id())
        for edge in edges:
            batch['edges'].append(edge.to_params())

        try:
            r = requests.post(f"{self._connection.url}/api/graphs/{self.graph}", headers=self._connection.headers,
                              timeout=self._connection.timeout,
                              data=json.dumps(batch))
            if r.status_code != 201:
                log.warn_fmt({'graph': self.graph, 'object': 'graph', 'operation': 'create',
                              'status_code': r.status_code}, "Failed to create graph")
        except Exception as err:
            log.error_fmt({'graph': self.graph, 'object': 'graph', 'operation': 'create', 'error': err.__str__()},
                          "Connection to nodegraph_provider failed")
        log.info_fmt(
            {'graph': self.graph, 'nodes': len(nodes), 'edges': len(edges), 'time': time.time() - start},
            "Update nodegraph_provider")
