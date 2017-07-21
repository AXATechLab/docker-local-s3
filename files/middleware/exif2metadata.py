from webob import Request, Response
from swift.common import utils as swift_utils
from swift.common.utils import list_from_csv

import exifread

class Exif2MetadataMiddleware(object):
    """Middleware which extracts the exif metadata from the uploaded media and add them as s3 metadata headers
    """

    def __init__(self, app, conf):
        # app is the final application
        self.app = app
        self.conf = conf
        self.logger = swift_utils.get_logger(conf, log_route='exif2metadata')
	types = conf.get('content_types', 'image/jpeg,image/png')
        self.content_types = [s.strip() for s in types.split(',')]

    def __call__(self, env, start_response):
        content_type = env.get('CONTENT_TYPE', '')

        path = env['PATH_INFO']
        version, account, container, object = swift_utils.split_path(path, minsegs=2, maxsegs=4, rest_with_last=True)

        self.logger.debug('exif2metadata: %s, %s, %s' % (env['REQUEST_METHOD'], content_type, object))

        if object is not None and env['REQUEST_METHOD'] in ["PUT", "POST"] and content_type in self.content_types:

            req = Request(env)
            req.make_body_seekable()

            # env['wsgi.input'] implements a file interface
            file = env['wsgi.input']

            #self.logger.debug('exif2metadata: dir on file: %s, class %s' % (','.join(dir(file)),file.__class__))

            # details=False: will not process the Thumbnail metadata types
            tags = exifread.process_file(file, details=False)

            # currently we delete the thumbnail tag (too long)
            # maybe we want to use this later when we do the thumbnail generation
            if "JPEGThumbnail" in tags:
                del tags["JPEGThumbnail"]

            for k,v in tags.copy().iteritems():
                if not k.startswith('Thumbnail'):
                    # todo: I need to sanitize k
                    key = 'x-object-meta-imgmd-%s' % k.replace(' ', '-')
                    self.logger.info('key: %s, val: %s' % (key, v))
                    req.headers[key] = v.printable

            # reset reader to start
            file.seek(0)

        return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def exif_metadata_filter(app):
        return Exif2MetadataMiddleware(app, conf)
    return exif_metadata_filter
