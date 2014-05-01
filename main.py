from google.appengine.api import app_identity
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
import cloudstorage
from datetime import datetime
import jinja2
import os
import logging
import time
import uuid
import webapp2

# The App Engine app's default GCS bucket name. (Typically "<appid>.appspot.com".)
# If the app does not have one, replace the value with a bucket created in your
# Google Cloud Console.
BUCKET = app_identity.get_default_gcs_bucket_name()

_loader = jinja2.FileSystemLoader(os.path.dirname(__file__))
_env = jinja2.Environment(loader=_loader, autoescape=True, trim_blocks=True)


class Error(Exception):
  pass


class FileNotFoundError(Error):
  pass


class AvatarDoesNotExistError(Error):
  pass


class Avatar(ndb.Model):
  gs_object_name = ndb.StringProperty()
  created = ndb.DateTimeProperty(auto_now_add=True)

  @classmethod
  def create(cls, ident, gs_object_name):
    key = ndb.Key('Avatar', ident)
    avatar = cls(key=key, gs_object_name=gs_object_name)
    avatar.put()
    return avatar

  @classmethod
  def get(cls, ident):
    avatar = cls.get_by_id(ident)
    if avatar is None:
      raise AvatarDoesNotExistError
    return avatar

  @property
  def url(self):
    return '/avatar/{}'.format(self.ident)

  @property
  def ident(self):
    return self.key.id()

  @classmethod
  def list(cls):
    query = cls.query()
    query = query.order(-cls.created)
    return query.fetch()

  @classmethod
  def create_upload_url(cls, ident):
    root = '{}/files'.format(BUCKET)
    return blobstore.create_upload_url(
        '/avatar/{}'.format(ident),    # Internal callback RequestHandler path.
        gs_bucket_name=root)           # Where the file will be uploaded in GCS.

  def update_response_headers(self, request_headers, response_headers):
    try:
      # cloudstorage.stat doesn't use "/gs" prefix.
      gs_object_name = self.gs_object_name[3:]
      stat = cloudstorage.stat(gs_object_name)
    except cloudstorage.errors.NotFoundError as e:
      raise FileNotFoundError(str(e))

    headers = {}
    time_obj = datetime.fromtimestamp(stat.st_ctime).timetuple()
    headers['Last-Modified'] =  time.strftime('%a, %d %b %Y %H:%M:%S GMT', time_obj)
    headers['ETag'] = '"{}"'.format(stat.etag)
    if stat.content_type:
      headers['Content-Type'] = stat.content_type

    # The presence of "X-AppEngine-BlobKey" tells App Engine that we want to
    # serve the GCS blob directly to the user. This avoids reading the blob data
    # into the App Engine application. If the user has the file cached already,
    # omit the X-AppEngine-BlobKey header since we want to serve an empty response
    # with a 304 status code.
    request_etag = request_headers.get('If-None-Match')
    if request_etag != headers['ETag']:
      key = blobstore.create_gs_key(self.gs_object_name)
      headers['X-AppEngine-BlobKey'] = key

    response_headers.update(headers)


class AvatarHandler(webapp2.RequestHandler):

  def post(self, ident):
    """Called internally by the system upon successfully writing file to GCS."""
    logging.info('Creating avatar...')

    # Get the "gcs_object_name" (which is its path in GCS) from the uploaded file.
    cgi_data = self.request.POST['file']
    file_info = blobstore.parse_file_info(cgi_data)
    gs_object_name = file_info.gs_object_name

    # Store the "gcs_object_name" on our avatar entity.
    try:
      avatar = Avatar.get(ident)
      avatar.update(gs_object_name)
    except AvatarDoesNotExistError:
      avatar = Avatar.create(ident, gs_object_name)

    logging.info('Created avatar: {}'.format(avatar))

    # Redirect the user back to the homepage.
    self.redirect('/')

  def get(self, ident):
    """Displays avatar image to user."""
    try:
      avatar = Avatar.get(ident)
    except AvatarDoesNotExistError:
      self.abort()

    # Instead of streaming the uploaded blob from GCS into our App Engine app,
    # leverage GCS/App Engine "magic", leave the response body empty, and update
    # the response headers to indicate to Google that we want the GCS file to be
    # served directly to the user from GCS.
    avatar.update_response_headers(
        request_headers=self.request.headers,
        response_headers=self.response.headers)

    # Serve a 304 response code if the file is in the user's cache.
    if_none_match = self.request.headers.get('If-None-Match')
    if if_none_match and if_none_match == self.response.headers.get('ETag'):
      self.response.status = 304


class MainHandler(webapp2.RequestHandler):
  """Shows avatars and a form to upload another avatar."""

  def get(self):
    ident = str(uuid.uuid4())
    params = {
        'avatars': Avatar.list(),
        'avatar_upload_url': Avatar.create_upload_url(ident),
    }
    template = _env.get_template('form.html')
    self.response.write(template.render(params))


app = webapp2.WSGIApplication([
    ('/avatar/([^/]*)', AvatarHandler),
    ('/', MainHandler),
])
