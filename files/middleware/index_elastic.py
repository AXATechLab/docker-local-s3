from webob import Request, Response
from swift.common import utils as swift_utils
from swift.common.utils import list_from_csv

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch_dsl import DocType, Date, Integer, Keyword, Text, Nested, Object
from elasticsearch_dsl.connections import connections

class File(DocType):
    bucket = Text()
    path = Text()
    timestamp = Date()
    user = Text()
    mimetype = Text()
    metadata = Object(include_in_all=True) # untyped dictionary

    class Meta:
        index = 'files'
        doc_type = 'file'

    @staticmethod
    def get_index(bucket, path):
        return bucket + ('_'.join(path.split('/')))

    def save(self, ** kwargs):
        self.meta.id = File.get_index(self.bucket, self.path)
        return super(File, self).save(** kwargs)

class IndexElasticMiddleware(object):
    """Middleware which keeps an ElasticSearch index up-to-date when a file is created/modified/delete 
       from the object store
    """

    def __init__(self, app, conf):
        # app is the final application
        self.app = app
        self.conf = conf
        self.logger = swift_utils.get_logger(conf, log_route='index_elastic')

	str = conf.get('endpoints', 'http://elastic:changeme@172.17.0.1:9200/')
        self.endpoints = [s.strip() for s in str.split(',')]

    def remove_file(self, env, req):
        try:
            self.logger.debug('indexelastic: start async remove: %s' % (env))

            path = env['PATH_INFO']
            container, object = swift_utils.split_path(path, minsegs=1, maxsegs=2, rest_with_last=True)

            connections.create_connection(hosts=self.endpoints)

            File.init()

            idx = File.get_index(container, '/' + object)
            f = File.get(id=idx)
            f.delete()

            self.logger.debug('indexelastic: object with id %s deleted' % f.meta.id)

        except Exception:
            self.logger.exception('indexelastic: encountered exception while indexing in elastic search')


    def add_file(self, env, req):
        try:
            self.logger.debug('indexelastic: start async add: %s' % (env))

            path = env['PATH_INFO']
            container, object = swift_utils.split_path(path, minsegs=1, maxsegs=2, rest_with_last=True)

            connections.create_connection(hosts=self.endpoints)

            File.init()

            f = File()
            f.bucket = container
            f.path = '/' + object
            f.timestamp = int(float(env['HTTP_X_TIMESTAMP'])*1000)
            #f.user = env['HTTP_X_USER']
            f.mimetype = env['CONTENT_TYPE']

            # adding meta data
            metaprefix = 'X-Object-Meta-Imgmeta-'
            metakeys = [k for k in req.headers if k.startswith(metaprefix)]
            for k in metakeys:
                #self.logger.debug('header %s -> %s' % (h, req.headers[h]))
                k_short = k.replace(metaprefix, '')
                f.metadata[k_short] = req.headers[k]

            f.save()
            self.logger.debug('indexelastic: object with id %s added' % f.meta.id)

        except Exception:
            self.logger.exception('indexelastic: encountered exception while indexing in elastic search')


    def __call__(self, env, start_response):
        content_type = env.get('CONTENT_TYPE', '')

        path = env['PATH_INFO']
        version, account, container, object = swift_utils.split_path(path, minsegs=2, maxsegs=4, rest_with_last=True)

        self.logger.debug('indexelastic: %s, %s, %s' % (env['REQUEST_METHOD'], content_type, object))

        req = Request(env)

        # don't index thumbnail files (TODO: is it ok like this?)
        if 'X-Object-Transient-Sysmeta-Thumbnail' in req.headers:
            self.logger.debug('indexelastic: image is a thumbnail, skipping')
            return self.app(env, start_response)

        if object is not None and env['REQUEST_METHOD'] in ["PUT", "POST"]:
            env['eventlet.posthooks'].append(
                (self.add_file, (req,), {})
            )

        elif object is not None and env['REQUEST_METHOD'] in ["DELETE"]:
            env['eventlet.posthooks'].append(
                (self.remove_file, (req,), {})
            )

        return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def index_elastic_filter(app):
        return IndexElasticMiddleware(app, conf)
    return index_elastic_filter
