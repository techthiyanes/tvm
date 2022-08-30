#!/usr/bin/env python3
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import json
import subprocess
import re
import base64
import logging
from urllib import request, error
from typing import Dict, Tuple, Any, Optional, List


def compress_query(query: str) -> str:
    query = query.replace("\n", "")
    query = re.sub("\s+", " ", query)
    return query


def post(url: str, body: Optional[Any] = None, auth: Optional[Tuple[str, str]] = None):
    print(f"Requesting POST to", url, "with", body)
    headers = {}
    req = request.Request(url, headers=headers, method="POST")
    if auth is not None:
        auth_str = base64.b64encode(f"{auth[0]}:{auth[1]}".encode())
        req.add_header("Authorization", f"Basic {auth_str.decode()}")

    if body is None:
        body = ""

    req.add_header("Content-Type", "application/json; charset=utf-8")
    data = json.dumps(body)
    data = data.encode("utf-8")
    req.add_header("Content-Length", len(data))

    with request.urlopen(req, data) as response:
        return response.read()


class GitHubRepo:
    def __init__(self, user, repo, token):
        self.token = token
        self.user = user
        self.repo = repo
        self.base = f"https://api.github.com/repos/{user}/{repo}/"

    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
        }

    def graphql(self, query: str, variables: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        query = compress_query(query)
        if variables is None:
            variables = {}
        response = self._request(
            "https://api.github.com/graphql",
            {"query": query, "variables": variables},
            method="POST",
        )
        if "data" not in response:
            msg = f"Error fetching data with query:\n{query}\n\nvariables:\n{variables}\n\nerror:\n{json.dumps(response, indent=2)}"
            raise RuntimeError(msg)
        return response

    def _request(self, full_url: str, body: Dict[str, Any], method: str) -> Dict[str, Any]:
        print(f"Requesting {method} to", full_url, "with", body)
        req = request.Request(full_url, headers=self.headers(), method=method.upper())
        req.add_header("Content-Type", "application/json; charset=utf-8")
        data = json.dumps(body)
        data = data.encode("utf-8")
        req.add_header("Content-Length", len(data))

        try:
            with request.urlopen(req, data) as response:
                content = response.read()
        except error.HTTPError as e:
            msg = str(e)
            error_data = e.read().decode()
            raise RuntimeError(f"Error response: {msg}\n{error_data}")

        logging.info(f"Got response from {full_url}: {content}")
        try:
            response = json.loads(content)
        except json.decoder.JSONDecodeError as e:
            return content

        return response

    def put(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(self.base + url, data, method="PUT")

    def patch(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(self.base + url, data, method="PATCH")

    def post(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(self.base + url, data, method="POST")

    def get(self, url: str) -> Dict[str, Any]:
        url = self.base + url
        print("Requesting GET to", url)
        req = request.Request(url, headers=self.headers())
        with request.urlopen(req) as response:
            response = json.loads(response.read())
        return response

    def delete(self, url: str) -> Dict[str, Any]:
        url = self.base + url
        print("Requesting DELETE to", url)
        req = request.Request(url, headers=self.headers(), method="DELETE")
        with request.urlopen(req) as response:
            response = json.loads(response.read())
        return response


def parse_remote(remote: str) -> Tuple[str, str]:
    """
    Get a GitHub (user, repo) pair out of a git remote
    """
    if remote.startswith("https://"):
        # Parse HTTP remote
        parts = remote.split("/")
        if len(parts) < 2:
            raise RuntimeError(f"Unable to parse remote '{remote}'")
        return parts[-2], parts[-1].replace(".git", "")
    else:
        # Parse SSH remote
        m = re.search(r":(.*)/(.*)\.git", remote)
        if m is None or len(m.groups()) != 2:
            raise RuntimeError(f"Unable to parse remote '{remote}'")
        return m.groups()


def git(command, **kwargs):
    command = ["git"] + command
    print("Running", command)
    proc = subprocess.run(command, stdout=subprocess.PIPE, encoding="utf-8", **kwargs)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed {command}:\nstdout:\n{proc.stdout}")
    return proc.stdout.strip()


def find_ccs(body: str) -> List[str]:
    matches = re.findall(r"(cc( @[-A-Za-z0-9]+)+)", body, flags=re.MULTILINE)
    matches = [full for full, last in matches]

    reviewers = []
    for match in matches:
        if match.startswith("cc "):
            match = match.replace("cc ", "")
        users = [x.strip() for x in match.split("@")]
        reviewers += users

    reviewers = set(x for x in reviewers if x != "")
    return list(reviewers)