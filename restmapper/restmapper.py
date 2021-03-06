#!/usr/bin/env python
# -*- coding:utf-8 -*-

import json
import logging
import re

import requests
import six

logging.basicConfig()

logger = logging.getLogger(__name__)


# logger.setLevel(logging.DEBUG)

class RestMapper(object):
    def __init__(self, url_format, parsers={}, callback=None, method=requests.get, verify_ssl=True):
        self.url_format = url_format
        # if not self.url_format.endswith("/"):
        #     self.url_format += "/"
        self.url = self.url_format
        self.parsers = parsers
        self.callback = callback
        self._method = None
        self.verify_ssl = verify_ssl
        self.auth = None
        self.client = requests.session()

    def __call__(self, auth=None, headers={}, params={}, **kwargs):
        """ Set request session with kwargs """
        session = requests.Session()
        session.auth = auth
        session.headers.update(headers)
        session.params = params

        self.url_format_parameters = kwargs
        self.session = session
        return self

    def __repr__(self):
        return "<RestMapper url={}>".format(self.url_format)

    @property
    def main(self):
        return self.method(self.url).text

    @property
    def links(self):
        return json.loads(self.main)["_links"]

    @property
    def _available_attributes(self):
        return [
            re.sub(
                "^{}(.*?)({{.+}})?$".format(self.url),
                r"\1",
                val["href"])
            for val in self.links.values()
            ]

    def __dir__(self):
        return (
            self._available_attributes
            + [
                "main",
                "links",
                "method",
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE"
            ]
        )

    @property
    def method(self):
        if self._method is None:
            return self.session.get
        else:
            return self._method

    @method.setter
    def method(self, method):
        self._method = method

    def __getitem__(self, k):
        return self.__getattr__(k)

    def __getattr__(self, k):
        if k in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            self.method = getattr(self.session, k.lower())
            return self
        else:
            method = self.method
            self.method = None
            return RestMapperCall(self.url_format, method, k, self.auth,
                                  self.parsers, self.callback, self.verify_ssl, **self.url_format_parameters)


class RestMapperCall(object):
    def __init__(self, url_format, method, path, auth, parsers, callback=None, verify_ssl=True, **kwargs):
        self.method = method
        self.components = [path]
        self.url_format = url_format
        self.auth = auth
        self.parsers = parsers
        self.method = method
        self.url_format_parameters = kwargs

        if callback is None:
            self.callback = lambda response: response
        else:
            self.callback = callback

        self.verify_ssl = verify_ssl

    def __getattr__(self, k):
        self.components.append(k)
        return self

    @property
    def main(self):
        return self.method(self.url).text

    @property
    def links(self):
        return json.loads(self.main)["_links"]

    @property
    def embedded_values(self):
        try:
            return json.loads(self.main)["_embedded"].values()
        except KeyError:
            return {}

    @property
    def embedded_links(self):
        return {
            link for link in
            {
                re.sub("^{}(.*?)({{.+}})?$".format(self.url), r"\1", link)
                for link in
                {
                    links["href"]
                    for embeddeds in self.embedded_values
                    for embedded in embeddeds
                    for links in embedded["_links"].values()
                    } | {
                    link["href"]
                    for link in self.links.values()
                    if link["href"].startswith(self.url)
                    }
                }
            if link != ''
            }

    @property
    def _available_attributes(self):
        return {
            re.sub("^([0-9]+)/", r"[\1].", link)
            for link in self.embedded_links
            }

    def __dir__(self):
        return list(
            self._available_attributes
            | {
                "main",
                "links",
                "embedded_links",
                "method",
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
            },
        )

    def __getitem__(self, k):
        self.components.append(str(k))
        return self

    @property
    def url(self):
        path = "/".join(self.components)
        if "{path}" in self.url_format:
            url_format_parameters = self.url_format_parameters
            url_format_parameters.update({'path': path})
            url = self.url_format.format(**url_format_parameters)
        else:
            url = self.url_format.format(**self.url_format_parameters) + path
        # if not url.endswith("/"):
        #     url += "/"
        return url

    def __call__(self, *args, **kwargs):
        url = self.url

        parse_response = kwargs.get('parse_response', True)
        headers = kwargs.get('headers', {})

        if 'headers' in kwargs:
            del kwargs['headers']

        if 'parse_response' in kwargs:
            del kwargs['parse_response']

        if 'params' in kwargs:
            params = kwargs['params']
            del kwargs['params']

            params.update(kwargs)
        else:
            params = kwargs

        if len(args) > 0:
            data = args[0]
        else:
            data = None

        logger.debug("URL: {}".format(url))
        response = self.method(
            url,
            data=data,
            params=params,
            auth=self.auth,
            verify=self.verify_ssl,
            headers=headers
        )

        Object = None
        if parse_response:
            for component, parser in six.iteritems(self.parsers):
                if component in self.components:
                    Object = parser

            try:
                json_response = response.json()
            except ValueError:
                return response
            else:
                self.callback(json_response)

                if parse_response and Object is not None:
                    if isinstance(json_response, list):
                        return map(lambda k: Object(**Object.parse(k)), json_response)
                    else:
                        return Object(**Object.parse(json_response))
                else:
                    return json_response
        else:
            return response
