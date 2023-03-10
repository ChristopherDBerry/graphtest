#!/usr/bin/env python
from json import dumps
import logging
import os
import requests
from urllib.parse import urlparse
import datetime

import keys

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


def drop_data(tx):
    """Delete all data, indexes, constraints"""
    tx.run("MATCH (n) DETACH DELETE n").consume()


def drop_constraints(tx):
    """Delete all data, indexes, constraints"""
    tx.run("CALL apoc.schema.assert({}, {})").consume()


def init_db(tx):
    """Initialise DB constraints, etc"""
    tx.run("CREATE CONSTRAINT FOR (p:Page) REQUIRE p.url IS UNIQUE"
           ).consume()
    tx.run("CREATE CONSTRAINT FOR (p:Page) REQUIRE p.url IS NOT NULL"
           ).consume()


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


@app.route("/json/vis/summary")
def get_vis_summary():
    def get_homepage(tx):
        result = tx.run("MATCH (p:Page {homePage: 1}) RETURN p")
        return result.single()
    def get_totals(tx):
        result = tx.run("MATCH (p:Page) RETURN "
            "SUM(p.red_techs) AS ce_techs, SUM(p.red_diags) AS ce_diags, "
            "SUM(p.a_techs) AS a_techs, SUM(p.a_diags) AS a_diags, "
            "SUM(p.aa_techs) AS aa_techs, SUM(p.aa_diags) AS aa_diags, "
            "SUM(p.axe_techs) AS axe_techs, SUM(p.axe_diags) AS axe_diags")
        return result.single()
    db = get_db()
    output = {}
    result = db.execute_read(get_homepage)
    finish = datetime.datetime.strptime(
        result['p']['finish'][:10], "%Y-%m-%d")
    output['finish'] = finish.strftime('%d %B %Y')
    output['screenshot'] = result['p']['screenshot']
    output['url'] = result['p']['url']
    result = db.execute_read(get_totals)
    output.update(result)
    return Response(dumps(output), mimetype="application/json")


@app.route("/json/vis/all")
def get_vis_hierarchy():
    def pages(tx):
        return list(tx.run(
            "MATCH (n:Page {distance:0})-[l]->(m:Page {distance:1}) "
            "OPTIONAL MATCH (m)-[l2]->(o:Page {distance:2}) "
            "OPTIONAL MATCH (o)-[l3]->(p:Page {distance:3}) "
            "RETURN n,l,m,l2,o,l3,p"))
    def clusters(tx):
        return list(tx.run("MATCH (c: Cluster) "
            "RETURN c"))
    def cluster_links(tx):
        return list(tx.run("MATCH (p:Page {page: 1})-[r]->"
            "(c: Cluster) RETURN p, r, c"))
    db = get_db()
    i = 0
    cluster_id = {}
    cluster_nodes = {}
    node_id = {}
    diag_id = {}
    nodes = []
    edges = []
    inserted_edges = []
    results = db.execute_read(pages)
    for result in results:
        for pid in ('n', 'm', 'o', 'p'):
            page = result[pid]
            if page is None:
                continue
            url = page["url"]
            if url in node_id:
                continue
            node_id[url] = i
            node = {"id": i, "label": '', "value": 1}
            node.update(page)
            if page.get("screenshot"):
                node["screenshot_url"] = page["screenshot"]
            node["group"] = page['level']
            node["page_title"] = page['title']
            distance = page['distance']
            if distance == 0: #XXX fix position of homepage
                node["y"] = 50
                node["x"] = 50
            nodes.append(node)
            i += 1
        for page_link in (('n', 'm'), ('m', 'o'), ('o', 'p')):
            from_page = result[page_link[0]]
            to_page = result[page_link[1]]
            if from_page is None or to_page is None:
                continue
            from_page = node_id[from_page["url"]]
            to_page = node_id[to_page["url"]]
            link = (from_page, to_page)
            if link in inserted_edges:
                continue
            inserted_edges.append(link)
            edge = {"from": from_page, "to": to_page, "physics": "false"}
            edges.append(edge)
    results = db.execute_read(clusters)
    for result in results:
        label = result['c']['label']
        node = {"id": i, "label": label, 'group': 'cluster', 'links': 0}
        cluster_id[label] = i
        cluster_nodes[label] = node
        i += 1
    results = db.execute_read(cluster_links)
    for result in results:
        cluster_label = result['c']['label']
        from_page = node_id.get(result['p']['url'])
        to_cluster = cluster_id.get(cluster_label)
        if from_page is None or to_cluster is None:
            continue
        cluster_nodes[cluster_label]['links'] += 1
        edge = {"from": from_page, "to": to_cluster,
                "length": 1, "hidden": "true"}
        edges.append(edge)
    for label in cluster_nodes:
        node = cluster_nodes[label]
        if node['links']:
            nodes.append(node)
    return Response(dumps({"nodes": nodes, "edges": edges}),
                    mimetype="application/json")


