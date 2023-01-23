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

#XXX Fix globals ALL CAPS
url = keys.url
NEO4J_URL = keys.neo4j_url
username = keys.username
password = keys.password
port = keys.port

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
    homepage = j["pages"][0]
    for (url, row) in j["urls"].items():
        row["page"] = 0
        row["url"] = url
        if url in j["pages"]:
            row["page"] = 1
            row["path"] = urlparse(url).path
            #XXX add group
            if url == homepage:
                row["homePage"] = 1
            if "links" in row:
                row["fixed_links"] = []
                for (link, link_datas) in row["links"].items():
                    row["fixed_links"].append({"to": link})
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


#XXX harcoded, can get with 
#MATCH (n:Page {page:1})-[e]->(m:Page {page:1}), (n)<-[b]-(Page{page:1}) WITH count(b) AS backlinks, n, e, m WHERE (n)<--(m) AND n<>m SET n.backlinks = backlinks RETURN DISTINCT(n) ORDER BY n.backlinks DESC LIMIT 10

GROUPS = [
]


@app.route('/dexter/report', methods=['POST',])
@app.route('/dexter/report/<id>')
def dexter_report(id=None):
    """Create new db for report"""
    def pages(tx, _data):
        tx.run(
            "WITH $data AS value "
            "UNWIND value AS item "
            "MERGE (p:Page {url: item.url}) "
            "SET p.screenshot = item.screenshot.storage "
            "SET p.contentTested = item.contentTested "
            "SET p.mimeType = item.mimeType "
            "SET p.page = item.page "
            "SET p.path = item.path "
            "SET p.homePage = item.homePage ",
            {"data": _data}
        ).consume()

    def links(tx, _data):
        #XXXadd weight
        tx.run(
            "WITH $data AS value "
            "UNWIND value AS item "
            "MATCH (p:Page {url: item.url}) "
            "UNWIND [x IN item.links] AS link "
            "MATCH (l:Page {url: link.to}) "
            "MERGE (p)-[lt:LINK_TO]->(l)",
            {"data": _data}
        ).consume()

    def diags(tx, _data):
        tx.run(
            "WITH $data AS value "
            "UNWIND value AS item "
            "MATCH (p:Page {url: item.url}) "
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

    def set_backlinks(tx):
        #add weights to backlinks
        tx.run(
            "MATCH (n:Page {page:1})-[e]->(m:Page {page:1}), "
            "(n)<-[b]-(Page{page:1}) "
            "WITH count(b) AS backlinks, n, e, m "
            "WHERE (n)<--(m) AND n<>m "
            "SET n.backlinks = backlinks "
            "SET n.size=n.backlinks^2 "
            "SET n.mass=n.backlinks^0.9 "
        ).consume()

    def create_groups(tx, _groups=10):
        result = tx.run(
            "MATCH (n:Page {page:1}) "
            "WHERE n.backlinks>0 "
            "WITH n.url AS url, n.backlinks AS backlinks "
            "ORDER BY n.backlinks DESC LIMIT $groups "
            "MERGE (g:Group {label:url, backlinks:backlinks, "
            "mass:1.0, group:url}) "
            "RETURN g.label ORDER BY size(g.label) DESC",
            {"groups": _groups})
        return list(result)

    def assign_groups(tx, _label):
        tx.run(
            "MATCH (g:Group {label:$label}) "
            "WITH g, g.label AS label, size(g.label) AS label_len "
            "ORDER BY label_len DESC MATCH (p:Page {page:1}) "
            "WHERE left(p.url, label_len)=label AND NOT (p)-->(:Group) "
            "MERGE (p)-[r:IN_GROUP]->(g) "
            "SET p.group=g.group "
            "RETURN p,r,g",
            {"label": _label}
        ).consume()

    if not id:
        id = request.form.get('id')

    data = process_dexter(id)

    db = get_db()
    db.execute_write(drop_data, data)
    db.execute_write(drop_constraints, data)
    db.execute_write(init_db, data)
    db.execute_write(pages, data)
    db.execute_write(links, data)
    db.execute_write(diags, data)
    db.execute_write(set_backlinks)
    groups = db.execute_write(create_groups, 10)
    for group in groups:
        label = group['g.label']
        db.execute_write(assign_groups, label)
    label = data[0]['url']
    db.execute_write(assign_groups, label)
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
    results = db.execute_read(pages, request.args.get("limit", 100))
    nodes = []
    i = 0
    node_id = {}
    for row in results:
        node_id[row["url"]] = i
        nodes.append({"id": i, "url": row["url"], "label": "page"})
        i += 1
    rels = []
    results = db.execute_read(links, request.args.get("limit", 100))
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
    results = db.execute_read(pages, request.args.get("limit", 10000))
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
            node["screenshot_url"] = page["screenshot"]
        nodes.append(node)
        i += 1
    edges = []
    results = db.execute_read(links, request.args.get("limit", 10000))
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
    def pages(tx):
        return list(tx.run("MATCH (p:Page)-->(d:Diag) "
            "WITH p, COUNT(d) AS diags "
            "RETURN p, diags ", {} ))
    #XXX probably a better way to do this
    def warning(tx):
        return list(tx.run("MATCH (p:Page)-->(m:Diag) "
            "WHERE m.level='moderate' WITH p, COUNT(m) AS moderate "
            "RETURN p, moderate", {} ))
    def error(tx):
        return list(tx.run("MATCH (p:Page)-->(s:Diag) "
            "WHERE s.level='serious' WITH p, COUNT(s) AS serious "
            "RETURN p, serious", {} ))
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
    #diags
    diag_errors = {}
    diag_warnings = {}
    results = db.execute_read(error)
    for result in results:
        page = result['p']
        diag_errors[page['url']] = result['serious']
    results = db.execute_read(warning)
    for result in results:
        page = result['p']
        diag_warnings[page['url']] = result['moderate']
    #pages
    results = db.execute_read(pages)
    i = 0
    node_id = {}
    diag_id = {}
    nodes = []
    hompage = ''
    for result in results:
        page = result['p']
        url = page.get("url")
        if page.get('homePage') and page['homePage'] == 1:
            homepage = url
        diags_count = result['diags']
        node_id[url] = i
        label = urlparse(url).path[:32]
        group = 'good'
        if diag_warnings.get(url):
            group = 'warning'
        if diag_errors.get(url):
            group = 'error'
        node = {"id": i, "url": url,
                "label": label, 'diags': diags_count,
                'errors': diag_errors[url],
                'warnings': diag_warnings[url],
                "group": group}
        if page.get("screenshot"):
            node["screenshot_url"] = page["screenshot"]
        nodes.append(node)
        i += 1
    #links
    edges = []
    results = db.execute_read(links, request.args.get("limit", 10000))
    for result in results:
        edge = {"from": node_id[result["src"]],
                "to": node_id[result["dest"]]}
        if result["src"] == homepage or result["dest"] == homepage:
            edge["normal"] = {"stroke": {"color": "#a0a0a0", "thickness": 1}}
        else:
            edge["normal"] = {"stroke": {"color": "#a0a0a0", "thickness": 0}}
            edge["hovered"] = {"stroke": {"color": "#a0a0a0", "thickness": 1}}
            edge["selected"] = {"stroke": {"color": "#a0a0a0", "thickness": 1}}
        link = result['link']
        edges.append(edge)
    return Response(dumps({"nodes": nodes, "edges": edges}),
                    mimetype="application/json")

#neovis charts
@app.route('/neovis/')
def neovis_simple():
    return render_template('neovis/simple-example.html',
                           url = NEO4J_URL,
                           username=username, password=password)



if __name__ == "__main__":
    logging.root.setLevel(logging.INFO)
    logging.info("Starting on port %d, database is at %s", port, url)
    app.run(port=port, host="0.0.0.0", debug=True)
