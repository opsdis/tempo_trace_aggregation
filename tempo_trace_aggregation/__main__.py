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

import argparse
import time

import yaml

from tempo_trace_aggregation.collect import TempoTraces, NodeGraphAPI, RestConnection

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='tta - Tempo trace aggregation')

    parser.add_argument('-g', '--graph',
                        dest="graph", help="graph model in nodegraph-provider", default='micro')

    parser.add_argument('-t', '--tag',
                        dest="tag", help="tag name to query on, default service.name", default='service.name')

    parser.add_argument('-f', '--filter',
                        dest="tag_filter", help="tag filter for the the tag value, default .*", default='.*')

    parser.add_argument('-n', '--not_use_tag_as_node', action='store_false',
                        dest="use_tag_as_node", help="use tag as a node, default true")

    parser.add_argument('-l', '--loop_interval',
                        dest="loop_interval", help="loop with interval defined, default 0 sec, which means no looping",
                        default=0)

    parser.add_argument('-c', '--config',
                        dest="config", help="config file for connections, default config.yml", default='config.yml')

    parser.add_argument('-s', '--search_from',
                        dest="search_from", help="the number of seconds to search back in time, default 7200 sec (2h)",
                        default=7200)

    parser.add_argument('-m', '--search_mode',
                        dest="search_mode",
                        help="the Tempo search mode, available values are blocks, ingesters or all, default ingester",
                        default='ingester')

    args = parser.parse_args()

    if not args.config:
        parser.print_help()
        exit(1)

    parsed_yaml = {}
    with open(args.config, 'r') as stream:
        try:
            parsed_yaml = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
            exit(1)

    if 'graph' in parsed_yaml:
        graph = parsed_yaml['graph'].get('name', args.graph)
    else:
        graph = args.graph

    if 'query' in parsed_yaml:
        tag = parsed_yaml['query'].get('tag', args.tag)
        tag_filter = parsed_yaml['query'].get('tag_filter', args.tag_filter)
        use_tag_as_node = parsed_yaml['query'].get('use_tag_as_node', args.use_tag_as_node)
    else:
        tag = args.tag
        tag_filter = args.tag_filter
        use_tag_as_node = args.use_tag_as_node

    if 'loop' in parsed_yaml:
        loop_interval = parsed_yaml['loop'].get('interval', args.loop_interval)
    else:
        loop_interval = args.loop_interval

    if 'search' in parsed_yaml:
        search_from = parsed_yaml['search'].get('from', args.search_from)
        search_mode = parsed_yaml['search'].get('mode', args.search_mode)
    else:
        search_from = args.search_from
        search_mode = args.search_mode

    nodegraph_provider_con = RestConnection()
    nodegraph_provider_con.url = parsed_yaml['nodegraph_provider']['url']
    nodegraph_provider_con.headers = parsed_yaml['nodegraph_provider']['headers']

    tempo_con = RestConnection()
    tempo_con.url = parsed_yaml['tempo']['url']
    tempo_con.headers = parsed_yaml['tempo']['headers']

    while True:
        tempo = TempoTraces(graph=graph, connection=tempo_con, tag=tag, tag_filter=tag_filter,
                            use_tag_as_node=use_tag_as_node)
        nodes, edges = tempo.execute(start_time=int(time.time() - float(search_from)), end_time=int(time.time()))

        nodeprovider = NodeGraphAPI(graph=graph, connection=nodegraph_provider_con)

        if nodes and edges:
            nodeprovider.update_nodes(nodes=nodes, edges=edges)
        else:
            nodeprovider.delete_graph()

        if int(loop_interval) == 0:
            break
        else:
            time.sleep(int(loop_interval))
