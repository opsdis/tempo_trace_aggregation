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
from typing import Dict, Any

import yaml

from tempo_trace_aggregation.collect import TempoTraces, NodeGraphAPI, RestConnection
from tempo_trace_aggregation.logging import Log

log = Log(__name__)


class MissingArgument(Exception):
    def __init__(self, argument: str):
        self.argument = argument

    def get_missing(self):
        return self.argument


def resolve(arguments: {}, config_object: str, attribute: str, arg, default=None):
    if arg:
        if config_object not in arguments:
            arguments[config_object] = {attribute: arg}
        else:
            arguments[config_object][attribute] = arg
    elif config_object not in arguments and default:
        arguments[config_object] = {attribute: default}
    elif config_object in arguments and attribute not in arguments[config_object] and default:
        arguments[config_object][attribute] = default

    if config_object not in arguments:
        raise MissingArgument(
            f"Configuration for \"{config_object}\"->\"{attribute}\" is missing in configuration file or as argument "
            f"and no default exists")
    elif attribute not in arguments[config_object]:
        raise MissingArgument(
            f"Configuration for \"{config_object}\"->\"{attribute}\" is missing in configuration file or as argument "
            f"and no default exists")


def argument_parser() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description='tta - Tempo trace aggregation')

    parser.add_argument('-g', '--graph',
                        dest="graph", help="graph model in nodegraph-provider, no default value")

    parser.add_argument('-t', '--tag',
                        dest="tag", help="tag name to query on, default service.name")

    parser.add_argument('-f', '--filter',
                        dest="tag_filter", help="tag filter for the the tag value, default .*")

    parser.add_argument('-n', '--not_use_tag_as_node', action='store_false',
                        dest="use_tag_as_node", help="use tag as a node, default true")

    parser.add_argument('-T', '--service_node_sub_title',
                        dest="service_node_sub_title", help="the subTitle name, if use tag as a node, default 'Service Node'")

    parser.add_argument('-L', '--trace_threshold_ms',
                        dest="trace_threshold_ms",
                        help="the trace threshold in ms that should indicate red on the graph node, default is 40.0")

    parser.add_argument('-l', '--loop_interval',
                        dest="loop_interval", help="loop with interval defined, default 0 sec, which means no looping")

    parser.add_argument('-c', '--config',
                        dest="config", help="config file for connections, default config.yml", default='config.yml')

    parser.add_argument('-s', '--search_from',
                        dest="search_from", help="the number of seconds to search back in time, default 7200 sec (2h)")

    parser.add_argument('-m', '--search_mode',
                        dest="search_mode",
                        help="the Tempo search mode, available values are blocks, ingesters or all, default ingester")

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
    # Must include connections
    if 'tempo' not in parsed_yaml or 'nodegraph_provider' not in parsed_yaml:
        print(f"error - Configuration file must include connections")
        parser.print_help()
        exit(1)
    try:
        resolve(parsed_yaml, 'graph', 'name', args.graph, None)
        resolve(parsed_yaml, 'query', 'tag', args.tag, 'service.name')
        resolve(parsed_yaml, 'query', 'tag_filter', args.tag_filter, '.*')
        resolve(parsed_yaml, 'query', 'use_tag_as_node', args.use_tag_as_node, True)
        resolve(parsed_yaml, 'query', 'trace_threshold_ms', args.trace_threshold_ms, '40.0')
        resolve(parsed_yaml, 'query', 'service_node_sub_title', args.service_node_sub_title, 'Service Node')
        resolve(parsed_yaml, 'loop', 'interval', args.loop_interval, '0')
        resolve(parsed_yaml, 'search', 'from', args.search_from, '7200')
        resolve(parsed_yaml, 'search', 'mode', args.search_mode, 'ingesters')
    except MissingArgument as err:
        print(f"error - {err.get_missing()}")
        parser.print_help()
        exit(1)

    info = {}
    for key in parsed_yaml.keys():
        if key in ['graph', 'query', 'loop', 'search']:
            info[key] = parsed_yaml[key]

    log.info_fmt(info, "configuration")
    return parsed_yaml


if __name__ == "__main__":
    conf = argument_parser()

    nodegraph_provider_con = RestConnection()
    nodegraph_provider_con.url = conf['nodegraph_provider']['url']
    nodegraph_provider_con.headers = conf['nodegraph_provider']['headers']
    if 'timeout' in conf['nodegraph_provider']:
        nodegraph_provider_con.timeout = conf['nodegraph_provider']['timeout']

    tempo_con = RestConnection()
    tempo_con.url = conf['tempo']['url']
    tempo_con.headers = conf['tempo']['headers']
    if 'timeout' in conf['tempo']:
        tempo_con.timeout = conf['tempo']['timeout']

    while True:
        tempo = TempoTraces(graph=conf['graph']['name'], connection=tempo_con,
                            tag=conf['query']['tag'],
                            tag_filter=conf['query']['tag_filter'],
                            use_tag_as_node=conf['query']['use_tag_as_node'],
                            service_node_sub_title=conf['query']['service_node_sub_title'],
                            trace_threshold_ms=float(conf['query']['trace_threshold_ms']))

        nodes, edges = tempo.execute(start_time=int(time.time() - float(conf['search']['from'])),
                                     end_time=int(time.time()),
                                     search_mode=conf['search']['mode'])

        nodeprovider = NodeGraphAPI(graph=conf['graph']['name'], connection=nodegraph_provider_con)

        if nodes and edges:
            nodeprovider.update_nodes(nodes=nodes, edges=edges)
        else:
            nodeprovider.delete_graph()

        if int(conf['loop']['interval']) == 0:
            break
        else:
            time.sleep(int(conf['loop']['interval']))
