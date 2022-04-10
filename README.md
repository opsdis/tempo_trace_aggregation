![Docker Pulls](https://img.shields.io/docker/pulls/athenodon/tempo_trace_aggregation)

Tempo trace aggregation - tta
-----------------------------

> The main purpose of this project is to be a demo for [nodegraph-provider](https://github.com/opsdis/nodegraph-provider)


# Overview
Tempo trace aggregation, tta, is an **example** how to create a dynamic service
map in Grafana with the [nodegraph plugin](https://grafana.com/docs/grafana/latest/visualizations/node-graph/) 
based on traces stored in [Grafana Tempo](https://github.com/grafana/tempo). 

![Overview](docs/overview.png?raw=true "Overview")

It requires the project Nodegraph-provider, https://github.com/opsdis/nodegraph-provider.
Please read the [README](https://github.com/opsdis/nodegraph-provider/blob/master/README.md) 
how the setup is done in Grafana.

![Petclinic Graph](docs/petclinic.png?raw=true "Example graph")


# Query Tempo
To get traces out of tempo we need to select on a tag name, default is `service.name`.
There is also possible just to filter on specific of the tag values of tag name
with regex. Default regex is `.*`
By default tta will create an additional node for the selected tag, this is often a benfit to get 
a graph that is fully connected.

# Requirements
- A tempo installation or just create a free account on [Grafana Cloud](https://grafana.com/products/cloud/)
- An installation of the [nodegraph-provider](https://github.com/opsdis/nodegraph-provider)
- Python 3.8 on the server you will be running tta. 

# Get started

Install python dependency

    pip install -r requierments.txt

See all tta options
```
python -m tempo_trace_aggregation -h 

usage: __main__.py [-h] [-g GRAPH] [-t TAG] [-f TAG_FILTER] [-n] [-T SERVICE_NODE_SUB_TITLE] [-L TRACE_THRESHOLD_MS] [-l LOOP_INTERVAL] [-c CONFIG] [-s SEARCH_FROM] [-m SEARCH_MODE]

tta - Tempo trace aggregation

optional arguments:
  -h, --help            show this help message and exit
  -g GRAPH, --graph GRAPH
                        graph model in nodegraph-provider, no default value
  -t TAG, --tag TAG     tag name to query on, default service.name
  -f TAG_FILTER, --filter TAG_FILTER
                        tag filter for the the tag value, default .*
  -n, --not_use_tag_as_node
                        use tag as a node, default true
  -T SERVICE_NODE_SUB_TITLE, --service_node_sub_title SERVICE_NODE_SUB_TITLE
                        the subTitle name, if use tag as a node, default 'Service Node'
  -L TRACE_THRESHOLD_MS, --trace_threshold_ms TRACE_THRESHOLD_MS
                        the trace threshold in ms that should indicate red on the graph node, default is 40.0
  -l LOOP_INTERVAL, --loop_interval LOOP_INTERVAL
                        loop with interval defined, default 0 sec, which means no looping
  -c CONFIG, --config CONFIG
                        config file for connections, default config.yml
  -s SEARCH_FROM, --search_from SEARCH_FROM
                        the number of seconds to search back in time, default 7200 sec (2h)
  -m SEARCH_MODE, --search_mode SEARCH_MODE
                        the Tempo search mode, available values are blocks, ingesters or all, default ingester

```

Example

     python -m tempo_trace_aggregation -t service.name -s 1200 -l 120 -m ingester

This will collect traces that have a label called `service.name` and aggregate on the 
label value of `service.name`. Only traces that exist in the ingester and happened in the last 1200 second will be 
aggregated and tta will do a new search every 120 second.

Please check out the command options and the example config file, `config_example.yml`, 
where all connection information for tempo and nodegraph-provider must exist.

# Build docker

Use the Dockerfile in the root directory of the project

     docker build -t tempo_trace_aggregation .

To run the image a config file must be mounted

     docker run -v $(pwd)/config.yaml:/app/config.yaml tempo_trace_aggregation

## Docker compose example

> Build image for [nodegraph-provider](https://github.com/opsdis/nodegraph-provider) before running `docker-compose up`

In the directory `docker-compose` there is a complete example to set up a running example with nodegraph-provider, 
redis with graph module and tempo_trace_aggregation.
The example is based on selecting trace tags `service.name`. Just go into the file called `tta_config.yml` and update
the connection to tempo.

# Nodegraph-provider configuration
The following nodegraph-provider configuration has a schema configuration that works with
tta.

```yml
# Default values are commented
# All default values can be overridden using environment values using NODEGRAPH_PROVIDER_XYZ
# Nested values should be separated with _


# API port
# port: 9393
# Configuration file name default without postfix
#config: config
# The prefix of the metrics
#prefix: nodegraph_provider


redis:
#  host: "localhost"
#  port: "6379"
#  db: 0
  #maxactive: 350
#  max_idle: 10


# The following do not have any default values

# The graph_schema define the field name and data type for the output to the data source.
# The field names are also used for the api calls to create, update and delete the nodes and edges.
# The only field not used in these api calls are the edge id that is automatically set to sourceid:targetid of
#  the nodes
graph_schemas:
  micro:
    # An example
    node_fields:
      - field_name: "id"
        type: "string"
      - field_name: "title"
        type: "string"
      - field_name: "subTitle"
        type: "string"
      - field_name: "mainStat"
        type: "number"
        displayName: "Count"
      - field_name: "secondaryStat"
        type: "number"
        displayName: "Avg duration (ms)"
      - field_name: "arc__failed"
        type: "number"
        color: "red"
      - field_name: "arc__passed"
        type: "number"
        color: "green"
      - field_name: "detail__role"
        type: "string"
        displayName: "Role"
    edge_fields:
      # id is never used in the api, will be set dynamically to nodes sourceid:targetid
      - field_name: "id"
        type: "string"
      - field_name: "source"
        type: "string"
      - field_name: "target"
        type: "string"
      - field_name: "mainStat"
        type: "number"
      - field_name: "secondaryStat"
        type: "number"
      - field_name: "detail__traffic"
        type: "string"
        displayName: "Traffic"


```
# Metrics explained
On the node the mainStat is a counter on the number of times it has been "active" in the
traces. The secondaryStat is the average latency time of the traces.
On the edge the mainStat is always 1, and the secondaryStat is always 0. 

So there is room for improvements for your specific use case. I have used the petclinic springboot microservice
project for testing, https://github.com/spring-petclinic/spring-petclinic-microservices.




