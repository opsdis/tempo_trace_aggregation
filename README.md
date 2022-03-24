Tempo trace aggregation - tta
-----------------------------

> The main purpose of this project is to be a demo for [nodegraph-provider](https://github.com/opsdis/nodegraph-provider)


# Overview
Tempo trace aggregation, tta, is an **example** how to create a dynamic service
map in Grafana with the [nodegraph plugin](https://grafana.com/docs/grafana/latest/visualizations/node-graph/) 
based on traces stored in [Grafana Tempo](https://github.com/grafana/tempo). 
It requires the project Nodegraph-provider, https://github.com/opsdis/nodegraph-provider.
Please read the [README](https://github.com/opsdis/nodegraph-provider/blob/master/README.md) 
how the setup is done in Grafana.

![Petclinic Graph](docs/petclinic.png?raw=true "Example graph")


# Query Tempo
To get traces out of tempo we need to select on a tag name, default is `service.name`.
There is also possible just to filter on specific of the tag values of tag name
with regex. Default regex is `.*`
By default tta will create a additional node for the selected tag, this is often a benfit to get 
a graph that is fully connected.

# Requirements
- A tempo installation or just create a free account on [Grafana Cloud](https://grafana.com/products/cloud/)
- An installation of the [nodegraph-provider](https://github.com/opsdis/nodegraph-provider)
- Python 3.8 on the server you will be running tta. 

# Get started

Install python dependency

    pip install -r requierments.txt

See all tta options

    python -m tempo_trace_aggregation -h 

Please check out the command options and the example config file, `config_example.yml`, 
where all connection information for tempo and nodegraph-provider must exist.

# Metrics explained
On the node the mainStat is a counter on the number of times its been "active" in the
traces. The secondaryStat is the average latency time of the traces.
On the edge the mainStat is always 1, and the secondaryStat is always 0. 

So there is room for improvements for your specific use case. I have used the petclinic springboot microservice
project for testing, https://github.com/spring-petclinic/spring-petclinic-microservices.



