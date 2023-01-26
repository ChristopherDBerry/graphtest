#!/usr/bin/env python

import sys
import os
import getopt
import requests
import time
from urllib.parse import urlparse
from neo4j import (
    GraphDatabase,
    basic_auth,
)
import ijson
import logging
logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)


import keys

URL = keys.url
NEO4J_URL = keys.neo4j_url
USERNAME = keys.username
PASSWORD = keys.password

NEO4J_VERSION = os.getenv("NEO4J_VERSION", "4")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


class Importer:

    def __init__(self, url, user, password):
        self.data_pages = []
        self.data_paths = {}
        self.data_links = {}
        self.driver = GraphDatabase.driver(url, auth=(user, password))

    def close(self):
        self.driver.close()

    @staticmethod
    def drop_data(tx):
        """Delete all data, indexes, constraints"""
        tx.run("MATCH (n) DETACH DELETE n").consume()

    @staticmethod
    def drop_constraints(tx):
        """Delete all data, indexes, constraints"""
        tx.run("CALL apoc.schema.assert({}, {})").consume()

    @staticmethod
    def init_db(tx):
        """Initialise DB constraints, etc"""
        tx.run("CREATE CONSTRAINT FOR (p:Page) REQUIRE p.url IS UNIQUE"
               ).consume()
        tx.run("CREATE CONSTRAINT FOR (p:Page) REQUIRE p.url IS NOT NULL"
               ).consume()

    @staticmethod
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

    @staticmethod
    def links(tx, _data):
        #XXX add weight
        tx.run(
            "WITH $data AS value "
            "UNWIND value AS item "
            "MATCH (f:Page {url: item.from}), "
            "(t:Page {url: item.to}) "
            "MERGE (f)-[lt:LINK_TO]->(t)",
            {"data": _data}
        ).consume()

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def get_cluster_urls(tx, _limit=200):
        #XXX
        result = tx.run(
            "MATCH (p:Page {page:1}) "
            "WHERE p.backlinks>0 "
            "RETURN p.url "
            "ORDER BY p.backlinks DESC LIMIT $limit ",
            {"limit": _limit})
        return [x["p.url"] for x in list(result)]

    @staticmethod
    def sort_cluster_urls(cluster_node_urls, limit=8):
      """Sort cluster_node urls by shortest, 'most different' first"""
      presorted = [[], ]
      for url in cluster_node_urls:
        position = 0
        for list_index, nodes in enumerate(presorted):
            l = list([(pos, (last_pos, x)) for (pos, (last_pos, x))
                in enumerate(nodes) if url.startswith(x)])
            if not l:
                break
            else:
                position = l[0][0]
        else:
            list_index +=1
        if list_index >= len(presorted):
            presorted.append([])
        presorted[list_index].append((position, url))
      sorted_urls = []
      for urls in presorted:
          for _, url in urls:
              sorted_urls.append(url)
              if len(sorted_urls) >= limit:
                  sorted_urls.reverse()
                  return sorted_urls
      sorted_urls.reverse()
      return sorted_urls

    @staticmethod
    def create_cluster_node(tx, _url):
        tx.run(
            "MERGE (c:Cluster {label: $url}) "
            "WITH c, size(c.label) AS label_len "
            "ORDER BY label_len DESC "
            "MATCH (p:Page {page:1}) "
            "WHERE left(p.url, label_len)=c.label AND NOT (p)-->(:Cluster) "
            "MERGE (p)-[r:IN_CLUSTER]->(c) "
            "SET p.group=c.label ",
            {"url": _url}
        ).consume()

    def process_dexter(self, did):
        """Process dexter results to be more neo4j-able"""
        data = []
        url = "https://dxtfs.com/%s(application,json)" % did
        response = requests.get(url)
#       j = response.json()
#       homepage = j["pages"][0]
#       for (url, row) in j["urls"].items():
        body = response.text
        jpages = ijson.items(body, 'pages')
        homepage = ''
        pages = []
        for page in jpages:
            if not homepage:
                homepage = page
            pages.append(page)
        body = response.text
        items = ijson.kvitems(body, 'urls')
        for (url, row) in items:
            print(url)
            page = {}
            #XXX skip repeated paths, may need to refine later
            path = urlparse(url).path
            if path in self.data_paths:
                continue
            else:
                self.data_paths[path] = 1
            page["page"] = 0
            page["url"] = url
            if 'mimeType' in row:
                page['mimeType'] = row['mimeType']
            if 'contentTested' in row:
                page['contentTested'] = row['contentTested']
            if 'screenshot' in row:
                page['screenshot'] = row['screenshot']
            if url in pages:
                page["page"] = 1
                page["path"] = path #urlparse(url).path
            if url == homepage:
                page["homePage"] = 1
            self.data_pages.append(page)
            for link in row.get("links", {}).keys():
                #XXX add weight
                self.data_links[(url, link)] = 1

    def run(self, did):
        self.process_dexter(did)
        with self.driver.session() as session:
            session.execute_write(self.drop_data)
            session.execute_write(self.drop_constraints)
            session.execute_write(self.init_db)
            SET_SIZE = 1000 # Limit large data sets
            data_subset = []
            for (n, row) in enumerate(self.data_pages, 1):
                data_subset.append(row)
                if n % SET_SIZE == 0:
                    session.execute_write(self.pages, data_subset)
                    data_subset = []
                    log.warning("%d pages" % n)
            else:
                session.execute_write(self.pages, data_subset)
                log.warning("%d pages" % n)
            data_subset = []
            for (n, row) in enumerate(self.data_links.keys(), 1):
                data_subset.append({'from': row[0], 'to': row[1]})
                if n % SET_SIZE == 0:
                    session.execute_write(self.links, data_subset)
                    data_subset = []
                    log.warning("%d links" % n)
            else:
                session.execute_write(self.links, data_subset)
                log.warning("%d links" % n)
            log.warning("setting backlinks")
            session.execute_write(self.set_backlinks)
            log.warning("building clusters")
            cluster_urls = session.execute_read(self.get_cluster_urls)
            cluster_urls = self.sort_cluster_urls(cluster_urls)
            for url in cluster_urls:
                session.execute_write(self.create_cluster_node, url)


if __name__ == '__main__':
    args_list = sys.argv[1:]
    opts = "hi:l" #XXX add a, analyze, display top div class
    long_opts = ["help", "id=", "list"]
    args, vals = getopt.getopt(args_list, opts, long_opts)

    help_string = """\
Dexter Neo4J importer
---------------------

Usage:
    {this_file} -h | --help                            Display this message
    {this_file} -i | --id <id>                         Import Dexter <id>
    {this_file} -l | --list                            List some useful dexter ids
"""
    list_string = """\
Useful dexter ids
-----------------

1fe21b88d1c3f61dbc883389234c70e7f0bad58fc29b5a7386b9fe9b7868003f       | bbk (small)
74bea74083135b9f509414888329ad599d0d28603cc87aae1d2c05d5ab5cbac3       | plymouth (med)
08932c746cdf882fd03d8c50c95d09a3f0427b720e77e77682f401041ecd3496       | selby(large)
"""
    for arg, val in args:
        if arg in ('-i', '--id'):
            importer = Importer(URL, USERNAME, PASSWORD)
            importer.run(val)
            importer.close()
            sys.exit("Done")
        if arg in ('-l', '--list'):
            sys.exit(list_string)
    sys.exit(help_string.format(this_file=sys.argv[0]))
