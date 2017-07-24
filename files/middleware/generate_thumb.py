from webob import Request, Response
from swift.common import utils as swift_utils
from swift.common.utils import list_from_csv

from PIL import Image

import StringIO
import os

class GenerateThumbMiddleware(object):
    """Middleware which generates asynchronously an image thumbnail (for the supported mime types) and does a Swift sub
       request to add it to the object store.
    """

    def __init__(self, app, conf):
        # app is the final application
        self.app = app
        self.conf = conf
        self.logger = swift_utils.get_logger(conf, log_route='generate_thumb')

	types = conf.get('content_types', 'image/jpeg,image/png')
        self.content_types = [s.strip() for s in types.split(',')]

        self.size = int(conf.get('size', '300'))

    def generate_thumbnail(self, env, req):
        try:
            #req = Request(env)

            self.logger.debug('generatethumb: start async: %s, req class: %s, input: %s, dir on wsgi.input: %s' % (env, req.__class__, input, dir(env['wsgi.input'])))

            #req.make_body_seekable()
            f = env['wsgi.input']
            f.seek(0)

            # generate thumbnail
            size = (self.size, self.size)
            im = Image.open(f)
            im.thumbnail(size, Image.ANTIALIAS)
            exif = im.info['exif'] if 'exif' in im.info else None
            thumb_io = StringIO.StringIO()

            if exif is not None:
                im.save(thumb_io, format=im.format, exif=exif)
            else:
                im.save(thumb_io, format=im.format)

            # do subrequest
            new_env = req.environ.copy()
            new_env['wsgi.input'] = thumb_io

            path = env['PATH_INFO']
            filename, ext = os.path.splitext(path)
            new_path = filename + '_thumb' + ext
            new_env['PATH_INFO'] = new_path

            new_env['CONTENT_LENGTH'] = thumb_io.len

            # add a transient metadata to tell it's an internal thumbnail
            req.headers['X-Object-Transient-Sysmeta-Thumbnail'] = 'True'

            create_obj_req = Request.blank(new_path, new_env)
            resp = create_obj_req.get_response(self.app)

            if not (resp.status_code >= 200 and resp.status_code < 300):
                self.logger.warning('generatethumb: an error occured while saving thumbnail %s' % new_path)
            else:
                self.logger.debug('generatethumb: thumbnail generation for path %s done' % new_path)

            # if sync execution, seek to the beginning
            f.seek(0)

        except Exception:
            self.logger.exception('generatethumb: encountered exception while generating the thumbnail')


    def __call__(self, env, start_response):
        content_type = env.get('CONTENT_TYPE', '')

        path = env['PATH_INFO']
        version, account, container, object = swift_utils.split_path(path, minsegs=2, maxsegs=4, rest_with_last=True)

        self.logger.debug('generatethumb: %s, %s, %s' % (env['REQUEST_METHOD'], content_type, object))

        req = Request(env)

        #self.logger.debug('generatethumb: class of req %s' % req.__class__)

        # don't generate the thumbnail for a thumbnailed image
        if 'X-Object-Transient-Sysmeta-Thumbnail' in req.headers:
            self.logger.debug('generatethumb: image already a thumbnail, skipping')
            return self.app(env, start_response)

        if object is not None and env['REQUEST_METHOD'] in ["PUT", "POST"] and content_type in self.content_types:

            #self.logger.debug('generatethumb: dir of wsgi.input: %s, class: %s' % (dir(env['wsgi.input']), env['wsgi.input'].__class__))

            req.make_body_seekable()

            # currently I have a problem if executing the thumbnail generation code in the posthook, I cannot properly do a make_body_seekable
            # in the posthook, getting a client disconnected error, maybe this is due to the body stream not being avail anymore in the hook.
            #env['eventlet.posthooks'].append(
            #    (self.generate_thumbnail, (req,), {})
            #)

            # debug: direct call
            self.generate_thumbnail(env,req)

        return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def generate_thumb_filter(app):
        return GenerateThumbMiddleware(app, conf)
    return generate_thumb_filter
