#!/usr/bin/env python
from json import dumps
import logging
import os
import requests
from urllib.parse import urlparse

import keys

from flask import render_template, url_for, request, jsonify
from flask import (
    Flask,
    g,
    request,
    Response,
    render_template,
    url_for,
    jsonify,
)
from neo4j import (
    GraphDatabase,
    basic_auth,
)


app = Flask(__name__, static_url_path="/static/")

url = keys.url
username = keys.username
password = keys.password

neo4j_version = os.getenv("NEO4J_VERSION", "4")
database = os.getenv("NEO4J_DATABASE", "neo4j")

port = os.getenv("PORT", 19132)

driver = GraphDatabase.driver(url, auth=basic_auth(username, password))


def get_db():
    if not hasattr(g, "neo4j_db"):
        if neo4j_version >= "4":
            g.neo4j_db = driver.session(database=database)
        else:
            g.neo4j_db = driver.session()
    return g.neo4j_db


def drop_data(tx, _data):
    """Delete all data, indexes, constraints"""
    tx.run("MATCH (n) DETACH DELETE n").consume()
    return True


def drop_constraints(tx, _data):
    """Delete all data, indexes, constraints"""
    tx.run("CALL apoc.schema.assert({}, {})").consume()
    return True


def init_db(tx, _data):
    """Initialise DB constraints, etc"""
    tx.run("CREATE CONSTRAINT FOR (p:Page) REQUIRE p.url IS UNIQUE"
           ).consume()
    tx.run("CREATE CONSTRAINT FOR (p:Page) REQUIRE p.url IS NOT NULL"
           ).consume()
    return True


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, "neo4j_db"):
        g.neo4j_db.close()


def process_dexter(id):
    """Process dexter results to be more neo4j-able"""
    data = []
    url = "https://dxtfs.com/%s(application,json)" % id
    response = requests.get(url)
    j = response.json()
    for (url, row) in j["urls"].items():
        if url not in j["pages"]:
            continue
        row["url"] = url
        if "links" in row:
            row["fixed_links"] = []
            for (link, link_datas) in row["links"].items():
                if link not in j["pages"]:
                    continue
                for link_data in link_datas:
                    link_data["to"] = link
                    row["fixed_links"].append(link_data)
            row["links"] = row["fixed_links"]
            del row["fixed_links"]
        data.append(row)
    return data


#@app.route("/")
#def get_index():
#    return render_template("index.html")

@app.route('/dexter/data/<id>')
def dexter_data(id):
    data = process_dexter(id)
    return jsonify(isError=False,
                    message= "Success",
                    statusCode= 200,
                    data= data), 200

@app.route('/')
@app.route('/dexter/fetch')
def dexter_fetch():
    return render_template('dexter/fetch.html')


@app.route('/info/d3_force')
def info_d3_force():
    return render_template('info/d3_force.html')


@app.route('/info/d3_concept')
def info_d3_concept():
    return render_template('info/d3_concept.html')


@app.route("/info/any_node")
def get_anychart():
    return render_template("/info/any_node.html")


@app.route("/info/any_edge_graph")
def get_anyedgegraph():
    return render_template("/info/any_edge_graph.html")


@app.route('/dexter/report', methods=['POST',])
@app.route('/dexter/report/<id>')
def dexter_report(id=None):
    """Create new db for report"""
    def work(tx, _data):
        tx.run(
            "WITH $data AS value "
            "UNWIND value AS item "
            "MERGE (p:Page {url: item.url}) "
            "SET p.screenshot = item.screenshot.storage "
            "SET p.contentTested = item.contentTested "
            "SET p.mimeType = item.mimeType "
            "WITH p, item "
            "UNWIND [x IN item.links] AS link "
            "MERGE (l:Page {url: link.to}) "
            "MERGE (p) -[lt:LINK_TO]-> (l) "
            "SET lt.redirect = l.redirect "
            "WITH p, item.diagnostics AS diags "
            "UNWIND [x in diags] AS diag "
            "MERGE (d:Diag "
                "{category: diag.category, "
                "name: diag.name, "
                "level: diag.level, "
                "message: diag.message}) "
            "MERGE (p) -[:HAS_DIAG]-> (d)",
            {"data": _data}
        ).consume()

    if not id:
        id = request.form.get('id')
    data = process_dexter(id)

    db = get_db()
    db.execute_write(drop_data, data)
    db.execute_write(drop_constraints, data)
    db.execute_write(init_db, data)
    summary = db.execute_write(work, data)
    db.close()

    return jsonify(isError= False,
                    message= "Success",
                    statusCode= 200,
                    data= data), 200


@app.route("/nodes")
def get_nodes():
    def pages(tx, limit):
        return list(tx.run(
            "MATCH (node:Page) "
            "RETURN node.url AS url "
            "LIMIT $limit",
            {"limit": limit}
        ))
    def links(tx, limit):
        return list(tx.run(
            "MATCH (s:Page)-[:LINK_TO]->(d:Page) "
            "RETURN s.url AS src, d.url AS dest "
            "LIMIT $limit",
            {"limit": limit}
        ))

    db = get_db()
    results = db.read_transaction(pages, request.args.get("limit", 100))
    nodes = []
    i = 0
    node_id = {}
    for row in results:
        node_id[row["url"]] = i
        nodes.append({"id": i, "url": row["url"], "label": "page"})
        i += 1
    rels = []
    results = db.read_transaction(links, request.args.get("limit", 100))
    for row in results:
        rels.append({"source": node_id[row["src"]],
                     "target": node_id[row["dest"]]})
    return Response(dumps({"nodes": nodes, "links": rels}),
                    mimetype="application/json")


