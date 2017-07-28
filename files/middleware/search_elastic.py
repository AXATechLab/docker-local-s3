from webob import Request, Response
from swift.common import utils as swift_utils
from swift.common.utils import list_from_csv

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch_dsl import DocType, Date, Integer, Keyword, Text, Nested, Object
from elasticsearch_dsl.connections import connections

import json
import hashlib
import urllib
import urlparse

class SearchElasticMiddleware(object):
    """Middleware which does a search in ElastcSearch and gives back the result.

       The advantage to using a Swift middleware: we check that the user can only access the
       buckets where he has access according to Keystone.
    """

    def __init__(self, app, conf):
        # app is the final application
        self.app = app
        self.conf = conf
        self.logger = swift_utils.get_logger(conf, log_route='index_elastic')

        str = conf.get('endpoints', 'http://elastic:changeme@172.17.0.1:9200/')
        self.endpoints = [s.strip() for s in str.split(',')]

    def search(self, env, req, start_response):
        def compute_hash(string):
            m = hashlib.md5()
            m.update(string.encode('utf-8'))
            return m.hexdigest()

        try:
            self.logger.debug('searchelastic: start search: %s' % (env))

            path = env['PATH_INFO']
            version, account, container, object = swift_utils.split_path(path, minsegs=2, maxsegs=4, rest_with_last=True)

            if env['REQUEST_METHOD'] == 'GET':
                f = env['wsgi.input']
                s = f.read()
                md5 = compute_hash(s)

                self.logger.debug('searchelastic: get cont %s, obj %s' % (container, object))

                if not '?' in object:
                    return Response(status=400,
                                    body='The query string should be present',
                                    headers={'ETag': md5, 'Content-Type': 'text/plain'}
                                    )(env, start_response)

                query = object.split('?')[-1]

                if not query.startswith('q='):
                    return Response(status=400,
                                    body='The query variable should be present',
                                    headers={'ETag': md5, 'Content-Type': 'text/plain'}
                                    )(env, start_response)

                self.logger.debug('searchelastic: query raw all is %s' % query)
                q = query[len('q='):]
                self.logger.debug('searchelastic: query raw right is %s' % q)

                q = urllib.unquote(q).decode('utf8')
                q = json.loads(q)

                self.logger.debug('searchelastic: query is %s' % q)
                self.logger.debug('searchelastic: endpoints %s' % self.endpoints)

                client = Elasticsearch(self.endpoints)
                response = client.search(
                    index='files',
                    body=q
                )

                self.logger.debug('searchelastic: send response')

                return Response(status=200,
                                body=json.dumps(response),
                                headers={'ETag': md5, 'Content-Type': 'application/json'}
                                )(env, start_response)

            elif env['REQUEST_METHOD'] == 'PUT':
                f = env['wsgi.input']
                s = f.read()
                md5 = compute_hash(s)

                self.logger.debug('searchelastic: s is %s' % s)
                q = json.loads(s)

                self.logger.debug('searchelastic: query is %s' % q)

                client = Elasticsearch(self.endpoints)
                response = client.search(
                    index='files',
                    body=q
                )

                self.logger.debug('searchelastic: send response')

                return Response(status=201,
                                body=json.dumps(response),
                                headers={'ETag': md5, 'Content-Type': 'application/json'}
                                )(env, start_response)

            elif env['REQUEST_METHOD'] == 'HEAD':

                status = 204 if object is None else 200
                self.logger.debug('searchelastic: send response with status %d, object %s' % (status, object))
                return Response(status=status,
                                body="ok",
                                content_type="text/plain")(env, start_response)


        except Exception:
            self.logger.exception('searchelastic: encountered exception while searching in elastic search')

    def __call__(self, env, start_response):
        content_type = env.get('CONTENT_TYPE', '')

        path = env['PATH_INFO']
        version, account, container, object = swift_utils.split_path(path, minsegs=2, maxsegs=4, rest_with_last=True)

        req = Request(env)

        self.logger.debug('searchelastic: meth %s, ver %s, account %s, cont %s, obj %s, path %s' % (env['REQUEST_METHOD'], version, account, container, object, path))
        if container == 'search' and env['REQUEST_METHOD'] in ["HEAD", "PUT", "GET"]:

            return self.search(env, req, start_response)

        else:

            return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def search_elastic_filter(app):
        return SearchElasticMiddleware(app, conf)
    return search_elastic_filter
