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

log = Log(__name__)


class EmptyResponse(Exception):
    pass


class RestConnection:
    def __init__(self):
        self.url: str = ''
        self.username: str = ''
        self.password: str = ''
        self.headers: Dict[str, str] = {}

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
                 use_tag_as_node: bool = True):
        self.graph = graph
        self._connection = connection
        self.tag = tag
        self.tag_filter = tag_filter
        self.use_tag_as_node = use_tag_as_node

    def execute(self) -> Tuple[List[Node], List[Edge]]:

        start = time.time()
        try:
            all_service_tags = self._api_call(f"/search/tag/{self.tag}/values")
        except EmptyResponse:
            log.warn_fmt({'url': f"/search/tag/{self.tag}/values"}, f"Empty response")
            return list(), list()

        nodes: Dict[str, Node] = {}
        span_to_node: Dict[str, Set[str]] = {}
        node_span_parent: Dict[str, Set[str]] = {}

        for tag_value in all_service_tags['tagValues']:
            if not re.search(self.tag_filter, self.tag):
                continue
            try:
                all_traces = self._api_call(f"/search?tags={self.tag}%3D{tag_value}")
            except EmptyResponse:
                log.info_fmt({'url': f"/search?tags={self.tag}%3D{tag_value}"}, f"Empty response")
                continue

            # high level node for the service
            if self.use_tag_as_node:
                service_node_id = md5(str.encode(f"{self.tag}##service")).hexdigest()
                if service_node_id not in nodes:
                    service_node = Node()
                    service_node.id = service_node_id
                    service_node.title = tag_value
                    service_node.subTitle = "Trace ingress"
                    nodes[service_node_id] = service_node
                    if service_node_id not in span_to_node:
                        span_to_node[service_node_id] = set()
                    span_to_node[service_node_id].add(service_node_id)
                service_node = nodes[service_node_id]

            if 'traces' in all_traces:
                for trace in all_traces['traces']:
                    if 'rootTraceName' in trace:
                        # print(trace['traceID'])
                        try:
                            trace_spans = self._api_call(f"/traces/{trace['traceID']}")
                        except EmptyResponse:
                            log.info_fmt({'url': f"/traces/{trace['traceID']}"}, f"Empty response")
                            continue
                        for span_resources in trace_spans['batches']:
                            # print(span_resources['resource']['attributes'][0]['value']['stringValue'])
                            service = span_resources['resource']['attributes'][0]['value']['stringValue']
                            for spans in span_resources['instrumentationLibrarySpans']:
                                for span in spans['spans']:
                                    if 'name' in span:
                                        # print(f">>>> {span['spanId']} {span['name']}")
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
                                        if node.secondaryStat > 40.0:
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
                    for node_id_source in span_to_node[span_id]:
                        edge = Edge()
                        edge.source = node_id_source
                        edge.target = node_id_taget
                        if f"{edge.source}#{edge.target}" not in edges:
                            edges[f"{edge.source}#{edge.target}"] = edge
                        edge = edges[f"{edge.source}#{edge.target}"]
                        edge.mainStat += 1

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
            r = requests.get(url=f"{self._connection.url}{url_path}", headers=self._connection.headers)
            if r.status_code == 200:
                response = r.json()
                if response:
                    return response
            
        except Exception as err:
            log.error_fmt({'graph': self.graph, 'error': err}, "Connection to tempo failed")
        raise EmptyResponse()


class NodeGraphAPI:
    def __init__(self, graph: str, connection: RestConnection):
        self.graph = graph
        self._connection = connection

    def delete_graph(self):
        try:
            requests.post(f"{self._connection.url}/api/controller/{self.graph}/delete-all",
                          headers=self._connection.headers)
        except Exception as err:
            log.error_fmt(
                {'graph': self.graph, 'error': err}, "Connection to nodegraph_provider failed")

    def update_nodes(self, nodes: List[Node], edges: List[Edge]):
        self.delete_graph()

        start = time.time()
        try:
            for node in nodes:
                r = requests.get(f"{self._connection.url}/api/nodes/{self.graph}/{node.id}",
                                 headers=self._connection.headers)
                if r.status_code == 404:
                    requests.post(f"{self._connection.url}/api/nodes/{self.graph}", headers=self._connection.headers,
                                  data=json.dumps(node.to_params_id()))
                elif r.status_code == 200:
                    requests.put(f"{self._connection.url}/api/nodes/{self.graph}/{node.id}",
                                 headers=self._connection.headers,
                                 params=node.to_params())
                else:
                    log.warn_fmt({'graph': self.graph, 'status_code': r.status_code}, "Failed to create/update node")

            for edge in edges:
                r = requests.get(f"{self._connection.url}/api/edges/{self.graph}/{edge.source}/{edge.target}",
                                 headers=self._connection.headers)
                if r.status_code == 404:
                    requests.post(f"{self._connection.url}/api/edges/{self.graph}", headers=self._connection.headers,
                                  data=json.dumps(edge.to_params()))

                elif r.status_code == 200:
                    requests.put(f"{self._connection.url}/api/edges/{self.graph}/{edge.source}/{edge.target}",
                                 headers=self._connection.headers,
                                 params=node.to_params())
                else:
                    log.warn_fmt({'graph': self.graph, 'status_code': r.status_code}, "Failed to create/update edge")

        except Exception as err:
            log.error_fmt({'graph': self.graph, 'error': err}, "Connection to nodegraph_provider failed")
        finally:
            log.info_fmt(
                {'graph': self.graph, 'nodes': len(nodes), 'edges': len(edges), 'time': time.time() - start},
                "Update nodegraph_provider")
