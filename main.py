#!/usr/bin/env python
from json import dumps
import logging
import os
import requests
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


def drop_db(tx, _data):
    return tx.run("MATCH (n) DETACH DELETE n").consume()


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
        row["url"] = url
        if "links" in row:
            row["fixed_links"] = []
            for (link, link_datas) in row["links"].items():
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
    return jsonify(isError= False,
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


@app.route("/info/any_node")
def get_anychart():
    return render_template("/info/any_node.html")


@app.route('/dexter/report', methods=['POST',])
@app.route('/dexter/report/<id>')
def dexter_report(id=None):
    def work(tx, _data):
        return tx.run(
            "WITH $data AS value "
            "UNWIND value AS item "
            "MERGE (p:Page {url: item.url}) "
            "SET p.screenshot = item.screenshot.storage "
            "SET p.contentTested = item.contentTested "
            "SET p.mimeType = item.mimeType "
            "WITH p, item "
            "UNWIND [x IN item.links] AS link "
            "MERGE (l:Page {url: link.to}) "
            "MERGE (p) -[le:LINK_TO]-> (l) "
            "SET le.redirect = l.redirect "
            "WITH p, item.diagnostics AS diags "
            "UNWIND [x in diags] AS diag "
            "MERGE (d:DIAGNOSTIC "
                "{category: diag.category, "
                "level: diag.level, "
                "message: diag.message}) "
            "MERGE (p) -[:HAS_DIAG]-> (d)",
            {"data": _data}
        ).consume()

    if not id:
        id = request.form.get('id')
    data = process_dexter(id)

    db = get_db()
    db.write_transaction(drop_db, data)
    summary = db.write_transaction(work, data)
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
    import random #XXX
    for row in results:
        rels.append({"source": node_id[row["src"]],
                     "target": node_id[row["dest"]]})
    return Response(dumps({"nodes": nodes, "links": rels}),
                    mimetype="application/json")


@app.route("/json/any/nodes")
def get_any_nodes():
    def pages(tx, limit):
        return list(tx.run(
            "MATCH (node:Page) "
            "RETURN node.url AS url, node.screenshot AS screenshot "
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
    results = db.read_transaction(pages, request.args.get("limit", 10000))
    nodes = []
    i = 0
    node_id = {}
    for row in results:
        #raise Exception(dir(row))
        node_id[row["url"]] = i
        node = {"id": i, "url": row["url"], "label": "page",}
        if row.get("screenshot"):
            node.update({"group": "screenshot",
                         "screenshot_storage": row["screenshot"]})
        nodes.append(node)
        i += 1
    rels = []
    results = db.read_transaction(links, request.args.get("limit", 10000))
    for row in results:
        rels.append({"from": node_id[row["src"]],
                     "to": node_id[row["dest"]]})
    return Response(dumps({"nodes": nodes, "edges": rels}),
                    mimetype="application/json")


def serialize_movie(movie):
    return {
        "id": movie["id"],
        "title": movie["title"],
        "summary": movie["summary"],
        "released": movie["released"],
        "duration": movie["duration"],
        "rated": movie["rated"],
        "tagline": movie["tagline"],
        "votes": movie.get("votes", 0)
    }


def serialize_cast(cast):
    return {
        "name": cast[0],
        "job": cast[1],
        "role": cast[2]
    }


@app.route("/graph")
def get_graph():
    def work(tx, limit):
        return list(tx.run(
            "MATCH (m:Movie)<-[:ACTED_IN]-(a:Person) "
            "RETURN m.title AS movie, collect(a.name) AS cast "
            "LIMIT $limit",
            {"limit": limit}
        ))

    db = get_db()
    results = db.read_transaction(work, request.args.get("limit", 100))
    nodes = []
    rels = []
    i = 0
    for record in results:
        nodes.append({"title": record["movie"], "label": "movie"})
        target = i
        i += 1
        for name in record["cast"]:
            actor = {"title": name, "label": "actor"}
            try:
                source = nodes.index(actor)
            except ValueError:
                nodes.append(actor)
                source = i
                i += 1
            rels.append({"source": source, "target": target})
    return Response(dumps({"nodes": nodes, "links": rels}),
                    mimetype="application/json")


@app.route("/search")
def get_search():
    def work(tx, q_):
        return list(tx.run(
            "MATCH (movie:Movie) "
            "WHERE toLower(movie.title) CONTAINS toLower($title) "
            "RETURN movie",
            {"title": q_}
        ))

    try:
        q = request.args["q"]
    except KeyError:
        return []
    else:
        db = get_db()
        results = db.read_transaction(work, q)
        return Response(
            dumps([serialize_movie(record["movie"]) for record in results]),
            mimetype="application/json"
        )


@app.route("/movie/<title>")
def get_movie(title):
    def work(tx, title_):
        return tx.run(
            "MATCH (movie:Movie {title:$title}) "
            "OPTIONAL MATCH (movie)<-[r]-(person:Person) "
            "RETURN movie.title as title,"
            "COLLECT([person.name, "
            "HEAD(SPLIT(TOLOWER(TYPE(r)), '_')), r.roles]) AS cast "
            "LIMIT 1",
            {"title": title_}
        ).single()

    db = get_db()
    result = db.read_transaction(work, title)

    return Response(dumps({"title": result["title"],
                           "cast": [serialize_cast(member)
                                    for member in result["cast"]]}),
                    mimetype="application/json")


@app.route("/movie/<title>/vote", methods=["POST"])
def vote_in_movie(title):
    def work(tx, title_):
        return tx.run(
            "MATCH (m:Movie {title: $title}) "
            "SET m.votes = coalesce(m.votes, 0) + 1;",
            {"title": title_}
        ).consume()

    db = get_db()
    summary = db.write_transaction(work, title)
    updates = summary.counters.properties_set

    db.close()

    return Response(dumps({"updates": updates}), mimetype="application/json")


if __name__ == "__main__":
    logging.root.setLevel(logging.INFO)
    logging.info("Starting on port %d, database is at %s", port, url)
    app.run(port=port, host="0.0.0.0", debug=True)