@app.route("/json/vis/pages/<distance>")
def get_vis_pages_distance(distance):
    def pages(tx, distance):
        return list(tx.run(
            "MATCH (n:Page {distance:$distance}) "
            "RETURN n",
            {"distance": distance}))
    def page_links(tx):
        result = tx.run("MATCH (n:Page {page:1})-[l]->(m:Page {page:1}) "
            "RETURN COUNT(l) AS total")
        limit = min(int(result.single()['total'] / 10), 1000)
        limit = 10000
        return list(tx.run("MATCH (p:Page {page: 1})-[l]->"
            "(q :Page {page: 1}) "
            "WHERE p.url <> q.url AND (q)<--(p) "
            "RETURN p.url AS from, q.url AS to, l.weight AS weight "
            "ORDER BY l.weight DESC LIMIT $limit",
            {"limit": limit}))
    def clusters(tx):
        return list(tx.run("MATCH (c: Cluster) "
            "RETURN c"))
    def cluster_links(tx):
        return list(tx.run("MATCH (p:Page {page: 1})-[r]->"
            "(c: Cluster) RETURN p, r, c"))
    distance = int(distance)
    db = get_db()
    i = 0
    cluster_id = {}
    cluster_nodes = {}
    node_id = {}
    diag_id = {}
    nodes = []
    edges = []
    inserted_edges = []
    hompage = ''
    results = db.execute_read(pages, distance)
    for result in results:
        page = result['page']
        url = page.get("url")
        if page.get('homePage') and page['homePage'] == 1:
            homepage = url
        node_id[url] = i
        label = urlparse(url).path[:32]
        label = ''
        node = {"id": i, "url": url, "group": page['level'],
                "label": label, "value": page.get("mass", 1),}
        if page.get("screenshot"):
            node["screenshot_url"] = page["screenshot"]
        nodes.append(node)
        i += 1
    results = db.execute_read(page_links)
    for result in results:
        from_page = node_id.get(result['from'])
        to_page = node_id.get(result['to'])
        if from_page is None or to_page is None:
            continue
        weight = result['weight']
        other_dir = (to_page, from_page) #skip bi direction links
        if other_dir in inserted_edges:
            continue
        inserted_edges.append((from_page, to_page))
        edge = {"from": from_page, "to": to_page,
                "weight": weight, "physics": "false"}
        edges.append(edge)
    results = db.execute_read(clusters)
    for result in results:
        label = result['c']['label']
        node = {"id": i, "label": label, 'group': 'cluster', 'links': 0}
        cluster_id[label] = i
        cluster_nodes[label] = node
        i += 1
    results = db.execute_read(cluster_links)
    for result in results:
        cluster_label = result['c']['label']
        from_page = node_id.get(result['p']['url'])
        to_cluster = cluster_id.get(cluster_label)
        if from_page is None or to_cluster is None:
            continue
        cluster_nodes[cluster_label]['links'] += 1
        edge = {"from": from_page, "to": to_cluster,
                "length": 1, "hidden": "true"}
        edges.append(edge)
    for label in cluster_nodes:
        node = cluster_nodes[label]
        if node['links']:
            nodes.append(node)
    return Response(dumps({"nodes": nodes, "edges": edges}),
                    mimetype="application/json")


#vis charts
@app.route('/vis/')
def vis_simple():
    return render_template('vis/test1.html',
                           url = NEO4J_URL,
                           username=username, password=password)

#vis charts
@app.route('/vis/2')
def vis_test2():
    return render_template('vis/test2.html',
                           url = NEO4J_URL,
                           username=username, password=password)

#vis charts
@app.route('/vis/cluster')
def vis_cluster():
    return render_template('vis/cluster.html',
                           url = NEO4J_URL,
                           username=username, password=password)


#neovis charts
@app.route('/neovis/')
def neovis_simple():
    return render_template('neovis/test1.html',
                           url = NEO4J_URL,
                           username=username, password=password)


#Image functions

@app.route('/image/<remote>')
def image(remote):
    #Fetch and clip the image
    #Obviously needs optimising
    remote = 'https://dxtfs.com/' + remote
    from PIL import Image
    import io
    import urllib
    rep = urllib.request.urlopen(remote)
    img_data = rep.read()
    output = io.BytesIO()
    with Image.open(io.BytesIO(img_data)) as im:
        im.crop((0, 0, 800, 800)).save(output, "PNG")
    return Response(output.getvalue(), mimetype="image/png")

if __name__ == "__main__":
    logging.root.setLevel(logging.INFO)
    logging.info("Starting on port %d, database is at %s", port, url)
    app.run(port=port, host="0.0.0.0", debug=True)