@app.route("/json/d3/concept")
def get_d3_concept():
    def pages(tx, limit):
        return list(tx.run(
            "MATCH (p:Page) "
            "RETURN p "
            "LIMIT $limit",
            {"limit": limit}
        ))
    def links(tx, limit):
        return list(tx.run(
            "MATCH (s:Page)-[l:LINK_TO]->(d:Page) "
            "RETURN s.url AS src, l AS link, d.url AS dest "
            "LIMIT $limit",
            {"limit": limit}
        ))

    db = get_db()
    results = db.read_transaction(pages, request.args.get("limit", 10000))
    nodes = []
    i = 0
    node_id = {}
    for result in results:
        page = result['p']
        label = urlparse(page.get("url")).path[:32]
        node_id[page.get("url")] = i
        node = {"id": i, "url": page.get("url"),
                "label": label,
                "group": page.get("mimeType")}
        if not page.get("contentTested"):
            node.update({"group": "disabled"})
        if page.get("screenshot"):
            node.update({ "height": 100, "width": 100,
                "shape": "square", "stroke": "none",
                "fill": { "src": page["screenshot"], "mode": "fit" }
            })
        nodes.append(node)
        i += 1
    edges = []
    results = db.read_transaction(links, request.args.get("limit", 10000))
    for result in results:
        edge = {"from": node_id[result["src"]],
                "to": node_id[result["dest"]]}
        link = result['link']
        #XXX bugged? check redirect
        if link.get("redirect"):
            edge.update({'stroke': {'dash': "10 5", 'color': '#000000'}})
        edges.append(edge)
    return Response(dumps({"nodes": nodes, "edges": edges}),
                    mimetype="application/json")


@app.route("/json/any/nodes")
def get_any_nodes():
    def pages(tx, limit):
        props = "{contentTested:true, mimeType: 'text/html'}"
        props = "{}"
        return list(tx.run(
            "MATCH (p:Page {props}) "
            "RETURN p "
            "LIMIT $limit".format(props=props),
            {"limit": limit}
        ))
    def links(tx, limit):
        props = "{contentTested:true, mimeType: 'text/html'}"
        props = "{}"
        return list(tx.run(
            "MATCH (s:Page {props})-[l:LINK_TO]->(d:Page {props}) "
            "RETURN s.url AS src, l AS link, d.url AS dest "
            "LIMIT $limit".format(props=props),
            {"limit": limit}
        ))
    def diags(tx, limit):
        props = "{}"
        return list(tx.run(
            "MATCH (d:Diag {props}) "
            "RETURN d "
            "LIMIT $limit".format(props=props),
            {"limit": limit}
        ))
    def has_diags(tx, limit):
        props = "{}"
        return list(tx.run(
            "MATCH (s:Page {props})-[l:HAS_DIAG]->(d:Diag) "
            "RETURN s.url AS src, l AS link, d.name AS name "
            "LIMIT $limit".format(props=props),
            {"limit": limit}
        ))

    db = get_db()
    #pages
    results = db.read_transaction(pages, request.args.get("limit", 10000))
    i = 0
    node_id = {}
    diag_id = {}
    nodes = []
    for result in results:
        page = result['p']
        node_id[page.get("url")] = i
        label = urlparse(page.get("url")).path[:32]
        node = {"id": i, "url": page.get("url"),
                "label": label,
                "group": 'page'}
        if page.get("screenshot"):
            node.update({ "height": 100, "width": 100,
                "shape": "square", "stroke": "none",
                "fill": { "src": page["screenshot"], "mode": "fit" }
            })
        nodes.append(node)
        i += 1
    #links
    edges = []
    results = db.read_transaction(links, request.args.get("limit", 10000))
    for result in results:
        edge = {"from": node_id[result["src"]],
                "to": node_id[result["dest"]]}
        link = result['link']
        #XXX bugged? check redirect
        if link.get("redirect"):
            edge.update({'stroke': {'dash': "10 5", 'color': '#000000'}})
        edges.append(edge)
    #diags
    results = db.read_transaction(diags, request.args.get("limit", 10000))
    for result in results:
        diag = result['d']
        diag_id[diag.get("name")] = i
        node = {"id": i, "label": diag['name'],
                "group": 'diag'}
        nodes.append(node)
        i += 1
    #has_diags
    results = db.read_transaction(has_diags, request.args.get("limit", 10000))
    for result in results:
        edge = {"from": node_id[result["src"]],
                "to": diag_id[result["name"]]}
        link = result['link']
        edges.append(edge)
    return Response(dumps({"nodes": nodes, "edges": edges}),
                    mimetype="application/json")


if __name__ == "__main__":
    logging.root.setLevel(logging.INFO)
    logging.info("Starting on port %d, database is at %s", port, url)
    app.run(port=port, host="0.0.0.0", debug=True)
