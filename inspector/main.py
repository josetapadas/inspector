import os
import tarfile
import urllib.parse
import zipfile
from io import BytesIO

import packaging.version
import requests
from flask import Flask, Response, abort, redirect, render_template, request

app = Flask(__name__)

# Lightweight datastore ;)
dists = {}


@app.route("/")
def index():
    if project := request.args.get("project"):
        return redirect(f"/project/{ project }")
    return render_template("index.html")


@app.route("/project/<project_name>/")
def versions(project_name):
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/json")
    if resp.status_code != 200:
        return abort(404)

    version_urls = [
        "." + "/" + str(version)
        for version in sorted(
            resp.json()["releases"].keys(), key=packaging.version.Version, reverse=True
        )
    ]
    return render_template(
        "links.html",
        links=version_urls,
        h2=project_name,
        h2_link=f"/project/{project_name}",
    )


@app.route("/project/<project_name>/<version>/")
def distributions(project_name, version):
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/{version}/json")
    if resp.status_code != 200:
        return abort(404)

    dist_urls = [
        "." + urllib.parse.urlparse(release["url"]).path + "/"
        for release in resp.json()["releases"][version]
    ]
    return render_template(
        "links.html",
        links=dist_urls,
        h2=f"{project_name}=={version}",
        h2_link=f"/project/{project_name}/{version}",
    )


class Distribution:
    def namelist(self):
        raise NotImplementedError

    def read(self):
        raise NotImplementedError


class ZipDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        self.zipfile = zipfile.ZipFile(f)

    def namelist(self):
        return self.zipfile.namelist()

    def contents(self, filepath):
        return self.zipfile.read(filepath).decode()


class TarGzDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        self.tarfile = tarfile.open(fileobj=f, mode="r:gz")

    def namelist(self):
        return self.tarfile.getnames()

    def contents(self, filepath):
        return self.tarfile.extractfile(filepath).read().decode()


def _get_dist(first, second, rest, distname):
    if distname in dists:
        return dists[distname]
    url = f"https://files.pythonhosted.org/packages/{first}/{second}/{rest}/{distname}"
    resp = requests.get(url)
    f = BytesIO(resp.content)

    if (
        distname.endswith(".whl")
        or distname.endswith(".zip")
        or distname.endswith(".egg")
    ):
        distfile = ZipDistribution(f)
        dists[distname] = distfile
        return distfile

    elif distname.endswith(".tar.gz"):
        distfile = TarGzDistribution(f)
        dists[distname] = distfile
        return distfile

    else:
        # Not supported
        return None


@app.route(
    "/project/<project_name>/<version>/packages/<first>/<second>/<rest>/<distname>/"
)
def distribution(project_name, version, first, second, rest, distname):
    dist = _get_dist(first, second, rest, distname)

    if dist:
        file_urls = ["./" + filename for filename in dist.namelist()]
        return render_template(
            "links.html",
            links=file_urls,
            h2=f"{project_name}=={version}",
            h2_link=f"/project/{project_name}/{version}",
            h3=distname,
            h3_link=f"/project/{project_name}/{version}/packages/{first}/{second}/{rest}/{distname}/",
        )
    else:
        return "Distribution type not supported"


@app.route(
    "/project/<project_name>/<version>/packages/<first>/<second>/<rest>/<distname>/<path:filepath>"
)
def file(project_name, version, first, second, rest, distname, filepath):
    dist = _get_dist(first, second, rest, distname)

    if dist:
        return render_template(
            "code.html",
            code=dist.contents(filepath),
            h2=f"{project_name}=={version}",
            h2_link=f"/project/{project_name}/{version}",
            h3=distname,
            h3_link=f"/project/{project_name}/{version}/packages/{first}/{second}/{rest}/{distname}/",
            h4=filepath,
            h4_link=f"/project/{project_name}/{version}/packages/{first}/{second}/{rest}/{distname}/{filepath}",
        )
    else:
        return "Distribution type not supported"


@app.route("/_health/")
def health():
    return "OK"


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /", mimetype="text/plain")
